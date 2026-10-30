"""Son kapı — aday kararın paper rotası (tek uygulama).

Tick bunu her aday hücre için bir kez çalıştırır ve sonucunu yayınlar; okuma
yüzeyleri (cockpit, karar matrisi, brifing, YZ) aynı sonucu gösterir, tick
yayını yoksa aynı fonksiyonu çalıştırır. Önceden kapı iki yerde ayrı yazılıydı
ve ekranda seans kapısı, owner onayı rotası ve haber çelişkisi yoktu.

Sıra (ilk düşen kapı gerekçedir):
  1. yürütmeye hazır mı — decide_matrix'in kapıları, RiskGate dahil
  2. teknik veri taze ve doğrulanmış mı
  3. teknik teyit (gösterge grubu sayımı)
  4. haber/dünya etkisi — çelişkide boyut küçültür, require modunda zorunlu
  5. seans + conflict gate rotası (block / manual_ready / open)

Yalnız kısıtlar: çarpanlar ≤ 1, hiçbir kapıyı gevşetmez, RiskGate'i atlamaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from packages.decision import gates
from packages.decision.engine import execution_readiness
from packages.paper import news_setup

CANDIDATE_ACTIONS = frozenset({"open_long", "open_short"})


def technical_data_ready(snap: Any, symbol: str, timeframe: str) -> bool:
    """Return true only for a complete, non-degraded technical cell."""
    by_tf = getattr(snap, "technicals_by_tf", None) or {}
    tech = (by_tf.get(symbol) or {}).get(timeframe)
    if tech is None:
        tech = (getattr(snap, "technicals", None) or {}).get(symbol)
    return str(getattr(tech, "status", "")).upper() == "OK"


# Aynı şeyi ölçen göstergeler tek teyit sayılır (owner kararı 2026-10-30):
# MACD histogramı ve RSI ikisi de momentumdur; kapı yalnız momentumla geçilmez.
# Gereken sayı farklı GRUP sayısıdır; tanınmayan gösterge kendi grubudur.
CONFIRMATION_GROUPS = {
    "macd_histogram_positive": "momentum",
    "rsi_above_50": "momentum",
    "ema_stack_bullish": "trend",
    "above_vwap": "location",
}


def _confirmation_group(signal: Any, index: int) -> str:
    name = getattr(signal, "name", None)
    if not name:
        return f"#{index}"  # adsız (eski fixture) sinyal kendi grubudur
    return CONFIRMATION_GROUPS.get(str(name), str(name))


def technical_confirmation_ready(
    snap: Any, symbol: str, timeframe: str, side: str, *, min_confirmations: int | None = None
) -> tuple[bool, str | None]:
    """Require same-side indicator confirmations for automatic paper opening.

    Older replay/synthetic snapshots do not carry ``confirmation_signals``;
    those remain backward compatible. Live technical cells do carry the list,
    so an empty or opposing list cannot silently pass the final gate.
    Confirmations are counted per indicator group (see CONFIRMATION_GROUPS),
    so two momentum readings count once.
    """
    by_tf = getattr(snap, "technicals_by_tf", None) or {}
    tech = (by_tf.get(symbol) or {}).get(timeframe)
    if tech is None:
        tech = (getattr(snap, "technicals", None) or {}).get(symbol)
    if tech is None or str(getattr(tech, "status", "")).upper() != "OK":
        return False, "technical_data"
    signals = getattr(tech, "confirmation_signals", None)
    if signals is None:
        return True, None
    try:
        from packages.data.registry.loader import load_thresholds
        cfg = load_thresholds().get("technical_entry_gate") or {}
        if not bool(cfg.get("enabled", True)):
            return True, None
    except Exception:
        cfg = {}
    signals = list(signals or [])
    if not signals:
        return False, "technical_confirmation"
    required = min_confirmations
    if required is None:
        per_timeframe = cfg.get("min_confirmations_by_timeframe") or {}
        required = per_timeframe.get(timeframe, cfg.get("min_confirmations", 2))
    try:
        required = int(required)
    except (TypeError, ValueError):
        required = 2
    required = max(1, int(required))
    wanted = "bullish" if str(side).casefold() == "long" else "bearish"
    directional = [getattr(signal, "direction", None) for signal in signals]
    if any(value is not None for value in directional):
        # Live signals carry explicit bullish/bearish/neutral semantics; neutral
        # is not evidence for either side.
        groups = {
            _confirmation_group(signal, i)
            for i, signal in enumerate(signals)
            if getattr(signal, "direction", None) == wanted
        }
    else:
        # Legacy replay fixtures predate the tri-state field.
        groups = {
            _confirmation_group(signal, i)
            for i, signal in enumerate(signals)
            if bool(getattr(signal, "fired", False)) == (wanted == "bullish")
        }
    aligned = len(groups)
    return (aligned >= required, None if aligned >= required else f"technical_confirmation:{aligned}/{required}")


@dataclass(frozen=True)
class FinalGate:
    """Bir aday hücrenin son kapı sonucu.

    ``route``: "open" (otomatik açılış), "manual_ready" (owner onayı) ya da
    "block". ``blocker`` ilk düşen kapının kodudur. ``size_multiplier`` seans,
    conflict gate ve haber çarpanlarının çarpımıdır (kararın kendi boyutu hariç).
    ``technical_confirmed`` / ``news_matched`` yaşam döngüsü etiketi içindir.
    """

    route: str
    side: str | None = None
    blocker: str | None = None
    reason: str | None = None
    size_multiplier: float = 0.0
    news_effect: dict | None = None
    gate: gates.GateDecision | None = None
    technical_confirmed: bool | None = None
    news_matched: bool | None = None
    detail: dict = field(default_factory=dict)


def _side(action: str | None) -> str | None:
    if action == "open_long":
        return "long"
    if action == "open_short":
        return "short"
    return None


def evaluate(
    d: Any,
    *,
    snap: Any,
    setups: Any,
    prices: dict[str, float],
    verified_flags: dict[str, bool],
    now: datetime,
    regime: Any,
    gate_cfg: Any,
    conflict_by_symbol: dict[str, dict],
    execution_ready: bool | None = None,
) -> FinalGate:
    """Aday kararı son kapıdan geçir. ``execution_ready`` verilirse (okuma modeli
    hücreleri) karar nesnesinin kendi hazırlık kontrolü yerine o kullanılır."""
    side = _side(getattr(d, "action", None))
    if side is None:
        return FinalGate(route="block", blocker="no_candidate")
    symbol, timeframe = str(d.symbol), str(d.timeframe)

    if execution_ready is None:
        ready, state = execution_readiness(d)
    else:
        ready, state = bool(execution_ready), "READY" if execution_ready else "BLOCKED"
    if not ready:
        return FinalGate(route="block", side=side, blocker="execution_gate", reason=state,
                         detail={"execution_state": state})

    if not technical_data_ready(snap, symbol, timeframe):
        return FinalGate(route="block", side=side, blocker="technical_data",
                         reason="Teknik veri taze ve doğrulanmış değil.", technical_confirmed=False)
    technical_ok, technical_reason = technical_confirmation_ready(snap, symbol, timeframe, side)

    # Haber etkisi saf ve ucuzdur; etiket için teknik teyit düşse de ölçülür.
    news_effect = news_setup.auto_open_news_effect(
        setups,
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        price=prices.get(symbol),
        data_verified=verified_flags.get(symbol, False),
        decision_id=getattr(d, "decision_id", None),
        now=now,
    )
    news_matched = True if news_effect["match"] else (False if news_effect["mode"] == "require" else None)
    evidence = {"technical_confirmed": technical_ok, "news_matched": news_matched, "news_effect": news_effect}

    if not technical_ok:
        return FinalGate(route="block", side=side, blocker="technical_confirmation",
                         reason=technical_reason or "insufficient same-side confirmations", **evidence)
    if not news_effect["allow"]:
        blocker = "news_confluence" if news_effect["mode"] == "require" else "news_conflict"
        return FinalGate(route="block", side=side, blocker=blocker, reason=news_effect["reason"], **evidence)

    routed = gates.apply_gates(
        d, side=side, now=now, regime=regime, gate_cfg=gate_cfg, conflict_by_symbol=conflict_by_symbol,
    )
    if routed.route == "block":
        return FinalGate(route="block", side=side, blocker="session_gate",
                         reason="Seans ya da conflict gate açılışı engelledi.", gate=routed, **evidence)
    return FinalGate(
        route=routed.route,
        side=side,
        reason=routed.reason,
        size_multiplier=routed.effective_multiplier * float(news_effect["size_multiplier"]),
        gate=routed,
        **evidence,
    )


__all__ = [
    "CANDIDATE_ACTIONS",
    "CONFIRMATION_GROUPS",
    "FinalGate",
    "evaluate",
    "technical_confirmation_ready",
    "technical_data_ready",
]
