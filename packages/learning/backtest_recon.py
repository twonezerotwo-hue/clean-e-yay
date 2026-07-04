"""B-1 — Geçmiş çok-modül yeniden-kurma + sadakat (fidelity) harness'i.

Amaç (owner kararı 2026-07-04): cat 6/7 (quantum + konsensüs ağırlığı) canlı
veri birikmesini haftalarca beklemek yerine, GERÇEK 1-2 yıllık fiyat/makro
serilerinden modül skorlarını geçmişe dönük yeniden kurup rejim-çeşitli kanıt
üretmenin ÖNKOŞULU: "yeniden-kurma canlı sistemle bire bir mi?" sorusunu
kanıtlamak.

TASARIM (pazarlıksız):
- Yeniden-kurma CANLI fonksiyonların KENDİSİNİ kullanır (kopya yok → drift yok):
  `technical.compute_snapshot` (touche), `rotation.compute` (quantum),
  `regime.classify` + `consensus._fundamental_v2/_sentinel` (makro modüller).
- LOOK-AHEAD YOK: her indekste yalnız `bars[: i + 1]` görülür (o ana kadar
  kapanmış barlar). Gelecek bar karara sızmaz.
- news modülü geçmişe kurulamaz (geçmiş sentiment saklanmıyor) → NÖTR 50 +
  `news_reconstructed=False` damgası. DATA_POLICY: uydurma veri yok.
- SALT-ÖLÇÜM / İZOLE: `verified` canlı outcome defterine ASLA yazmaz; yalnız
  `data/runtime/backtest_recon.json` fidelity artifact'ı üretir. Ağırlık/
  kalibrasyon/paper state'e temas etmez. Flag `BACKTEST_RECON_ENABLED` (env,
  DEFAULT OFF) → learning worker adımı tam no-op.
- Fidelity kanıtı: son indekste yeniden-kurulan quantum, BAĞIMSIZ canlı yol
  `rotation.get_rotation()` ile kıyaslanır (aynı formül, ayrı çağrı yolu);
  |delta| eşik altındaysa FAITHFUL. Rejim/fundamental/sentinel deterministik
  türevlerdir, aynı artifact'ta gözlem için taşınır. Rejim-çeşitli outcome
  ÜRETİMİ (B-2) ancak bu kapı FAITHFUL derse anlamlıdır.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from packages.consensus.engine import _fundamental_v2, _sentinel
from packages.data.providers import rotation as rotation_provider
from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
from packages.data.providers.rotation.engine import compute as rotation_compute
from packages.data.providers.technical import compute_snapshot
from packages.regime.classifier import classify

_ENV_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_OUT = "data/runtime/backtest_recon.json"
# Rejim makro girdileri (classifier _liquidity/_appetite katmanları okur).
_MACRO_SYMBOLS = ("DXY", "US10Y", "US02Y", "CPI", "VIX")
# Quantum için minimum seri (rotation.compute 32 bar ister); +BTC touche.
_MIN_BARS = 32
# Fidelity eşiği: yeniden-kurulan quantum ile canlı get_rotation farkı bu
# puanın altındaysa FAITHFUL (aynı formül; ufak fark yalnız bar-tazeliği).
_FIDELITY_TOL = 1.0


def enabled() -> bool:
    return os.environ.get("BACKTEST_RECON_ENABLED", "").lower() in _ENV_TRUE


def _out_path() -> Path:
    return Path(os.environ.get("BACKTEST_RECON_PATH", _DEFAULT_OUT))


@dataclass
class ReconScores:
    """Bir geçmiş indeksinde yeniden-kurulan modül skorları (salt-gözlem)."""

    index: int
    as_of: str | None
    regime_label: str | None
    quantum: float | None
    fundamental_v2: float | None
    sentinel: float | None
    news_reconstructed: bool = False
    dropped_layers: list[str] = field(default_factory=list)
    error: str | None = None


def _rotation_shim(closes_upto: dict[str, list[float]]):
    """`rotation.compute` sonucunu classifier'ın okuduğu arayüze (status/score/
    direction/evidence) uyarlar. RRotationResult.available → status."""
    res = rotation_compute(closes_upto)
    status = "OK" if res.available else "UNAVAILABLE"
    return SimpleNamespace(
        status=status,
        score=res.score,
        direction=res.direction,
        evidence=list(res.evidence),
    )


def reconstruct_at(
    bars_by_symbol: dict[str, list],
    macro_by_symbol: dict[str, list],
    index: int,
) -> ReconScores:
    """`index`'e kadar kapanmış barlarla modül skorlarını yeniden kurar.

    `bars_by_symbol`: rotasyon+BTC OHLCV barları (OHLCVBar listesi).
    `macro_by_symbol`: makro seri barları (DXY/US10Y/US02Y/CPI/VIX).
    LOOK-AHEAD YOK: her seri `[: index + 1]` dilimlenir."""
    btc_bars = bars_by_symbol.get("BTCUSD") or []
    if index < 0 or index >= len(btc_bars):
        return ReconScores(index, None, None, None, None, None, error="index_out_of_range")
    if index + 1 < _MIN_BARS:
        return ReconScores(index, None, None, None, None, None, error="insufficient_bars")

    as_of_ts = btc_bars[index].ts
    as_of = str(as_of_ts)

    # 1) Quantum: rotasyon anahtarı → as_of TARİHİNE kadar kapanış serisi.
    #    Semboller farklı bar sayısına/başlangıcına sahip → indeks-hizalama
    #    yanlış tarihi alır; DATE-hizalama şart (canlı get_rotation full seri
    #    kullanır, son indekste bu ona birebir denk gelir).
    closes_upto: dict[str, list[float]] = {}
    for key, sym in ROTATION_SYMBOLS.items():
        seq = bars_by_symbol.get(sym) or []
        upto = [b.close for b in seq if b.ts <= as_of_ts]
        if upto:
            closes_upto[key] = upto
    rot_shim = _rotation_shim(closes_upto)

    # 2) BTC 1d touche (kripto rejim katmanı) — canlı builder, bars dilimi.
    btc_tech = compute_snapshot("BTCUSD", "1d", btc_bars[: index + 1])

    # 3) Makro fiyatlar: her makro serinin o indekse kadarki SON kapanışı
    #    (as-of; gelecek yok). Bar sayısı seriye göre değişebildiğinden yaş
    #    hizası için tarih-eşlemesi yerine indeks-kadarki son bar alınır.
    prices = []
    for sym in _MACRO_SYMBOLS:
        seq = macro_by_symbol.get(sym) or []
        upto = [b for b in seq if b.ts <= btc_bars[index].ts]
        if upto:
            prices.append(SimpleNamespace(symbol=sym, price=upto[-1].close))

    snap = SimpleNamespace(
        prices=prices,
        technicals={"BTCUSD": btc_tech},
        rotation=rot_shim,
    )
    regime = classify(snap)

    return ReconScores(
        index=index,
        as_of=as_of,
        regime_label=regime.label,
        quantum=round(rot_shim.score, 2),
        fundamental_v2=(
            round(_fundamental_v2(regime), 2) if _fundamental_v2(regime) is not None else None
        ),
        sentinel=(round(_sentinel(regime), 2) if _sentinel(regime) is not None else None),
        news_reconstructed=False,
        dropped_layers=list(getattr(regime, "dropped", []) or []),
    )


def _load_series():
    """Rotasyon+BTC OHLCV ve makro serileri (1d) canlı cache'ten (ağ yok)."""
    from packages.data.providers.ohlcv import get_bars

    bars_by_symbol: dict[str, list] = {}
    for sym in set(ROTATION_SYMBOLS.values()) | {"BTCUSD"}:
        bars_by_symbol[sym] = get_bars(sym, "1d") or []
    macro_by_symbol = {sym: (get_bars(sym, "1d") or []) for sym in _MACRO_SYMBOLS}
    return bars_by_symbol, macro_by_symbol


