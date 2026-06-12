"""Offline türev fixture'ları — yalnızca test/dev (v2.7 D2).

DATA_POLICY: bu veriler `verified=False` damgalıdır ve **runtime'da asla**
kullanılmaz; yalnızca `TEST_USE_MOCK=true` / `DERIVATIVES_USE_FIXTURE=true`
path'inden gelir ve karar zincirine GİRMEZ (yalnızca dashboard bağlamı).
"""
from __future__ import annotations

from packages.data.providers.derivatives.binance import RawDerivatives

# Deterministik, makul ham değerler (gerçek piyasa değil — fixture).
_FIXTURES: dict[str, RawDerivatives] = {
    "BTCUSD": RawDerivatives(
        funding_rate=0.0006,        # hafif kalabalık long
        open_interest_usd=9_500_000_000.0,
        oi_change_pct=0.03,
    ),
    "ETHUSD": RawDerivatives(
        funding_rate=-0.0002,       # nötr
        open_interest_usd=4_200_000_000.0,
        oi_change_pct=-0.01,
    ),
}


def fetch(symbol: str) -> RawDerivatives | None:
    raw = _FIXTURES.get(symbol)
    return RawDerivatives(**vars(raw)) if raw is not None else None
