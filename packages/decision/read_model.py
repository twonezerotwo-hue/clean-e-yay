"""Okuma yüzeyleri için tek karar kaynağı (hedef mimari: tek karar kaydı).

Ekran, brifing, YZ bağlamı ve raporlar kararı, konsensüsü ve rejimi kendileri
hesaplamaz; tick'in aynı anlık görüntü için yayımladığı kararı okur
(``tick_artifact``). Tick bu görüntü için yayımlamadıysa (ilk açılış, ayrı API
süreci, test) aynı fonksiyonla (``decide_matrix``) bir kez hesaplanır.

İşlem evreni dışındaki semboller (makro göstergeler) için tick karar vermez; bu
semboller okunurken konsensüs aynı görüntü ve tick'in rejimiyle hesaplanır.

Salt okuma: karar yetkisi eklemez, RiskGate'i atlamaz, kararı değiştirmez.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionView:
    snap: Any
    ps: Any
    symbols: list[str]
    regime: Any
    risk: Any
    decisions: list[Any]
    _off_universe: dict = field(default_factory=dict, repr=False)

    def consensus(self, symbol: str, timeframe: str = "1d") -> Any:
        """Sembol × TF konsensüsü: işlem evreninde tick'in kararından okunur."""
        for d in self.decisions:
            if d.symbol == symbol and getattr(d, "timeframe", "1d") == timeframe:
                return d.consensus
        key = (symbol, timeframe)
        if key not in self._off_universe:
            from packages.consensus.engine import build as build_consensus

            self._off_universe[key] = build_consensus(symbol, self.snap, self.regime, timeframe)
        return self._off_universe[key]

    def matrix(self) -> dict:
        """Karar matrisi görünümü (hücre rozetleri + son kapı durumu)."""
        from packages.decision.cockpit import finalize_matrix_view
        from packages.decision.engine import matrix_view

        view = matrix_view(self.regime, self.risk, self.decisions, self.snap, self.symbols)
        return finalize_matrix_view(view, self.snap, self.ps)


def current(snap: Any = None, ps: Any = None) -> DecisionView:
    """Şu anki karar: tick'in yayını (aynı görüntü), yoksa aynı girdilerle hesap."""
    from packages.data.ingestion.pipeline import get_cached_snapshot
    from packages.data.registry import assets as asset_registry
    from packages.decision import paper_policy
    from packages.decision.tick_artifact import decide_matrix_for
    from packages.paper import state as paper_state
    from packages.risk.engine import risk_input_from_state

    snap = snap if snap is not None else get_cached_snapshot()
    ps = ps if ps is not None else paper_state.load()
    symbols = asset_registry.trade_symbols()
    regime, risk, decisions = decide_matrix_for(
        symbols,
        snap,
        risk_input_from_state(ps, snap.quality.score),
        open_positions=ps.open_positions,
        paper_exploration=paper_policy.enabled(),
    )
    return DecisionView(snap, ps, symbols, regime, risk, list(decisions))


__all__ = ["DecisionView", "current"]