def fidelity_report() -> dict:
    """Son indekste yeniden-kurma ↔ bağımsız canlı `get_rotation()` kıyası.

    FAITHFUL: |recon.quantum − live.quantum| ≤ tol. Bu, geçmiş yeniden-kurma
    boru hattının (bar dilimi + saf fonksiyonlar) canlı sistemle aynı sonucu
    ürettiğini kanıtlar → B-2 (rejim-çeşitli üretim) yeşil ışık alır."""
    now = datetime.now(UTC).isoformat()
    bars_by_symbol, macro_by_symbol = _load_series()
    btc_bars = bars_by_symbol.get("BTCUSD") or []
    if len(btc_bars) < _MIN_BARS:
        report = {
            "generated_at": now,
            "verdict": "INSUFFICIENT_DATA",
            "reason": f"BTCUSD {len(btc_bars)} bar < {_MIN_BARS}",
            "recon": None,
            "live_quantum": None,
        }
        _write(report)
        return report

    last = len(btc_bars) - 1
    recon = reconstruct_at(bars_by_symbol, macro_by_symbol, last)

    # Bağımsız canlı yol (aynı formül, ayrı çağrı) — quantum ground-truth.
    live = rotation_provider.get_rotation()
    live_q = getattr(live, "score", None)
    delta = (
        round(abs(recon.quantum - live_q), 3)
        if (recon.quantum is not None and live_q is not None)
        else None
    )
    if delta is None:
        verdict = "UNAVAILABLE"
    elif delta <= _FIDELITY_TOL:
        verdict = "FAITHFUL"
    else:
        verdict = "DRIFT"

    report = {
        "generated_at": now,
        "verdict": verdict,
        "quantum_delta": delta,
        "tolerance": _FIDELITY_TOL,
        "live_quantum": round(live_q, 2) if live_q is not None else None,
        "recon": asdict(recon),
        "note": (
            "news geçmişe kurulamaz (nötr 50, damgalı); rejim/fundamental/"
            "sentinel deterministik türev — quantum fidelity girdi boru hattını "
            "doğrular. FAITHFUL → B-2 rejim-çeşitli üretim güvenli."
        ),
    }
    _write(report)
    return report


def _write(report: dict) -> None:
    try:
        p = _out_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # salt-gözlem; yazım başarısızsa worker'ı kesme
