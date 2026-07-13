"""Konsensüs motoru — 5 modül, rejim ağırlıklı toplam.

Modüller:
  - touche        (teknik)
  - fundamental   (rejim/makro)
  - news          (haber)
  - sentinel      (volatilite/stres)
  - quantum       (rotasyon)

Not (M5, 2026-07-02): eski `chart_pattern` slotu KALDIRILDI — hiç implement
edilmemişti ve gerçek formasyon tespiti zaten touche içinde çalışıyor
(`technical/timeframe.py` direction_tilt). Ayrı modül aynı kanıtı iki kez
sayardı (M3'teki çifte-sayım hatasının aynısı).

Eski projede `_redistribute_weights` davranışı korundu: eksik modül varsa
ağırlık otomatik yeniden dağıtılır.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import (
    load_active_weights,
    load_source_registry,
    load_thresholds,
)
from packages.regime.classifier import RegimeOutput


@dataclass
class ModuleScore:
    name: str
    score: float
    weight: float
    contribution: float


@dataclass
class ConsensusResult:
    symbol: str
    score: float                        # 0–100
    direction: str                      # bullish/bearish/neutral
    modules: list[ModuleScore]
    confluence_aligned: bool
    dominant_module: str
    timeframe: str = "1d"               # T2 — (symbol, timeframe) sinyal uzayı
    warnings: list[str] = field(default_factory=list)  # T2 additive


def _direction(s: float, bullish_min: float = 55.0, bearish_max: float = 45.0) -> str:
    """Yön etiketi — trade aksiyon eşikleriyle (consensus.bullish_min/bearish_max)
    AYNI banttan okunur. Eskiden 60/40 sabitti ama aksiyon eşiği 55/45'e
    gevşetilmişti (2026-06-20); bu uyumsuzluk [40,45] ölü-bandında "neutral signal"
    yazıp short açtırıyordu. Artık etiket ↔ aksiyon tek kaynak: short açılan her
    skor (≤bearish_max) "bearish", long açılan her skor (≥bullish_min) "bullish"."""
    if s >= bullish_min:
        return "bullish"
    if s <= bearish_max:
        return "bearish"
    return "neutral"


def _redistribute(weights: dict[str, float], available: set[str]) -> dict[str, float]:
    keep = {k: v for k, v in weights.items() if k in available}
    total = sum(keep.values())
    if total <= 0:
        # eşit dağıt
        return {k: 1.0 / max(1, len(available)) for k in available}
    return {k: v / total for k, v in keep.items()}


_STALE_AFTER_SEC = {
    "15m": 1800,
    "1h": 7200,
    "4h": 28800,
    "1d": 172800,
    "1w": 864000,
}


def _technical_degraded_reasons(t: object, timeframe: str) -> list[str]:
    reasons: list[str] = []
    bars_used = int(getattr(t, "bars_used", 0) or 0)
    if bars_used <= 0:
        reasons.append("no_bars")
    elif bars_used < 200:
        reasons.append(f"limited_bars:{bars_used}")
    if getattr(t, "rsi", None) is None:
        reasons.append("rsi_missing")
    if getattr(t, "macd", None) is None:
        reasons.append("macd_missing")
    if getattr(t, "atr", None) is None:
        reasons.append("atr_missing")
    if getattr(t, "ema_stack", None) is None:
        reasons.append("ema_stack_missing")

    ts = getattr(t, "ts", None)
    stale_after = _STALE_AFTER_SEC.get(timeframe)
    if isinstance(ts, datetime) and stale_after is not None:
        ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        age_sec = (datetime.now(UTC) - ts_utc.astimezone(UTC)).total_seconds()
        if age_sec > stale_after:
            reasons.append(f"stale_bar:{int(age_sec)}s")
    return reasons or ["degraded"]


def _degraded_direction_score(raw_score: float, reasons: list[str]) -> tuple[float, float]:
    """Use degraded technical direction, but pull it toward neutral confidence."""
    factor = 0.80
    if any(r in reasons for r in ("no_bars", "rsi_missing", "macd_missing", "atr_missing")):
        factor = min(factor, 0.55)
    if any(r.startswith("stale_bar:") for r in reasons):
        factor = min(factor, 0.70)
    if any(r.startswith("limited_bars:") for r in reasons):
        factor = min(factor, 0.80)
    if "ema_stack_missing" in reasons:
        factor = min(factor, 0.80)
    adjusted = 50.0 + ((raw_score - 50.0) * factor)
    return max(0.0, min(100.0, adjusted)), factor


# T-1 — üst-TF hiza basamağı (Elder triple-screen oranı ~×4-6): her alt dilim
# bir üst basamağın yönüne karşı tartılır. 1d'nin üstü yok (1w snapshot'ta
# hesaplanmıyor — uydurma basamak eklenmez).
_HTF_LADDER = {"15m": "1h", "1h": "4h", "4h": "1d"}
_HTF_NEUTRAL_BAND = 5.0  # üst TF |lean| < 5 → nötr sayılır, sönümleme yok


def _htf_alignment_cfg() -> dict:
    """`technical.htf_alignment` bloğu (enabled default False = bayt-aynı)."""
    try:
        return (load_thresholds().get("technical") or {}).get("htf_alignment") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _htf_dampen(
    symbol: str, snap: MarketSnapshot, timeframe: str, score: float
) -> tuple[float, str | None]:
    """T-1 — alt TF skoru üst basamağın yönüne TERSse 50'ye doğru kıs.

    YALNIZ KÜÇÜLTÜR: aynı yön → dokunmaz (boost yok); üst TF nötr/verisiz →
    dokunmaz; yön ASLA çevrilmez (çarpan [min_mult..1.0]). Çarpan her karşıtlıkta
    hesaplanıp warning satırına yazılır (shadow); yalnız flag açıkken uygulanır."""
    htf = _HTF_LADDER.get(timeframe)
    if htf is None:
        return score, None
    t = (snap.technicals_by_tf or {}).get(symbol, {}).get(htf)
    ds = getattr(t, "direction_score", None) if t is not None else None
    if ds is None:
        return score, None
    ltf_lean = score - 50.0
    htf_lean = float(ds) - 50.0
    if ltf_lean == 0.0 or abs(htf_lean) < _HTF_NEUTRAL_BAND:
        return score, None
    if (ltf_lean > 0) == (htf_lean > 0):
        return score, None  # aynı yön — asla boost edilmez
    cfg = _htf_alignment_cfg()
    try:
        min_mult = min(1.0, max(0.0, float(cfg.get("min_mult", 0.6))))
    except (TypeError, ValueError):
        min_mult = 0.6
    strength = min(1.0, abs(htf_lean) / 50.0)  # üst TF ne kadar kararlı
    mult = 1.0 - (1.0 - min_mult) * strength
    adjusted = 50.0 + ltf_lean * mult
    enabled = bool(cfg.get("enabled", False))
    tag = "htf_alignment" if enabled else "htf_alignment_shadow"
    warning = (
        f"{tag}:{symbol}:{timeframe}vs{htf}:htf_score={float(ds):.1f}:"
        f"mult={mult:.3f}:raw={score:.2f}:used={adjusted if enabled else score:.2f}"
    )
    return (adjusted if enabled else score), warning


def _touche(
    symbol: str,
    snap: MarketSnapshot,
    timeframe: str = "1d",
) -> tuple[float, list[str]]:
    """Technical module score for one (symbol, timeframe).

    T-1: taban skor `_touche_base`'ten gelir; üst-TF karşıtlığında flag'li
    sönümleme (`_htf_dampen`) uygulanır — shadow satırı her karşıtlıkta yazılır."""
    score, warnings = _touche_base(symbol, snap, timeframe)
    adjusted, htf_warning = _htf_dampen(symbol, snap, timeframe, score)
    if htf_warning is not None:
        warnings.append(htf_warning)
    return adjusted, warnings


def _touche_base(
    symbol: str,
    snap: MarketSnapshot,
    timeframe: str = "1d",
) -> tuple[float, list[str]]:
    """Technical module score for one (symbol, timeframe).

    Priority: technicals_by_tf[symbol][timeframe] -> legacy technicals[symbol].
    DEGRADED snapshots with direction_score keep direction but are dampened toward
    neutral and surfaced through warnings. Without direction_score, fallback is 50.
    """
    warnings: list[str] = []
    t = None
    if snap.technicals_by_tf and symbol in snap.technicals_by_tf:
        t = snap.technicals_by_tf[symbol].get(timeframe)
    if t is None:
        t = snap.technicals.get(symbol)
        if t is not None and timeframe != t.timeframe:
            warnings.append(f"touche_fallback_legacy:{symbol}:{timeframe}")
    if t is None:
        warnings.append(f"touche_no_technicals:{symbol}:{timeframe}")
        return 50.0, warnings
    # Top-down gated direction (momentum trigger + location/pattern/volume gate) is
    # the authoritative technical read; fall back to legacy `score` (RSI+MACD only)
    # when the gated score is unavailable (older snapshots / insufficient momentum).
    ds = getattr(t, "direction_score", None)
    if getattr(t, "status", "OK") == "DEGRADED":
        if ds is not None:
            reasons = _technical_degraded_reasons(t, timeframe)
            adjusted, factor = _degraded_direction_score(float(ds), reasons)
            warnings.append(
                "touche_degraded_dampened:"
                f"{symbol}:{t.timeframe}:raw={float(ds):.2f}:used={adjusted:.2f}:"
                f"factor={factor:.2f}:reasons={','.join(reasons)}"
            )
            return adjusted, warnings
        warnings.append(f"touche_degraded_neutral:{symbol}:{t.timeframe}:no_direction_score")
        return 50.0, warnings
    if ds is not None:
        return ds, warnings
    warnings.append(f"touche_legacy_score_fallback:{symbol}:{t.timeframe}")
    return t.score, warnings


# Teknik oy kaynağı (2026-07-12 owner kararı): tf_scoring_v4 owner formülü
# BİRİNCİL, touche_backup (v2 rejim-anahtarlı motor) YEDEK. Artifact bu yaştan
# eskiyse (öğrenme worker'ı durmuşsa) zemin teknik motora düşülür.
_TOUCHE_SHADOW_MAX_AGE_SEC = 3 * 3600


def _touche_v4_enabled() -> bool:
    """`consensus.touche_v4` owner-flag'i (default KAPALI = zemin motor birebir).

    Açıkken teknik yön oyu kademelidir: tf_scoring_v4 (owner birleşik formülü)
    BİRİNCİL; v4 çekimserse touche_backup (v2 rejim-anahtarlı motor) konuşur;
    ikisi de yoksa zemin teknik motor. Geri-alma = bu flag false (tek satır)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("touche_v4", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _touche_speaker_tf_only_enabled() -> bool:
    """`consensus.touche_speaker_tf_only` owner-flag'i (default KAPALI = bayt-aynı).

    2026-07-13 dış denetim P0 bulgusu: v4 artifact'ı sembol başına TEK yön taşır
    (konuşmacı TF: UP→1d, DOWN→4h) ama consensus bu yönü DÖRT timeframe hücresine
    de kopyalıyordu — aynı sinyalden çoklu pozisyon riski. Açıkken v4/backup oyu
    yalnız artifact'ın kendi konuşmacı TF hücresinde sayılır; diğer hücreler
    TF-duyarlı zemin motora düşer (uydurma yön yok). Geri-alma = false."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("touche_speaker_tf_only", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _dir_to_score(d) -> float | None:
    """Yön (−1..+1) → 0-100 teknik skor (50=nötr). None geçer."""
    if d is None:
        return None
    try:
        return max(0.0, min(100.0, 50.0 + float(d) * 50.0))
    except (TypeError, ValueError):
        return None


def _touche_shadow_row(symbol: str) -> tuple[float | None, float | None, str | None]:
    """Üretici artifact'ından (v4, backup, speaker_tf) üçlüsü → 0-100 + TF etiketi.

    v4 = tf_scoring_v4 owner formülü (BİRİNCİL); backup = touche_backup
    (EDGE-kanıtlı karne yolu, YEDEK); speaker_tf = üreticinin yönü hangi
    timeframe için hesapladığı (rejim konuşmacısı). Artifact yok/bayat/bozuk →
    (None, None, None): çağıran zemin motora düşer (dürüst: uydurma yön yok,
    öğrenme worker'ı durursa canlı tick bağımsız kalır). Salt-okur; lazy import
    (yük-zamanı decision→learning bağı yok)."""
    try:
        from packages.learning import tf_scoring_shadow
        path = tf_scoring_shadow.artifact_path()
        if not path.exists():
            return None, None, None
        data = json.loads(path.read_text(encoding="utf-8"))
        gen = datetime.fromisoformat(str(data.get("generated_at")))
        if (datetime.now(UTC) - gen).total_seconds() > _TOUCHE_SHADOW_MAX_AGE_SEC:
            return None, None, None  # öğrenme worker'ı durmuş → zemine düş
        row = (data.get("per_symbol") or {}).get(symbol) or {}
        speaker = row.get("speaker_tf")
        return (
            _dir_to_score(row.get("direction_v4")),
            _dir_to_score(row.get("direction_backup")),
            str(speaker) if speaker else None,
        )
    except (OSError, ValueError, TypeError, KeyError):
        return None, None, None


def _touche_shadow(symbol: str) -> tuple[float | None, float | None]:
    """Geriye-uyum sarmalayıcı: (v4, backup) çifti — speaker_tf'siz eski imza."""
    v4, backup, _ = _touche_shadow_row(symbol)
    return v4, backup


def _fundamental(regime: RegimeOutput) -> float | None:
    # likidite + crypto + rotation layer'larının ortalaması
    layers = [layer for layer in regime.layers if layer.name != "Risk İştahı"]
    if not layers:
        # F2-3: makro katman kalmadı (drop_unavailable_layers) — 0/1=0 gibi
        # saçma skor üretme; modül düşer, ağırlığı redistribute edilir.
        return None
    return sum(layer.score for layer in layers) / len(layers)


def _fundamental_v2(regime: RegimeOutput) -> float | None:
    """M3 — fundamental v2: Kripto Momentum katmanı HARİÇ (likidite + rotasyon).

    v1'de BTC'nin 1d teknik skoru hem touche modülünde hem fundamental'in
    içindeki Kripto Momentum katmanında sayılıyordu (çifte sayım). v2 makroyu
    saf tutar. Katman kalmazsa None → modül düşer (redistribute)."""
    layers = [
        layer for layer in regime.layers
        if layer.name not in ("Risk İştahı", "Kripto Momentum")
    ]
    if not layers:
        return None
    return sum(layer.score for layer in layers) / len(layers)


def _fundamental_v3(regime: RegimeOutput) -> float | None:
    """Fundamental v3 (GÖLGE) — Sermaye Rotasyonu da HARİÇ (saf makro = Likidite).

    2026-07-13 dış denetim P0 bulgusu: v2 Kripto Momentum'u çıkarırken Rotasyonu
    içeride bırakmıştı; aynı rotasyon skoru quantum modülünde ve rejim
    sınıflandırıcısında da sayılıyor (üçlü sayım — quantum'un gerçek etkisi
    görünen ağırlığının ~2 katı). v3 fundamental'i rotasyondan arındırır;
    rotasyon oyu YALNIZ quantum'da kalır. Katman kalmazsa None → modül düşer
    (redistribute). Aktivasyon owner kararı + kural #3 (5y çok-rejim backtest)."""
    layers = [
        layer for layer in regime.layers
        if layer.name not in ("Risk İştahı", "Kripto Momentum", "Sermaye Rotasyonu")
    ]
    if not layers:
        return None
    return sum(layer.score for layer in layers) / len(layers)


def _fundamental_v3_enabled() -> bool:
    """`consensus.fundamental_v3` owner-flag'i (default KAPALI = v2/v1 birebir).

    Açılana kadar v3 skoru her hücrede `fundamental_v3_observe` warning
    satırıyla SALT-GÖZLEM olarak izlenir; aktivasyon ayrı tarihli owner kararı."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("fundamental_v3", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


# v4 memoize: DXY/US10Y bar arşivi dosya-imzası (boyut+mtime) değişmedikçe tick
# içi 20+ hücre tek hesabı paylaşır (sıcak yol; zaman-bağımsız → test-flake yok).
_FUND_V4_MEMO: dict = {"key": None, "val": None}


def _fundamental_v4() -> float | None:
    """Fundamental v4 (GÖLGE) — DEĞİŞİM-bazlı makro likidite (ADAY B, 5y tezgâh).

    2026-07-13 Basamak-4: mevcut Likidite formülü mutlak seviyeye çapalıydı (5y'da
    1118/1118 gün ≥55 — hiç bearish olamıyor). v4 DXY + 10y faizin çoklu-ufuk
    vol-norm momentumundan gelir (yükseliyorsa sıkılaşma = risk-off). Üretici
    `flow.liquidity_momentum_score` (tek kaynak; macro_backtest ADAY B birebir).
    Seri bar arşivinden (asset-level); arşiv yok/kapalı/yetersiz → None → kademe
    v3/v2/v1'e düşer (dürüst degrade). Salt-okur; lazy import."""
    try:
        from packages.data.providers.ohlcv import history

        def _sig(sym: str):
            try:
                st = history._path(sym, "1d").stat()
                return (st.st_size, int(st.st_mtime))
            except OSError:
                return None

        key = (history.enabled(), _sig("DXY"), _sig("US10Y"))
        if _FUND_V4_MEMO["key"] == key:
            return _FUND_V4_MEMO["val"]
        from packages.data.providers.rotation import flow

        dxy = [b.close for b in history.load("DXY", "1d")]
        us10y = [b.close for b in history.load("US10Y", "1d")]
        val = flow.liquidity_momentum_score(dxy, us10y)
        _FUND_V4_MEMO["key"], _FUND_V4_MEMO["val"] = key, val
        return val
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _fundamental_v4_enabled() -> bool:
    """`consensus.fundamental_v4` owner-flag'i (default KAPALI = v3/v2/v1 birebir).

    Açılana kadar v4 skoru her hücrede `fundamental_v4_observe` warning satırıyla
    SALT-GÖZLEM (owner v4↔mevcut ayrışmasını izler); aktivasyon ayrı owner kararı.
    Kanıt: macro_backtest ADAY B — merkez düzeldi + tüm hedeflerde genel pozitif."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("fundamental_v4", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _fundamental_v2_enabled() -> bool:
    """`consensus.fundamental_v2` owner-flag'i (default KAPALI = v1 birebir).

    Aktivasyon ayrı tarihli owner kararı; açılana kadar v2 skoru her hücrede
    `fundamental_v2_observe` warning satırıyla SALT-GÖZLEM olarak izlenir."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("fundamental_v2", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _news_symbol_filter_enabled() -> bool:
    """consensus.news_symbol_filter — owner-flag (default KAPALI = eski davranış).

    Açıkken _news yalnız o sembole `asset_impact` taşıyan VERIFIED başlıkları
    sayar (DATA_POLICY: verified=False consensus'a girmez). Kapalıyken global
    sentiment tally'si birebir korunur (bozulma yok, tek satır geri dönüş)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("news_symbol_filter", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _news_abstain_enabled() -> bool:
    """`consensus.news_abstain` owner-flag'i (default KAPALI = bayt-aynı).

    2026-07-13 dış denetim bulgusu: "haber yok" ile "boğa/ayı dengede" aynı şey
    değildir — kanıtsız modülün 50 (nötr) OY'u consensus'u yapay etkiler (ağırlığı
    skoru 50'ye çeker). Açıkken ilgili başlık yoksa news modülü OY KULLANMAZ
    (None → düşer, ağırlığı _redistribute; kapsama da dürüstçe azalır — M10 ile
    bileşik). Kapalıyken her boş-kanıt hücresinde `news_abstain_observe` satırı
    birikir. Geri-alma = false (tek satır)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("news_abstain", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _news_evidence_gap(snap: MarketSnapshot, symbol: str | None) -> str | None:
    """News modülünün kanıt boşluğu: ilgili başlık yoksa sebep etiketi, varsa None."""
    if symbol is not None and _news_symbol_filter_enabled():
        has = any(h.verified and symbol in h.asset_impact for h in snap.headlines)
        return None if has else "no_relevant_headlines"
    if any(h.sentiment for h in snap.headlines):
        return None
    return "no_headlines"


def _news(snap: MarketSnapshot, symbol: str | None = None) -> float | None:
    """Haber modülü skoru (0-100, 50 = nötr).

    Sembol-ilişkili mod (news_symbol_filter açık + symbol verilmiş): yalnız
    `headline.asset_impact[symbol]` taşıyan verified başlıklar sayılır; yön
    global sentiment yerine sembole özgü impact'ten gelir (örn. hawkish Fed
    haberi bearish sentiment'lidir ama DXY için +1). İlgili başlık yoksa 50
    (nötr) — asset_impact haritasında olmayan semboller (örn. custom hisseler)
    alakasız küresel haber gürültüsüyle OYNAMAZ.

    Legacy mod (flag kapalı veya symbol None): tüm başlıkların sentiment
    tally'si — mevcut davranış birebir."""
    if symbol is not None and _news_symbol_filter_enabled():
        vals = [
            float(h.asset_impact[symbol])
            for h in snap.headlines
            if h.verified and symbol in h.asset_impact
        ]
        if not vals:
            # news_abstain açıkken kanıtsız modül OY KULLANMAZ (None → düşer).
            return None if _news_abstain_enabled() else 50.0
        return 50.0 + (sum(vals) / len(vals)) * 25.0
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    for h in snap.headlines:
        if h.sentiment:
            tally[h.sentiment] += 1
    total = sum(tally.values())
    if not total:
        return None if _news_abstain_enabled() else 50.0
    return 50.0 + (tally["bullish"] - tally["bearish"]) / total * 25.0


def _sentinel(regime: RegimeOutput) -> float | None:
    # F2-3: Risk İştahı katmanı düştüyse (VIX verisi yok) nötr-50 uydurulmaz;
    # modül düşer, ağırlığı redistribute edilir. Flag kapalıyken katman hep var.
    return next(
        (layer.score for layer in regime.layers if layer.name == "Risk İştahı"),
        None,
    )


# M4 — sentinel v2: tek-gösterge VIX yerine çok-girdili stres kompoziti.
# Tüm girdiler snapshot'ta ZATEN hesaplanıyor (yeni ağ çağrısı yok); v2 yalnız
# bunları tek 0-100 eksende (yüksek = sakin / risk iştahı) birleştirir.
# Eksik girdi ağırlığı kalanlara redistribute edilir (quantum deseni; DATA_POLICY:
# eksik girdi için skor uydurulmaz). Bileşen ağırlıkları config'ten okunur.
_SENTINEL_V2_DEFAULT_WEIGHTS = {
    "vix": 0.5,          # makro korku endeksi (mevcut v1 girdisi)
    "volatility": 0.25,  # sembolün (symbol, tf) realized-vol z-skoru + shock
    "derivatives": 0.15, # kripto squeeze proxy (yalnız kripto sembolleri)
    "options": 0.10,     # BTC/ETH IV/skew/term stres rejimi
}

# Options stres rejimi → sakinlik skoru (0-100). Sıralama gerekçesi:
# PUT_SKEW_STRESS en stresli (çöküş hedge talebi), RICH_VOL/TERM_STRESS
# yüksek stres, CALL_SKEW_EUPHORIA aşırı iyimserlik (nötr-altı sağlıklı
# değil), CHEAP_VOL/NORMAL sakin.
_OPTIONS_REGIME_CALM = {
    "NORMAL": 70.0,
    "CHEAP_VOL": 60.0,
    "CALL_SKEW_EUPHORIA": 50.0,
    "RICH_VOL": 30.0,
    "TERM_STRESS": 30.0,
    "PUT_SKEW_STRESS": 25.0,
}


def _sentinel_v2_cfg() -> dict:
    """`sentinel_v2` config bloğu (enabled default False = v1 birebir)."""
    try:
        return load_thresholds().get("sentinel_v2") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _sentinel_v2_enabled() -> bool:
    """`sentinel_v2.enabled` owner-flag'i (default KAPALI = v1 birebir).

    Aktivasyon ayrı tarihli owner kararı; açılana kadar v2 skoru her hücrede
    `sentinel_v2_observe` warning satırıyla SALT-GÖZLEM olarak izlenir."""
    return bool(_sentinel_v2_cfg().get("enabled", False))


def _sentinel_v2(
    regime: RegimeOutput, snap: MarketSnapshot, symbol: str, timeframe: str
) -> float | None:
    """M4 — stres kompoziti (0-100, yüksek = sakin). Girdi yoksa None → modül düşer.

    DATA_POLICY: VIX dışındaki girdiler yalnız verified + status OK ise sayılır
    (fixture/degraded veri karar zincirine girmez)."""
    parts: dict[str, float] = {}
    vix = _sentinel(regime)
    if vix is not None:
        parts["vix"] = float(vix)
    v = (getattr(snap, "volatility", None) or {}).get(symbol, {}).get(timeframe)
    if (
        v is not None
        and getattr(v, "status", None) == "OK"
        and getattr(v, "verified", False)
        and v.vol_zscore is not None
    ):
        # z=0 → 50 nötr; z=-2 (çok sakin) → 100; z=+2 (extreme) → 0. Shock
        # durumunda tavan 25 (ani hareket sakinlik sayılamaz).
        s = max(0.0, min(100.0, 50.0 - 25.0 * float(v.vol_zscore)))
        if getattr(v, "vol_state", "") == "shock":
            s = min(s, 25.0)
        parts["volatility"] = s
    d = (getattr(snap, "derivatives", None) or {}).get(symbol)
    if (
        d is not None
        and getattr(d, "status", None) == "OK"
        and getattr(d, "verified", False)
        and d.squeeze_proxy is not None
    ):
        # squeeze_proxy 0-100 (yüksek = squeeze baskısı) → sakinlik = 100 − proxy.
        parts["derivatives"] = max(0.0, min(100.0, 100.0 - float(d.squeeze_proxy)))
    o = (getattr(snap, "options", None) or {}).get(symbol)
    if o is not None and getattr(o, "status", None) == "OK" and getattr(o, "verified", False):
        calm = _OPTIONS_REGIME_CALM.get(str(getattr(o, "regime", "")))
        if calm is not None:
            parts["options"] = calm
    if not parts:
        return None
    cfg_w = _sentinel_v2_cfg().get("weights") or {}
    base = {
        k: float(cfg_w.get(k, dv)) for k, dv in _SENTINEL_V2_DEFAULT_WEIGHTS.items()
    }
    w = _redistribute(base, set(parts))
    return sum(parts[k] * w.get(k, 0.0) for k in parts)


def _quantum(snap: MarketSnapshot) -> float:
    return snap.rotation.score


def _quantum_v2_enabled() -> bool:
    """`consensus.quantum_v2` owner-flag'i (default KAPALI = v1 birebir).

    Açıkken quantum oyu tek makro tilt yerine SEMBOL-BAŞI kesitsel göreceli-güç
    (para akışı: lider/geride) skorundan gelir (rotation.per_symbol). Kanıtsız
    (yeterli veri yok) sembolde v1'e düşer. Aktivasyon owner kararı; v2 skoru her
    hücrede `quantum_v2_observe` satırıyla yan yana."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("quantum_v2", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _quantum_v2(snap: MarketSnapshot, symbol: str) -> float | None:
    """Sembolün kesitsel göreceli-güç (para akışı) skoru (0-100) veya None.

    rotation.per_symbol'dan okur (rotation motoru üretir); sembol yoksa/veri
    yetersizse None → çağıran v1 makro tilte düşer (dürüst). getattr ile savunmacı
    (eski kayıt/test snap'inde alan olmayabilir → v1)."""
    per_symbol = getattr(snap.rotation, "per_symbol", None) or {}
    val = per_symbol.get(symbol)
    return float(val) if val is not None else None


def _quantum_regime_gate_enabled() -> bool:
    """`consensus.quantum_regime_gate` owner-flag'i (default KAPALI = bayt-aynı).

    Kanıt (challenger karnesi, CANLI ölçüm): quantum OFFENSIVE'da pozitif
    ayrışıyor (sep +0.0142), NEUTRAL'da TERS (sep −0.0106) — göreceli-momentum
    yatay piyasada "yükselene al" = tepeden almak. Açıkken quantum oyu yalnız
    izinli rejimlerde sayılır; diğerlerinde modül DÜŞER (ağırlığı _redistribute
    ile dağılır — nötr-50 uydurulmaz). Geri-alma = false (tek satır)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("quantum_regime_gate", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


_QUANTUM_GATE_DEFAULT_REGIMES = ("OFFENSIVE",)


def _quantum_gate_allowed_regimes() -> set[str]:
    """Kapı açıkken quantum'un konuşabildiği rejimler (config; default yalnız
    OFFENSIVE — kanıtın pozitif olduğu tek rejim)."""
    try:
        raw = load_thresholds().get("consensus", {}).get("quantum_gate_allowed_regimes")
        vals = [str(x).strip().upper() for x in (raw or _QUANTUM_GATE_DEFAULT_REGIMES)]
        return {v for v in vals if v}
    except (OSError, KeyError, ValueError, TypeError):
        return set(_QUANTUM_GATE_DEFAULT_REGIMES)


# Kaynak kind → consensus modülü eşlemesi (source_registry `decision_usage`
# uygulaması). Fiyat/makro kaynakları (verified_required) touche/fundamental/
# sentinel'i besler — kısıt yalnız rotation→quantum ve news*→news kaynaklarında.
_KIND_TO_MODULE = {"rotation": "quantum", "news": "news", "news_geo": "news"}
_RESTRICTED_USAGES = ("analytics_only", "simulation_only")


def _enforce_decision_usage_enabled() -> bool:
    """`consensus.enforce_decision_usage` owner-flag'i (default KAPALI = bayt-aynı).

    2026-07-13 dış denetim P1 bulgusu: source_registry haber kaynaklarını
    `analytics_only`, rotasyon kaynaklarını `simulation_only` etiketler ama
    consensus bu politikayı UYGULAMIYORDU — etiket fiilen dokümantasyondu.
    Açıkken kısıtlı-kaynaklı modüller (news, quantum) yön kararına GİRMEZ
    (modül düşer, ağırlığı _redistribute; nötr-50 uydurulmaz). Kapalıyken her
    hücrede `decision_usage_observe` kanıt satırı birikir. Geri-alma = false."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("enforce_decision_usage", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _restricted_modules() -> dict[str, str]:
    """source_registry'den kısıtlı consensus modülleri: {modül: en-kısıtlı etiket}.

    verified_required = tam karar hakkı; analytics_only/simulation_only karar
    zincirinde kısıtlı. Modülü besleyen kaynaklardan herhangi biri kısıtlıysa
    modül o etiketi taşır (analytics_only > simulation_only muhafazakârlığı).
    Registry okunamazsa boş dict (kısıt uygulanmaz — mevcut davranış)."""
    try:
        out: dict[str, str] = {}
        for src in load_source_registry().get("sources") or []:
            mod = _KIND_TO_MODULE.get(str(src.get("kind", "")))
            usage = str(src.get("decision_usage", ""))
            if mod and usage in _RESTRICTED_USAGES and out.get(mod) != "analytics_only":
                out[mod] = usage
        return out
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}


def _min_module_coverage() -> float:
    """`consensus.min_module_coverage` (default 0.0 = KAPALI = bayt-aynı).

    2026-07-13 dış denetim P1 bulgusu: modül düşünce `_redistribute` ağırlığını
    kalanlara TAM dağıtıyor — veri azaldıkça kalan kanıtlar güçleniyor (ters
    davranış; CRISIS'te sentinel düşerse ~%53 ağırlık diğerlerine şişer).
    0'dan büyükse: mevcut modüllerin TABAN ağırlık toplamı (kapsama) bu eşiğin
    altına düşerse yön nötre zorlanır (işlem açılmaz; skor/modüller raporda
    aynen kalır — yalnız yön kararı kısıtlanır). Kapsama her eksik-modüllü
    hücrede `coverage_observe` satırıyla flag'siz izlenir. Geri-alma = 0.0."""
    try:
        v = load_thresholds().get("consensus", {}).get("min_module_coverage", 0.0)
        return float(v or 0.0)
    except (OSError, KeyError, ValueError, TypeError):
        return 0.0


def _dominant_directional_enabled() -> bool:
    """`consensus.dominant_directional` owner-flag'i (default KAPALI = bayt-aynı).

    2026-07-13 dış denetim bulgusu: legacy dominant `max(score×weight)` bearish
    modülü HİÇBİR ZAMAN dominant seçemez (skor 5 × ağırlık 0.5 = 2.5, skor 70 ×
    ağırlık 0.2 = 14 kazanır) — mistake-memory fingerprint'i dersi yanlış modüle
    yazar. Açıkken dominant nötr-50 merkezli yön katkısıyla seçilir:
    `max(|score−50| × weight)`. İki hesap her hücrede `dominant_observe`
    satırıyla yan yana (flag'siz gözlem). Geri-alma = false (tek satır)."""
    try:
        return bool(load_thresholds().get("consensus", {}).get("dominant_directional", False))
    except (OSError, KeyError, ValueError, TypeError):
        return False


MODULE_ORDER = ["touche", "fundamental", "news", "sentinel", "quantum"]


def build(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    timeframe: str = "1d",
) -> ConsensusResult:
    # T2 — timeframe yalnızca teknik (touche) modülünü farklılaştırır;
    # makro/haber/rotasyon katmanları asset-level kalır. Default "1d" ile
    # mevcut asset-level davranış birebir korunur.
    # Teknik oy kademesi (2026-07-12 owner kararı): v4 owner formülü BİRİNCİL,
    # touche_backup (v2 rejim-anahtarlı motor) YEDEK, zemin teknik motor en dip
    # paraşüt. Varyantlar her zaman gözlem satırında yan yana (owner kanıtı
    # buradan izler). RiskGate/boyut/manuel kuyruk DEĞİŞMEZ — yalnız yön oyu.
    touche_base, tf_warnings = _touche(symbol, snap, timeframe)
    sh_v4, sh_backup, speaker_tf = _touche_shadow_row(symbol)
    # TF-kapısı (2026-07-13, gölge-önce): artifact sembol başına TEK yön taşır
    # (konuşmacı TF). Kapı açıkken bu yön yalnız kendi TF hücresinde sayılır;
    # diğer hücreler TF-duyarlı zemin motora düşer. Gözlem satırı HER ZAMAN
    # yazılır (kanıt birikir); kapalıyken karar davranışı bayt-aynı.
    if (
        speaker_tf
        and speaker_tf != timeframe
        and (sh_v4 is not None or sh_backup is not None)
    ):
        tf_gate_applied = _touche_speaker_tf_only_enabled()
        tf_warnings.append(
            "touche_tf_gate_observe:"
            f"speaker={speaker_tf}:cell={timeframe}:"
            f"applied={'yes' if tf_gate_applied else 'no'}"
        )
        if tf_gate_applied:
            sh_v4, sh_backup = None, None  # kopya yön yok → zemin motor konuşur
    if _touche_v4_enabled() and sh_v4 is not None:
        touche_score, touche_used = sh_v4, "v4"
    elif _touche_v4_enabled() and sh_backup is not None:
        touche_score, touche_used = sh_backup, "backup"
    else:
        touche_score, touche_used = touche_base, "base"
    if sh_v4 is not None or sh_backup is not None:
        tf_warnings.append(
            "touche_observe:"
            f"base={touche_base:.1f}:"
            f"backup={'none' if sh_backup is None else f'{sh_backup:.1f}'}:"
            f"v4={'none' if sh_v4 is None else f'{sh_v4:.1f}'}:used={touche_used}"
        )
    raw = {"touche": touche_score}
    # news ABSTAIN (2026-07-13, gölge-önce): kanıt boşluğu HER ZAMAN gözlem
    # satırı yazar; flag açıkken kanıtsız news oy kullanmaz (düşer, redistribute).
    news_score = _news(snap, symbol)
    news_gap = _news_evidence_gap(snap, symbol)
    if news_gap:
        tf_warnings.append(
            f"news_abstain_observe:reason={news_gap}:"
            f"applied={'yes' if news_score is None else 'no'}"
        )
    if news_score is not None:
        raw["news"] = news_score
    # F2-3 — fundamental/sentinel katman verisi yoksa (drop_unavailable_layers
    # açıkken) modül düşer; ağırlığı redistribute edilir (quantum deseniyle aynı).
    # Flag kapalıyken katmanlar hep dolu → bu iki modül her zaman girer (bayt-aynı).
    # M3 — fundamental_v2 (Kripto Momentum hariç): flag açıkken v2 canlı, v1
    # gözlem; kapalıyken v1 canlı (bayt-aynı), v2 gözlem. İki varyant her zaman
    # warning satırında yan yana — owner aktivasyon kanıtını buradan izler.
    fund_v1 = _fundamental(regime)
    fund_v2 = _fundamental_v2(regime)
    fund_v3 = _fundamental_v3(regime)
    fund_v4 = _fundamental_v4()
    # Kademe: v4 (değişim-bazlı makro, GÖLGE — 5y tezgâh ADAY B) > v3 > v2 > v1.
    # Hangisi açıksa o canlı; v4 açık ama üretemiyorsa (arşiv yok) alt kademeye
    # düşer. Tüm flag'ler kapalıyken davranış v2/v1 seçimiyle bayt-aynı.
    if _fundamental_v4_enabled() and fund_v4 is not None:
        fundamental, fund_used = fund_v4, "v4"
    elif _fundamental_v3_enabled():
        fundamental, fund_used = fund_v3, "v3"
    elif _fundamental_v2_enabled():
        fundamental, fund_used = fund_v2, "v2"
    else:
        fundamental, fund_used = fund_v1, "v1"
    if fund_v1 is not None or fund_v2 is not None:
        tf_warnings.append(
            "fundamental_v2_observe:"
            f"v1={'none' if fund_v1 is None else f'{fund_v1:.1f}'}:"
            f"v2={'none' if fund_v2 is None else f'{fund_v2:.1f}'}"
        )
    if fund_v3 is not None or fund_v2 is not None:
        tf_warnings.append(
            "fundamental_v3_observe:"
            f"v3={'none' if fund_v3 is None else f'{fund_v3:.1f}'}:"
            f"used={fund_used}"
        )
    if fund_v4 is not None:
        tf_warnings.append(
            "fundamental_v4_observe:"
            f"v4={fund_v4:.1f}:"
            f"v3={'none' if fund_v3 is None else f'{fund_v3:.1f}'}:used={fund_used}"
        )
    if fundamental is not None:
        raw["fundamental"] = fundamental
    else:
        tf_warnings.append(f"fundamental_dropped:no_macro_layers:{symbol}:{timeframe}")
    # M4 — sentinel_v2 (çok-girdili stres kompoziti): flag açıkken v2 canlı,
    # kapalıyken v1 (yalnız VIX) canlı — bayt-aynı. İki varyant her zaman
    # warning satırında yan yana (owner aktivasyon kanıtını buradan izler).
    sent_v1 = _sentinel(regime)
    sent_v2 = _sentinel_v2(regime, snap, symbol, timeframe)
    sentinel = sent_v2 if _sentinel_v2_enabled() else sent_v1
    if sent_v1 is not None or sent_v2 is not None:
        tf_warnings.append(
            "sentinel_v2_observe:"
            f"v1={'none' if sent_v1 is None else f'{sent_v1:.1f}'}:"
            f"v2={'none' if sent_v2 is None else f'{sent_v2:.1f}'}"
        )
    if sentinel is not None:
        raw["sentinel"] = sentinel
    else:
        tf_warnings.append(f"sentinel_dropped:no_risk_appetite_layer:{symbol}:{timeframe}")
    # Rotasyon UNAVAILABLE ise quantum modülü düşer; ağırlığı _redistribute
    # ile diğer modüllere dağıtılır (mock skor karar zincirine girmez).
    # quantum_v2 — sembol-başı kesitsel göreceli-güç (para akışı): flag açıkken v2
    # canlı, kapalıyken v1 makro tilt (bayt-aynı). v2 kanıtsız (veri yetersiz)
    # sembolde v1'e düşer. İki varyant her zaman gözlem satırında yan yana.
    if snap.rotation.status != "UNAVAILABLE":
        quantum_v1 = _quantum(snap)
        quantum_v2 = _quantum_v2(snap, symbol)
        use_q2 = _quantum_v2_enabled() and quantum_v2 is not None
        q_score = quantum_v2 if use_q2 else quantum_v1
        # Rejim-kapısı (2026-07-13, gölge-önce): göreceli-momentum yalnız trendli
        # havada konuşur (kanıt: challenger karnesi — NEUTRAL'da TERS). İzinsiz
        # rejimde gözlem satırı HER ZAMAN yazılır (kanıt birikir); kapı yalnız
        # flag açıkken uygulanır (kapalıyken karar davranışı bayt-aynı).
        gate_allowed = regime.label in _quantum_gate_allowed_regimes()
        gate_applied = _quantum_regime_gate_enabled() and not gate_allowed
        if not gate_allowed:
            tf_warnings.append(
                "quantum_gate_observe:"
                f"regime={regime.label}:score={q_score:.1f}:"
                f"applied={'yes' if gate_applied else 'no'}"
            )
        if gate_applied:
            # Modül düşer → ağırlığı _redistribute ile diğerlerine dağılır
            # (rotation UNAVAILABLE ile aynı desen; nötr-50 uydurulmaz).
            tf_warnings.append(f"quantum_dropped:regime_gate:{regime.label}:{symbol}")
        else:
            raw["quantum"] = q_score
            if quantum_v2 is not None:
                tf_warnings.append(
                    "quantum_v2_observe:"
                    f"v1={quantum_v1:.1f}:v2={quantum_v2:.1f}:used={'v2' if use_q2 else 'v1'}"
                )
    # Kaynak-politikası (2026-07-13, gölge-önce): source_registry'de kısıtlı
    # etiketli (analytics_only/simulation_only) kaynakların beslediği modüller.
    # Gözlem satırı HER ZAMAN (kanıt birikir); düşürme yalnız flag açıkken.
    restricted = {m: u for m, u in _restricted_modules().items() if m in raw}
    if restricted:
        usage_applied = _enforce_decision_usage_enabled()
        tf_warnings.append(
            "decision_usage_observe:"
            + ":".join(f"{m}={u}" for m, u in sorted(restricted.items()))
            + f":applied={'yes' if usage_applied else 'no'}"
        )
        if usage_applied:
            for m, u in sorted(restricted.items()):
                raw.pop(m, None)
                tf_warnings.append(f"decision_usage_dropped:{m}:{u}")
    weights_cfg = load_active_weights()
    base = weights_cfg["regimes"].get(regime.label, weights_cfg["regimes"]["NEUTRAL"])
    available = set(raw.keys())
    # Kapsama (2026-07-13, gölge-önce): _redistribute eksik modülün ağırlığını
    # kalanlara TAM dağıtır — kapsama bunun dürüstlük sayacı: mevcut modüllerin
    # TABAN ağırlık toplamı. Eksik modül varken her hücrede gözlem satırı;
    # eşik (min_module_coverage>0) altında yön nötre zorlanır (aşağıda).
    base_total = sum(float(v) for v in base.values()) or 1.0
    coverage = sum(float(base.get(k, 0.0)) for k in available) / base_total
    min_cov = _min_module_coverage()
    coverage_forced_neutral = bool(min_cov > 0.0 and coverage < min_cov)
    if coverage < 1.0 - 1e-9:
        tf_warnings.append(
            f"coverage_observe:cov={coverage:.2f}:min={min_cov:.2f}:"
            f"applied={'yes' if coverage_forced_neutral else 'no'}"
        )
    w = _redistribute(base, available)
    modules = []
    weighted = 0.0
    for name in MODULE_ORDER:
        if name not in raw:
            continue
        s = raw[name]
        wt = w.get(name, 0.0)
        c = s * wt
        weighted += c
        modules.append(ModuleScore(name=name, score=round(s, 2), weight=round(wt, 4), contribution=round(c, 3)))
    dominant_legacy = max(modules, key=lambda m: m.contribution).name if modules else ""
    # Yön-katkılı dominant (nötr-50 merkezli): |skor−50|×ağırlık — bearish modül
    # de dominant olabilir (legacy `score×weight` bunu yapısal olarak engelliyordu).
    dominant_dir = (
        max(modules, key=lambda m: abs((m.score - 50.0) * m.weight)).name
        if modules else ""
    )
    if dominant_dir and dominant_dir != dominant_legacy:
        # İki hesap ayrıştığında kanıt satırı (flag'siz gözlem; owner aktivasyon
        # kararını buradan izler). Aynıysa satır yazılmaz (gürültü yok).
        tf_warnings.append(
            f"dominant_observe:legacy={dominant_legacy}:directional={dominant_dir}"
        )
    dominant = dominant_dir if _dominant_directional_enabled() else dominant_legacy
    final = max(0.0, min(100.0, weighted))
    # Yön etiketi trade aksiyon eşikleriyle aynı banttan (tek kaynak) okunur.
    cons_th = load_thresholds().get("consensus", {})
    bullish_min = float(cons_th.get("bullish_min", 55.0))
    bearish_max = float(cons_th.get("bearish_max", 45.0))
    # Confluence (bugfix 2026-07-02, owner onayı): en az 3 modül SİNYALİN KENDİ
    # yönünde hemfikir olmalı. Eski kod yön ayrımı yapmıyordu (above>=3 OR
    # below>=3) — 3 modül işlemin TERSİNE hizalıyken bile "uyumlu" sayıp boyut
    # yarılamasını atlıyordu. Nötr sinyalde taraf yok → False (işlem de yok).
    # Modül eşikleri de artık aksiyon eşikleriyle aynı config bandından okunur
    # (eskiden 55/45 sabitti — owner eşiği değiştirince sessizce ayrışırdı).
    above = sum(1 for m in modules if m.score >= bullish_min)
    below = sum(1 for m in modules if m.score <= bearish_max)
    if final >= bullish_min:
        confluence = above >= 3
    elif final <= bearish_max:
        confluence = below >= 3
    else:
        confluence = False
    direction = _direction(final, bullish_min, bearish_max)
    if coverage_forced_neutral and direction != "neutral":
        # Kapsama eşiği altı: kanıt tabanı incelmiş — yön kararı verilmez
        # (skor/modüller raporda aynen kalır; yalnız işlem-açıcı yön kısıtlanır).
        tf_warnings.append(f"coverage_gate:forced_neutral:was={direction}")
        direction = "neutral"
        confluence = False
    return ConsensusResult(
        symbol=symbol,
        score=round(final, 1),
        direction=direction,
        modules=modules,
        confluence_aligned=confluence,
        dominant_module=dominant,
        timeframe=timeframe,
        warnings=tf_warnings,
    )
