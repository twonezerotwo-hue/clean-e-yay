"""D — dinamik korelasyon vetosu (P1, shadow-first, YALNIZ ENGELLER).

Owner içgörüsü + 5y çok-rejim backtest (2026-07-10): varlıklar tek başına değil,
akrabalarıyla okunmalı. Ama "aynı yön onayı" (C varyantı) İYİ işlemleri eledi;
kazanan okuma **çelişki vetosu**: aday sinyalin akrabası — o anki güçlü korelasyonlu
varlık — KENDİ sinyaliyle ilişkiyi çürütüyorsa işlem AÇILMAZ. Backtest: edge
+0.171 → +0.235, elenen işlemler −0.511 (çöp eliyor), 5/5 yıl taban çizgisini geçti.

Akraba OTOMATİK seçilir (owner kararı 2026-07-10): sistem o anki 90g korelasyondan
EN GÜÇLÜ akrabayı kendi bulur — owner'ın varsayımları veriyle çürüse bile (BTC-gümüş
+0.12 zayıfmış) otomatik düzeltir; kayan korelasyonlara dayanıklı, bakım gerektirmez.

MİMARİ KURALLAR (self_conflict/concentration deseniyle birebir):
- Config-flag `correlation_veto.enabled` (thresholds YAML, default FALSE → shadow:
  her kararda correlation_veto_report hesaplanır, davranış değişmez).
- Yalnız ENGELLER (veto → size 0); boyut ARTIRMAZ, RiskGate/DQS/halt bypass etmez.
- Saf/defansif: veri yok / zayıf korelasyon / nötr akraba → veto YOK (uydurma yok).
- Ağ çağrısı YOK — correlation.price_return_series (1d OHLCV disk cache) + partner
  yön okuması _momentum_score (üretim touche çekirdeği; formül drift yok).
"""
from __future__ import annotations

from packages.data.providers.ohlcv import cache as ohlcv_cache
from packages.data.providers.technical import indicators as ind
from packages.data.providers.technical.timeframe import (
    _EMA_PERIODS,
    _clamp,
    _ema_stack,
    _momentum_score,
)
from packages.risk import correlation

_DIR_EPS = 0.05        # |partner_lean| bu eşiğin altında → akraba nötr (veto yok)
_MIN_WARMUP = 60       # partner _momentum_score için yeterli 1d bar


def partner_lean(symbol: str) -> float | None:
    """Akrabanın yön okuması ∈ [−1,1] — üretim `_momentum_score`'undan (touche
    çekirdeği; drift yok). 1d disk cache'inden okur (ağ yok). Yetersiz → None."""
    cached = ohlcv_cache.load(symbol, "1d")
    if cached is None:
        return None
    bars = [b for b in sorted(cached.bars, key=lambda b: b.ts)
            if getattr(b, "verified", True) and b.close and b.close > 0]
    if len(bars) < _MIN_WARMUP:
        return None
    closes = [b.close for b in bars]
    rsi_v = ind.rsi(closes)
    macd_t = ind.macd(closes)
    atr_v = ind.atr(bars)
    macd_atr = macd_t[2] / atr_v if (macd_t is not None and atr_v and atr_v > 0) else None
    stack = _ema_stack([ind.ema(closes, p) for p in _EMA_PERIODS])
    ms = _momentum_score(rsi_v, macd_atr, stack)
    return None if ms is None else _clamp((ms - 50.0) / 50.0, -1.0, 1.0)


def nearest_relative(
    candidate: str, universe: list[str], *, min_abs_rho: float, window_days: int,
) -> tuple[str | None, float]:
    """Adayın EN GÜÇLÜ akrabası (o anki |rho| en yüksek) + rho. price_return_series
    (1d cache, ağ yok) ile 90g pencere. |rho| < min → (None, 0) (güçlü akraba yok)."""
    others = [s for s in universe if s != candidate]
    if not others:
        return None, 0.0
    series = correlation.price_return_series([candidate, *others], window_days=window_days)
    best_sym, best_rho = None, 0.0
    for s in others:
        rho, _n = correlation._pair_price_rho(candidate, s, series)
        if rho is not None and abs(rho) > abs(best_rho):
            best_sym, best_rho = s, rho
    if best_sym is None or abs(best_rho) < min_abs_rho:
        return None, round(best_rho, 3)
    return best_sym, round(best_rho, 3)


def assess(candidate_symbol: str, side: str, universe: list[str], cfg: dict) -> dict:
    """Aday için korelasyon vetosunu değerlendir → rapor (her kararda hesaplanır).

    Boş dict = değerlendirilecek güçlü akraba yok (veto konusu değil). Aksi halde:
    en güçlü akraba bulunur, KENDİ yön okuması ilişkinin beklediğiyle çelişirse
    `vetoed=True`. `enabled` kapalıyken rapor yine dolu (shadow); yalnız açıkken
    engel. Saf/defansif — asla raise etmez (engine try/except zaten sarar)."""
    enabled = bool(cfg.get("enabled", False))
    min_rho = float(cfg.get("min_abs_rho", 0.5))
    window = int(cfg.get("corr_window_days", 90))
    cand_sign = 1.0 if side == "long" else -1.0

    partner, rho = nearest_relative(
        candidate_symbol, universe, min_abs_rho=min_rho, window_days=window,
    )
    if partner is None:
        return {}  # güçlü akraba yok → veto konusu değil (gözlem gürültüsü yaratma)

    p_lean = partner_lean(partner)
    if p_lean is None or abs(p_lean) < _DIR_EPS:
        return {  # akraba nötr/okunamıyor → çelişki tespit edilemez, veto yok
            "active": enabled, "vetoed": False, "partner": partner, "rho": rho,
            "partner_lean": None if p_lean is None else round(p_lean, 3),
            "reason": "akraba yön nötr/okunamıyor",
        }

    # İlişkiye göre akrabadan BEKLENEN yön: pozitif korelasyon → aynı, negatif → ters.
    expected_sign = cand_sign if rho > 0 else -cand_sign
    partner_sign = 1.0 if p_lean > 0 else -1.0
    conflict = partner_sign != expected_sign
    return {
        "active": enabled,
        "vetoed": bool(conflict),
        "partner": partner,
        "rho": rho,
        "partner_lean": round(p_lean, 3),
        "expected_partner_sign": expected_sign,
        "reason": (
            f"{partner} (rho={rho:+.2f}) ilişkiyle çelişiyor: akraba "
            f"{'yukarı' if partner_sign > 0 else 'aşağı'} okuyor, beklenen "
            f"{'yukarı' if expected_sign > 0 else 'aşağı'}"
            if conflict else f"{partner} (rho={rho:+.2f}) ilişkiyle uyumlu"
        ),
    }


__all__ = ["assess", "nearest_relative", "partner_lean"]
