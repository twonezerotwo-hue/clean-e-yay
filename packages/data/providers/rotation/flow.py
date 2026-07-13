"""Sermaye akis skoru (capital_flow) — coklu-ufuk, hacim-onayli, kanit-agirlikli.

Rotasyon motorunun (engine.py) 5 zaafini kapatan yeni cekirdek. GOLGE: canli
`rotation.score`'a DOKUNMAZ (o hala engine.py'den gelir); bu modul yaninda
hesaplar, Faz 2 backtest'i agirliklari doldurur, kanit yeterince olunca owner
terfi eder.

Kapatilan 5 zaaf:
  1. Coklu ufuk (21/63/126g) — tek 30g yerine (kisa hafiza).
  2. Hacim onayi — hacimi GERCEK olan sembollerde (TLT/SP500/HYG/LQD) momentum
     hacim-trendiyle onaylanir; digerinde saf momentum (durust degrade —
     BTC/DXY'de hacim yok).
  3. Tum sinyaller nihai skora — gumus/petrol dahil (elle kova YOK).
  4. Kanit-agirlikli — her sinyalin agirligi 5yr backtest'ten (elle 1.5/x25 yok).
  5. Kredi spread'i (HYG/LQD) AYRI eksen — hisse sinifina gomulu degil.

Skor 0-100 (yuksek = risk-on). Pure; LOOK-AHEAD yok (cagiran son bara kadar veri
gecirir). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import statistics as _st

HORIZONS = (21, 63, 126)   # ~1a / 3a / 6a
VOL_WINDOW = 20
_MIN_HISTORY = max(HORIZONS) + 1
# Hacimi GERCEK olan semboller (digerinde hacim-onayi atlanir — durust degrade).
# Anahtarlar ROTASYON anahtari (engine.ROTATION_SYMBOLS): S&P 500 = "SPY".
VOLUME_RELIABLE = frozenset({"TLT", "SPY", "HYG", "LQD"})
_SIGNAL_CLAMP = 3.0        # tek sinyalin |vol-norm momentum| tavani (yumusak bound)

# Nihai skora giren 8 sinyal: 7 varlik-sinifi ana gostergesi + kredi ekseni.
# (HYG/LQD tekil momentumu DEGIL — kredi yalniz HYG/LQD ORANI ekseninden girer.)
SIGNAL_KEYS = ("BTC", "GLD", "XAG", "TLT", "SPY", "DXY", "OIL", "CREDIT")

# Faz 2 backtest DOLDURACAK. Simdilik yon-makul isaretler (risk-on=+, defansif=−;
# petrol/gumus 0 = "veri karar versin", kredi +). scale ile skor bandi ayarlanir.
DEFAULT_WEIGHTS: dict[str, float] = {
    "BTC": 1.0, "SPY": 1.0, "CREDIT": 1.0,        # risk-on
    "GLD": -1.0, "TLT": -1.0, "DXY": -1.0,        # defansif / guvenli liman
    "XAG": 0.0, "OIL": 0.0,                        # iki-yuzlu → backtest yerlestirir
}
DEFAULT_SCALE = 8.0
# Makro likidite momentum skoru band olcegi (macro_backtest ADAY B'de dogrulandi;
# clamp+/-3 ile skor bandi ~[12,88], merkez 50). Elle degil — backtest secti.
LIQUIDITY_MOM_SCALE = 12.5


def vol_norm_momentum(closes: list[float]) -> float | None:
    """Coklu-ufuk (%1a/3a/6a) getiri ortalamasi / realized-vol (oynaklik-adil).
    Yetersiz veri → None. `_SIGNAL_CLAMP`'e yumusak kirpik."""
    if len(closes) < _MIN_HISTORY:
        return None
    moms = [(closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100.0
            for n in HORIZONS if closes[-1 - n]]
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(len(closes) - VOL_WINDOW, len(closes)) if i > 0 and closes[i - 1]]
    if len(moms) < len(HORIZONS) or len(rets) < 3:
        return None
    vol = _st.pstdev(rets) * 100.0
    if vol <= 0:
        return None
    raw = (sum(moms) / len(moms)) / vol
    return max(-_SIGNAL_CLAMP, min(_SIGNAL_CLAMP, raw))


def volume_confirm(volumes: list[float] | None) -> float:
    """Son hacim / taban hacim → onay carpani [0.6, 1.4]. Yuksek hacim momentumu
    guclendirir, dusuk zayiflatir. Hacim yok/yetersiz → 1.0 (notr, degrade)."""
    vals = [v for v in (volumes or []) if v]
    if len(vals) < VOL_WINDOW + 1:
        return 1.0
    baseline = _st.mean(vals[-VOL_WINDOW:])
    if baseline <= 0:
        return 1.0
    recent = _st.mean(vals[-5:])
    return max(0.6, min(1.4, recent / baseline))


