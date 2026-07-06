"""I5 — İzleme kapsama sözleşmesi: "canlıya dokunan HER davranış flag'i nasıl
izleniyor?" sorusunun TEK açık cevabı + guard.

Amaç (owner talebi 2026-07-05, `docs/LEARNING_INTEGRATION_REPORT.md`): sistemde
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
                  izlenen bir mekanizmaya (tf_platt / ağırlık auto-apply) besler.
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
    "TF_TARGET_AUTO_ONLY": {
        "mechanism": WATCHDOG, "monitor": "tf_target_auto_only",
        "reason": "TF-target girdi hijyeni aktivasyonu; OFF→ON'da watchdog baseline damgalar.",
    },
    "TF_TARGET_EDGE_GATE": {
        "mechanism": WATCHDOG, "monitor": "tf_target_edge_gate",
        "reason": "TF-target edge-stability auto-apply kapısı; watchdog izler.",
    },
    "EXIT_FORENSICS_NUDGE": {
        "mechanism": WATCHDOG, "monitor": "exit_forensics_nudge",
        "reason": "Çıkış otopsisi oransal nudge aktivasyonu; watchdog izler.",
    },
    "WEIGHT_REGIME_FILTER": {
        "mechanism": WATCHDOG, "monitor": "weight_regime_filter",
        "reason": "Rejim-filtreli ağırlık eğitimi aktivasyonu; watchdog izler.",
    },
    "MISTAKE_MEMORY_V2": {
        "mechanism": WATCHDOG, "monitor": "mistake_memory_v2",
        "reason": "Mistake memory v2 aktivasyonu; watchdog izler.",
    },
    "EXPECTANCY_R_MODE": {
        "mechanism": WATCHDOG, "monitor": "expectancy_r_mode",
        "reason": "R-bazlı expectancy aktivasyonu; watchdog izler.",
    },
    # --- OWN_ROLLBACK: auto-apply kendi outcome-rollback'ine bağlı (2) ---
    "THRESHOLD_AUTOTUNE": {
        "mechanism": OWN_ROLLBACK,
        "monitor": "packages.learning.threshold_trainer:check_rollback",
        "reason": "Eşik auto-apply; post<baseline → threshold_overrides.revert (kendi rollback).",
    },
    "TF_TARGET_TRAIL_AUTOTUNE": {
        "mechanism": OWN_ROLLBACK,
        "monitor": "packages.learning.tf_target_rollback:check_rollback",
        "reason": "TF trailing çarpanı auto-apply; tf_target_store override'ı rollback'li.",
    },
    # --- INPUT_HYGIENE: filtre/mod; zaten-izlenen mekanizmaya besler (3) ---
    "TF_CALIBRATION_AUTO_ONLY": {
        "mechanism": INPUT_HYGIENE, "monitor": None,
        "reason": "tf_platt kalibrasyonunun girdi filtresi (yalnız auto kohort); "
                  "tf_platt aktivasyonu zaten watchdog'da — ayrı aktivasyon değil.",
    },
    "WEIGHT_LOSS_AWARE": {
        "mechanism": INPUT_HYGIENE, "monitor": None,
        "reason": "Ağırlık eğitimi skorlama MODU (winsorize profit-factor); ağırlık "
                  "auto-apply zaten weight_rollback outcome-rollback'ine bağlı.",
    },
    "TF_TRUST_PER_BUCKET": {
        "mechanism": INPUT_HYGIENE, "monitor": None,
        "reason": "Canlı tf_weights kapısının per-TF SERTLEŞTİRMESİ (D4): kanıtsız "
                  "TF nötr kalır — mevcut trust-gate'i kısar, yeni canlı-dokunuş "
                  "eklemez; tf_weights zaten kalibrasyon+owner zincirinde.",
    },
    # --- TUNING_PARAM: bir izleyicinin parametresi (1) ---
    "REBALANCE_ROLLBACK_MIN_OUTCOMES": {
        "mechanism": TUNING_PARAM, "monitor": None,
        "reason": "weight_rollback'in min-outcome eşiği — aç/kapa aktivasyonu değil, "
                  "rollback mekanizmasının ta kendisinin parametresi.",
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
    "LEARNING_INCLUDE_SHADOW": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Kaynak seçici salt-gözlem (I3); yalnız damgalı kanıt gösterir, "
                  "canlı karara/hücreye dokunmaz.",
    },
    "BAR_HISTORY_ENABLED": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Bar arşivi salt-veri biriktirme (kanıt-büyütme); izole JSONL'e "
                  "yazar, canlı bar akışını/kararı DEĞİŞTİRMEZ (asla raise etmez).",
    },
    "SUBSIGNAL_SCORECARD_ENABLED": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "Sinyal karnesi (D5) salt-gözlem: haftalık sinyal×TF ileri-getiri "
                  "ölçümü, izole artifact; canlı skora/karara/paper'a ASLA yazmaz.",
    },
    "TF_SCORING_V2_SHADOW": {
        "mechanism": SHADOW_EXEMPT, "monitor": None,
        "reason": "tf_scoring_v2 (D6) gölge yön skoru: karne kanıtıyla katmanlı v2 "
                  "yönü canlı barlarda üretir, izole artifact; canlı skora/karara/"
                  "paper'a ASLA yazmaz (D7 yarış girdisi).",
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
