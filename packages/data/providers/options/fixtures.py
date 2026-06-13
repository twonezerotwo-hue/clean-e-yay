"""Offline options fixture'ları — yalnızca test/dev (v2.7 D3).

DATA_POLICY: bu veriler `verified=False` damgalıdır ve **runtime'da asla**
kullanılmaz; yalnızca `TEST_USE_MOCK=true` / `OPTIONS_USE_FIXTURE=true`
path'inden gelir ve karar zincirine GİRMEZ (yalnızca dashboard bağlamı).

Deterministik, makul bir chain (gerçek piyasa değil — fixture): 3 vade
(front / next / long) × strike bandı × call/put. Hafif put skew (OTM put IV >
OTM call IV) ve hafif backwardation (ön vade IV > uzun vade) içerir.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.data.providers.options.deribit import RawOptionQuote, RawOptionsChain

# (underlying, [(expiry_label, expiry_ts, atm_iv, skew_pt, term_pt)])
# skew_pt: OTM put'a eklenen vol-puan (pozitif = put pahalı = put skew).
# term_pt: bu vadenin ATM IV'sine eklenen vol-puan (front 0; uzun vade negatif
#          = backwardation).
_SPEC: dict[str, dict] = {
    "BTCUSD": {
        "underlying": 60_000.0,
        "atm_iv": 0.55,
        "skew_pt": 0.04,
        "expiries": [
            ("27JUN25", datetime(2025, 6, 27, 8, tzinfo=UTC), 0.0),
            ("25JUL25", datetime(2025, 7, 25, 8, tzinfo=UTC), -0.005),
            ("26SEP25", datetime(2025, 9, 26, 8, tzinfo=UTC), -0.01),
        ],
        "strikes": [0.90, 1.00, 1.10],
        "oi": 1_200.0,
    },
    "ETHUSD": {
        "underlying": 3_000.0,
        "atm_iv": 0.62,
        "skew_pt": 0.03,
        "expiries": [
            ("27JUN25", datetime(2025, 6, 27, 8, tzinfo=UTC), 0.0),
            ("25JUL25", datetime(2025, 7, 25, 8, tzinfo=UTC), -0.003),
            ("26SEP25", datetime(2025, 9, 26, 8, tzinfo=UTC), -0.008),
        ],
        "strikes": [0.90, 1.00, 1.10],
        "oi": 5_000.0,
    },
}


def _build(spec: dict) -> RawOptionsChain:
    underlying: float = spec["underlying"]
    quotes: list[RawOptionQuote] = []
    for label, ts, term_pt in spec["expiries"]:
        base_iv = spec["atm_iv"] + term_pt
        for m in spec["strikes"]:
            strike = round(underlying * m, 2)
            # Put skew: OTM put'lar (m<1) skew_pt kadar daha pahalı; call'lar düz.
            put_iv = base_iv + (spec["skew_pt"] if m < 1.0 else 0.0)
            call_iv = base_iv
            quotes.append(
                RawOptionQuote(
                    expiry_ts=ts,
                    strike=strike,
                    option_type="put",
                    mark_iv=round(put_iv, 4),
                    open_interest=spec["oi"],
                    expiry_label=label,
                )
            )
            quotes.append(
                RawOptionQuote(
                    expiry_ts=ts,
                    strike=strike,
                    option_type="call",
                    mark_iv=round(call_iv, 4),
                    open_interest=spec["oi"] * 0.8,
                    expiry_label=label,
                )
            )
    return RawOptionsChain(underlying_price=underlying, quotes=quotes)


def fetch(symbol: str) -> RawOptionsChain | None:
    spec = _SPEC.get(symbol)
    return _build(spec) if spec is not None else None
