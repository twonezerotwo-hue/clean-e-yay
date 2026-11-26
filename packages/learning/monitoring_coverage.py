"""I5 — İzleme kapsama sözleşmesi: "canlıya dokunan HER davranış flag'i nasıl
izleniyor?" sorusunun TEK açık cevabı + guard.

Amaç (owner talebi 2026-07-05, `docs/archive/LEARNING_INTEGRATION_REPORT.md`): sistemde
otomatik-ayar / aktivasyon dağınık izleniyor — kimi `activation_watchdog`
baseline-expectancy'siyle, kimi kendi outcome-rollback'iyle, kimi de canlı karara
hiç dokunmadığı için izlemesiz (shadow). "İzlemesiz canlı-dokunuş" gözden kaçarsa
sessiz risk. Bu modül AWS'e senkronlanan her davranış flag'ini (tek kaynak:
`scripts/flag-sync-check.sh` SYNC_FLAGS) BEŞ güvenli izleme sınıfından birine
BAĞLAR ve `test_monitoring_coverage` bunu guard'lar:

  WATCHDOG      — activation_watchdog.REGISTRY baseline-expectancy izleyicisi
                  (OFF→ON'da baseline damgalanır, çöküşte DEGRADED önerisi).
  OWN_ROLLBACK  — auto-apply kendi outcome-rollback'ine bağlı (post<baseline →
                  otomatik revert). `monitor` = "modül:callable" (import edilir).
  INPUT_HYGIENE — girdi/skorlama filtresi; kendi başına aktivasyon değil, ZATEN
                  izlenen bir mekanizmaya (TF kalibrasyonu / ağırlık auto-apply) besler.
  TUNING_PARAM  — bir izleyicinin parametresi (aç/kapa aktivasyonu değil).
  SHADOW_EXEMPT — shadow/observe-only; canlı karar zincirine DOKUNMAZ (izleme
                  gereksiz — kirlenme yok).

Beş sınıfın hepsi "izlenen ya da güvenli"dir; "izlemesiz canlı-dokunuş" sınıfı
YOKTUR — yeni bir flag eklenip SYNC_FLAGS'e girince, burada da sınıflanmak
ZORUNDA (yoksa guard düşer). Böylece kör nokta oluşamaz.

KIRMIZI ÇİZGİ: bu modül salt-gözlem/sözleşme — hiçbir şeyi izlemez/kapatmaz,
yalnız "nasıl izlendiğini" beyan eder ve guard'a zemin olur.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

WATCHDOG = "watchdog"
OWN_ROLLBACK = "own_rollback"
INPUT_HYGIENE = "input_hygiene"
TUNING_PARAM = "tuning_param"
SHADOW_EXEMPT = "shadow_exempt"

MECHANISMS = frozenset({WATCHDOG, OWN_ROLLBACK, INPUT_HYGIENE, TUNING_PARAM, SHADOW_EXEMPT})

# Her SYNC_FLAGS davranış flag'i → izleme sınıfı + kanıt.
#   mechanism: yukarıdaki beş sınıftan biri.
#   monitor:   WATCHDOG → activation_watchdog.REGISTRY anahtarı;
#              OWN_ROLLBACK → "modül:callable" (import edilebilir rollback girişi);
#              diğerleri → None (mekanizma reason'da).
#   reason:    düz-dil gerekçe (LLM/panel + insan denetimi için).
COVERAGE: dict[str, dict] = {
    # --- WATCHDOG: activation_watchdog baseline-expectancy izleyicisi (6) ---
    # --- INPUT_HYGIENE: filtre/mod; zaten-izlenen mekanizmaya besler (3) ---
    "E_YAY_CANONICAL_RUNTIME": {
        "mechanism": INPUT_HYGIENE, "monitor": None,
        "reason": "Kanonik canlı karar yolunun süreç bayrağı: yalnız VERİSİ gelmeyen "
                  "modülü nötr 50 sayar ve hücreyi nötr/hold'a çeker — yalnız kısıtlar "
                  "(no-boost), açılış yetkisi eklemez; pytest/golden altında kapalı.",
    },
    # --- TUNING_PARAM: bir izleyicinin parametresi (1) ---
    "EYAY_BINANCE_OHLCV_ENABLED": {
        "mechanism": TUNING_PARAM, "monitor": None,
        "reason": "Binance spot salt-okuma gerçek mum kaynağı (Kraken'den sonra, CoinGecko'dan "
                  "önce); emir veya karar yetkisi eklemez.",
    },
    "EYAY_KRAKEN_OHLCV_ENABLED": {
        "mechanism": TUNING_PARAM, "monitor": None,
        "reason": "CoinGecko rate-limitinde kullanılan salt-okuma OHLCV sağlayıcı "
                  "seçimi; emir veya karar yetkisi eklemez.",
    },
    # --- SHADOW_EXEMPT: canlı karara dokunmaz (6) ---
    "DISCOVERY_SCAN_ENABLED": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Keşif tarayıcı GÖLGEDE koşar (K serisi); işlem açmaz, canlı karar "
                  "zinciri/RiskGate'e dokunmaz — izleme gereksiz.",
    },
    "BACKTEST_CHALLENGER_ENABLED": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "İzole backtest challenger kanalı (B serisi); canlı ağırlık/paper/"
                  "karara ASLA yazmaz — ayrı kanal.",
    },
    "SUBSIGNAL_SCORECARD_ENABLED": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Sinyal karnesi (D5) salt-gözlem: haftalık sinyal×TF ileri-getiri "
                  "ölçümü, izole artifact; canlı skora/karara/paper'a ASLA yazmaz.",
    },
    "TF_SCORING_V2_SHADOW": {
        "mechanism": INPUT_HYGIENE, "monitor": None,
        "reason": "tf_scoring üreticisi (v4+backup yön artifact'ı; flag adı tarihsel): "
                  "CANLI touche bu artifact'ı okur ama canlı tüketim AYRI YAML "
                  "flag'iyle kapılı (consensus.touche_v4; geri-alma tek satır). "
                  "Üretim durursa 3 saatte zemin motora KADEMELİ düşüş; v4 "
                  "performansı tf_scoring_race karnesiyle canlı ölçülür.",
    },
    "OPENROUTER_MODEL": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "YZ anlatıcı modeli (ücretsiz katman); yalnız metin üretir, karar/"
                  "boyut/RiskGate zincirine girmez.",
    },
    "GROQ_MODEL": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "YZ anlatıcı modeli; yalnız metin üretir, karar zincirine girmez.",
    },
    "API_AUTH_TOKEN": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "T2 — HTTP yazma-istekleri kilidi (sır; değer GitHub/wrangler "
                  "secret'ta). Karar/öğrenme zincirine DOKUNMAZ — yalnız yetkisiz "
                  "isteği 401 ile çevirir; kirlenme yok, izleme gereksiz.",
    },
    "BENZINGA_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Benzinga haber API anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: yalnız ek haber kaynağını açar; yokken sağlayıcı "
                  "kapalı, hata akışı düşürmez. İzleme ilk görülme kaydında.",
    },
    "TWELVEDATA_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Yedek fiyat zinciri anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: yalnız birincil kaynak düşünce yedeği açar; yokken "
                  "kaynak kapalı (disabled), fiyat DATA_UNAVAILABLE. İzleme sağlık ucunda.",
    },
    "ALPHAVANTAGE_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Yedek fiyat zinciri anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: yalnız birincil kaynak düşünce yedeği açar; yokken "
                  "kaynak kapalı (disabled), fiyat DATA_UNAVAILABLE. İzleme sağlık ucunda.",
    },
    "FINNHUB_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Yedek fiyat zinciri anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: yalnız birincil kaynak düşünce yedeği açar; yokken "
                  "kaynak kapalı (disabled), fiyat DATA_UNAVAILABLE. İzleme sağlık ucunda.",
    },
    "FRED_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Resmî makro kaynak anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: kaynağı açar; yokken kaynak kapalı (disabled), makro "
                  "satırı ve arşiv eksik kalır. İzleme sağlık ucunda.",
    },
    "EIA_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Resmî makro kaynak anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: kaynağı açar; yokken kaynak kapalı (disabled), makro "
                  "satırı ve arşiv eksik kalır. İzleme sağlık ucunda.",
    },
    "BLS_API_KEY": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Resmî makro kaynak anahtarı (sır; değer GitHub secret'ta). Davranış "
                  "bayrağı değil: kaynağı açar; yokken kaynak kapalı (disabled), makro "
                  "satırı ve arşiv eksik kalır. İzleme sağlık ucunda.",
    },
}


def watchdog_env_flags() -> set[str]:
    """WATCHDOG sınıfı ENV flag adları (COVERAGE anahtarları). activation_watchdog
    REGISTRY'nin env kaynaklarıyla birebir eşleşmeli (guard: test_monitoring_coverage)."""
    return {flag for flag, d in COVERAGE.items() if d["mechanism"] == WATCHDOG}


