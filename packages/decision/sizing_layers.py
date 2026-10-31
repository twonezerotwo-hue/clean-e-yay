"""Boyut katmanları — inanç-boyu + oynaklık-paritesi + son-edge freni (YALNIZ KISAR).

5 yıllık backtest bulguları (2026-07-10, çok-rejim, gerçek veri):

- **İnanç boyu:** consensus sinyal gücü (|score−50|) dilimlere ayrıldığında ileri-getiri
  KUSURSUZ merdiven (en zayıf %20 edge −0.210, en güçlü %20 +0.266). Sinyal gücüne
  oransal boyut → eşit-boya karşı edge +0.085 → +0.159 (~2 kat).
- **Oynaklık paritesi:** boyut ATR/oynaklığa ters orantılandığında (oynak varlığa az
  para) 5y maksimum düşüş −293 → −171 (yarıya yakın), getiri korunuyor.

MİMARİ KURALLAR:
- Üç katman her kararda hesaplanır ve çarpılır; rapor kararla birlikte taşınır.
- **NO-BOOST:** her faktör [floor, 1.0] arasına clamp'lenir — ASLA boyut artırmaz.
- Saf fonksiyon, yan etki yok; yetersiz girdi → faktör 1.0 (kısma yok, uydurma yok).
- RiskGate/DQS/halt'ı bypass ETMEZ — karar zincirinde en son boyut katmanı.
"""
from __future__ import annotations

_NEUTRAL_SCORE = 50.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def conviction_factor(
    score: float, *, threshold_dist: float, full_strength: float,
    min_factor: float,
) -> float:
    """Sinyal gücüne (|score−50|) oransal boyut faktörü ∈ [min_factor, 1.0].

    Eşiğe yakın (zayıf) sinyal → min_factor; `full_strength` gücünde → 1.0; arası
    doğrusal. Karar motoruna gelen aday zaten eşik-üstü (hold elenmiş); bu katman
    eşik-üstü sinyalleri güçlerine göre AYIRIR. Asla >1.0 (no-boost)."""
    strength = abs(score - _NEUTRAL_SCORE)
    span = full_strength - threshold_dist
    if span <= 0:
        return 1.0
    ratio = (strength - threshold_dist) / span   # 0 (eşikte) .. 1 (tam güç)
    return _clamp(min_factor + (1.0 - min_factor) * ratio, min_factor, 1.0)


def brake_factor(recent_edge: float | None, *, threshold: float, factor: float) -> float:
    """'Bugün oynama' freni — sistemin son dönem GERÇEKLEŞEN edge'i (ort R) eşiğin
    altındaysa boyut çarpanı `factor` (<1.0), değilse 1.0. Backtest: kötü dönemde
    yarı-boy maksimum düşüşü küçültür (−293→−213). Kanıt yok (None) → 1.0 (fren yok,
    uydurma yok). Yalnız KISAR — factor asla >1.0 varsayılmaz (config disiplini)."""
    if recent_edge is None:
        return 1.0
    return factor if recent_edge < threshold else 1.0


def vol_parity_factor(realized_vol: float, *, ref_vol: float, floor: float) -> float:
    """Oynaklığa ters orantılı boyut faktörü ∈ [floor, 1.0].

    Varlığın oynaklığı referansı aşarsa (daha oynak) boyut kısılır (ref/realized);
    referans altındaysa 1.0 (büyütme YOK — no-boost). Böylece her işlemin "1R"i
    yaklaşık eşit acı verir; oynak varlık portföyü tek başına sürüklemez."""
    if realized_vol is None or realized_vol <= 0 or ref_vol <= 0:
        return 1.0
    return _clamp(ref_vol / realized_vol, floor, 1.0)


def evaluate(
    *, score: float, realized_vol: float | None, threshold_dist: float,
    conviction_cfg: dict, vol_parity_cfg: dict,
    recent_edge: float | None = None, brake_cfg: dict | None = None,
) -> dict:
    """Katmanları hesapla → rapor (faktörler + uygulanan birleşik çarpan).

    `applied` = üç faktörün çarpımı, [0, 1] aralığında. Saf/defansif — raise etmez."""
    brake_cfg = brake_cfg or {}

    conv_f = conviction_factor(
        score,
        threshold_dist=threshold_dist,
        full_strength=float(conviction_cfg.get("full_strength", 25.0)),
        min_factor=float(conviction_cfg.get("min_factor", 0.5)),
    )
    vp_f = vol_parity_factor(
        realized_vol if realized_vol is not None else 0.0,
        ref_vol=float(vol_parity_cfg.get("ref_vol", 0.03)),
        floor=float(vol_parity_cfg.get("floor", 0.3)),
    )
    brake_f = brake_factor(
        recent_edge,
        threshold=float(brake_cfg.get("threshold", 0.0)),
        factor=float(brake_cfg.get("factor", 0.5)),
    )
    applied = _clamp(conv_f * vp_f * brake_f, 0.0, 1.0)   # no-boost güvencesi
    return {
        "conviction": {"factor": round(conv_f, 4),
                       "strength": round(abs(score - _NEUTRAL_SCORE), 2)},
        "vol_parity": {"factor": round(vp_f, 4), "realized_vol": realized_vol},
        "brake": {"factor": round(brake_f, 4), "recent_edge": recent_edge},
        "applied_factor": round(applied, 4),
    }


__all__ = ["brake_factor", "conviction_factor", "evaluate", "vol_parity_factor"]