def asset_signal(symbol: str, closes: list[float], volumes: list[float] | None = None) -> float | None:
    """Bir varligin akis sinyali: vol-norm momentum; hacimi guvenilir sembolde
    hacim-trendiyle onayli. `symbol` = rotasyon anahtari (SPY/GLD/…) veya VALUE."""
    m = vol_norm_momentum(closes)
    if m is None:
        return None
    if symbol in VOLUME_RELIABLE:
        m *= volume_confirm(volumes)
    return m


def credit_signal(hyg_closes: list[float], lqd_closes: list[float]) -> float | None:
    """Kredi risk-istahi ekseni: HYG/LQD orani coklu-ufuk momentumu. Oran yukari
    (HY, IG'yi geciyor) = kredi risk-istahi guclu = risk-on."""
    n = min(len(hyg_closes), len(lqd_closes))
    if n < _MIN_HISTORY:
        return None
    ratio = [hy / ig for hy, ig in zip(hyg_closes[-n:], lqd_closes[-n:], strict=False) if ig]
    if len(ratio) < _MIN_HISTORY:
        return None
    return vol_norm_momentum(ratio)


def liquidity_momentum_score(
    dxy_closes: list[float], us10y_closes: list[float]
) -> float | None:
    """Makro likidite skoru — DEGISIM-bazli (0-100, yuksek = risk-on/gevseme).

    Mevcut Likidite formulu mutlak seviyeye capaliydi (5y'da 1118/1118 gun >=55 —
    hic bearish olamiyordu; dis denetim "asiri iyimser merkez" bulgusu). Bu
    surum DXY ve 10y faizin coklu-ufuk (1a/3a/6a) vol-norm momentumundan gelir:
    ikisi de YUKSELIYORSA para sikilasiyor = risk-off (skor<50). Merkez yapisal
    olarak 50. 5y tezgah (macro_backtest ADAY B): tum hedeflerde genel pozitif,
    SPY 4/5 yil tutarli. Yetersiz veri (her iki eksen de gerekli) -> None.

    Esit-agirlik eksen (katsayi UYDURMA yok); flow.vol_norm_momentum REUSE.
    `scale` backtest'te dogrulanan band (12.5); iki eksen ortalamasina biner."""
    md = vol_norm_momentum(dxy_closes)
    mr = vol_norm_momentum(us10y_closes)
    if md is None or mr is None:
        return None
    return max(0.0, min(100.0, 50.0 + LIQUIDITY_MOM_SCALE * (-md - mr) / 2.0))


def flow_score(
    signals: dict[str, float],
    weights: dict[str, float] | None = None,
    scale: float = DEFAULT_SCALE,
) -> float | None:
    """`signals`: SIGNAL_KEYS → deger. Skor = 50 + scale × agirlikli-ortalama
    (Σ w·s / Σ|w|; bounded). Aktif (agirligi 0-disi + sinyali olan) yoksa None.
    Kanit-agirlikli: `weights` backtest'ten (None → DEFAULT_WEIGHTS)."""
    w = DEFAULT_WEIGHTS if weights is None else weights
    terms = [(w.get(k, 0.0), signals[k]) for k in signals if w.get(k, 0.0) != 0.0]
    tw = sum(abs(wi) for wi, _ in terms)
    if tw <= 0.0:
        return None
    wavg = sum(wi * si for wi, si in terms) / tw
    return max(0.0, min(100.0, 50.0 + scale * wavg))


# Rotasyon anahtari → asset_signal cagrisinda kullanilacak sinyal anahtari.
# (engine.ROTATION_SYMBOLS ile ayni anahtar kumesi; CREDIT ayri turetilir.)
def build_signals(
    closes_by_key: dict[str, list[float]],
    volumes_by_key: dict[str, list[float] | None] | None = None,
) -> dict[str, float]:
    """Ham seri sozlugunden (rotasyon anahtari → kapanislar) SIGNAL_KEYS sozlugu.
    Yetersiz sinyal atlanir (uydurma yok). CREDIT = HYG/LQD orani."""
    vols = volumes_by_key or {}
    out: dict[str, float] = {}
    for key in ("BTC", "GLD", "XAG", "TLT", "SPY", "DXY", "OIL"):
        c = closes_by_key.get(key)
        if not c:
            continue
        s = asset_signal(key, c, vols.get(key))
        if s is not None:
            out[key] = s
    hyg, lqd = closes_by_key.get("HYG"), closes_by_key.get("LQD")
    if hyg and lqd:
        cs = credit_signal(hyg, lqd)
        if cs is not None:
            out["CREDIT"] = cs
    return out


__all__ = [
    "DEFAULT_SCALE",
    "DEFAULT_WEIGHTS",
    "SIGNAL_KEYS",
    "asset_signal",
    "build_signals",
    "credit_signal",
    "flow_score",
    "liquidity_momentum_score",
    "vol_norm_momentum",
    "volume_confirm",
]
