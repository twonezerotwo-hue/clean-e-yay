"""T5 — fırtına kuralı (dış denetim P0-3): DEFENSIVE/CRISIS → owner onayı.

Eski kural yalnız API kopya motorunda yaşıyordu ve `RegimeOutput` nesnesini
string'le kıyasladığı için HİÇ çalışmamıştı. Tamir tek rotalama noktasında
(`decision/gates.apply_gates`). Kapsam:
- flag KAPALI (default): rejim fırtına olsa da rota "open" — bayt-aynı (izleme);
- flag AÇIK: DEFENSIVE ve CRISIS "manual_ready" + reason `regime_<label>`;
- flag AÇIK: OFFENSIVE/NEUTRAL rota "open" (kural yalnız fırtınada);
- label'sız/None rejim güvenli: rota "open" (kural sessiz kalır).
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.data.registry.loader import threshold_override
from packages.decision import conflict_gate, gates

# BTCUSD 7/24 açık → session gate "open" verir; hafta içi öğlen UTC güvenli.
_NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _decision(symbol="BTCUSD", tf="1d"):
    return SimpleNamespace(symbol=symbol, timeframe=tf, risk=SimpleNamespace(action="OPEN"))


def _apply(regime_label):
    regime = SimpleNamespace(label=regime_label) if regime_label is not None else None
    return gates.apply_gates(
        _decision(), side="long", now=_NOW, regime=regime,
        gate_cfg=conflict_gate.load_config(), conflict_by_symbol={},
    )


def test_flag_off_storm_regime_stays_open_byte_same() -> None:
    for label in ("DEFENSIVE", "CRISIS"):
        routed = _apply(label)
        assert routed.route == "open", label  # izleme modu: rota değişmez


def test_flag_on_storm_regime_routes_to_manual_ready() -> None:
    with threshold_override({"gates": {"regime_manual_ready": {"enabled": True}}}):
        for label, reason in (("DEFENSIVE", "regime_defensive"), ("CRISIS", "regime_crisis")):
            routed = _apply(label)
            assert routed.route == "manual_ready", label
            assert routed.reason == reason


def test_flag_on_calm_regime_stays_open() -> None:
    with threshold_override({"gates": {"regime_manual_ready": {"enabled": True}}}):
        for label in ("OFFENSIVE", "NEUTRAL"):
            assert _apply(label).route == "open", label


def test_flag_on_missing_regime_label_stays_open() -> None:
    """Rejim nesnesi yok/label'sız → kural sessizce devre dışı (crash yok)."""
    with threshold_override({"gates": {"regime_manual_ready": {"enabled": True}}}):
        assert _apply(None).route == "open"