def watchdog_registry_keys() -> set[str]:
    """WATCHDOG flag'lerin activation_watchdog.REGISTRY anahtarları (monitor değeri)."""
    return {
        d["monitor"] for d in COVERAGE.values()
        if d["mechanism"] == WATCHDOG and d["monitor"]
    }


def coverage_summary() -> dict:
    """`GET /learning/monitoring-coverage` görünümü (read-only). Her davranış
    flag'inin izleme sınıfı + WATCHDOG'ların REGISTRY'de gerçekten kayıtlı olup
    olmadığı (canlı doğrulama). REGISTRY lazy okunur (import döngüsü yok)."""
    from packages.learning.activation_watchdog import REGISTRY

    by_mechanism: dict[str, int] = {}
    flags = []
    for flag, d in COVERAGE.items():
        mech = d["mechanism"]
        by_mechanism[mech] = by_mechanism.get(mech, 0) + 1
        registered = d["monitor"] in REGISTRY if mech == WATCHDOG else None
        flags.append({
            "flag": flag, "mechanism": mech, "monitor": d["monitor"],
            "registered": registered, "reason": d["reason"],
        })
    return {
        "total": len(COVERAGE),
        "by_mechanism": by_mechanism,
        "flags": flags,
        "note": (
            "izleme kapsama sözleşmesi (I5, salt-gözlem): her AWS-senkron davranış "
            "flag'i beş güvenli izleme sınıfından birinde; 'izlemesiz canlı-dokunuş' "
            "sınıfı yok — kör nokta guard'lı (test_monitoring_coverage)."
        ),
    }


__all__ = [
    "COVERAGE", "INPUT_HYGIENE", "MECHANISMS", "OWN_ROLLBACK", "SHADOW_EXEMPT",
    "TUNING_PARAM", "WATCHDOG", "coverage_summary", "watchdog_env_flags",
    "watchdog_registry_keys",
]
