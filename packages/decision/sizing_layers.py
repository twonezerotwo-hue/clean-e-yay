"""Boyut katmanları — inanç-boyu + oynaklık-paritesi (P1, shadow-first, YALNIZ KISAR).

5 yıllık backtest bulguları (2026-07-10, çok-rejim, gerçek veri):

- **İnanç boyu:** consensus sinyal gücü (|score−50|) dilimlere ayrıldığında ileri-getiri
  KUSURSUZ merdiven (en zayıf %20 edge −0.210, en güçlü %20 +0.266). Sinyal gücüne
  oransal boyut → eşit-boya karşı edge +0.085 → +0.159 (~2 kat).
- **Oynaklık paritesi:** boyut ATR/oynaklığa ters orantılandığında (oynak varlığa az
  para) 5y maksimum düşüş −293 → −171 (yarıya yakın), getiri korunuyor.

MİMARİ KURALLAR (self_conflict/concentration/regime_brake deseniyle birebir):
- Config-flag (`sizing_layers.*.enabled`, thresholds YAML, default FALSE) — env flag
  YOK. Kapalıyken faktör 1.0 → boyut BAYT-AYNI (shadow-first: rapor her kararda
  hesaplanır, davranış değişmez; owner kanıtı panelden izler).
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
) -> dict:
    """İki katmanı da hesapla → rapor (faktörler + uygulanan birleşik çarpan).

    Her katman config-flag'iyle bağımsız; kapalı olan faktör 1.0 (etkisiz). `applied`
    = kapalıyken 1.0 (shadow: rapor dolu, boyut değişmez). Saf/defansif — raise etmez."""
    conv_on = bool(conviction_cfg.get("enabled", False))
    vp_on = bool(vol_parity_cfg.get("enabled", False))

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
    applied = 1.0
    if conv_on:
        applied *= conv_f
    if vp_on:
        applied *= vp_f
    applied = _clamp(applied, 0.0, 1.0)   # no-boost güvencesi
    return {
        "conviction": {"enabled": conv_on, "factor": round(conv_f, 4),
                       "strength": round(abs(score - _NEUTRAL_SCORE), 2)},
        "vol_parity": {"enabled": vp_on, "factor": round(vp_f, 4),
                       "realized_vol": realized_vol},
        "applied_factor": round(applied, 4),
    }


__all__ = ["conviction_factor", "evaluate", "vol_parity_factor"]
