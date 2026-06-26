"""Conflict Resolver — sabit otorite sırası (spec v2.3 §28), EVIDENCE/gözlem amaçlı.

Bu modül **yeni bir karar motoru değildir** — mevcut `decide_for_symbol()` /
`agent_decision.decide()` zincirlerinin yerini almaz, onlara dokunmaz. Zaten
hesaplanmış kanıtları (risk gate aksiyonu, DQS durumu, setup classifier
sonucu, trade economics, historical edge, consensus alignment, Elliott) sabit
bir otorite sırasıyla birleştirip **gözlem amaçlı** bir "v2.3 bu durumda ne
derdi" çıktısı üretir. Paper state'i mutate etmez, trade açmaz/kapatmaz.

Otorite sırası (en yüksekten en düşüğe — spec §28.1):
  1. Hard Safety        (DQS_BAD, KILL_SWITCH benzeri risk_gate_action)
  2. Data Validity       (DQS_DEGRADED — trade_profile bazlı matris, spec §29)
  3. Agent Mode Permission (Faz 4 — packages/mode/filter.py'dan opsiyonel girdi; verilmezse PASS)
  4. RiskGate            (risk_gate_action: HOLD/WATCH ok, NO_POSITION_INCREASE/RISK_REDUCE/KILL_SWITCH blok)
  5. Position Management (açık pozisyon girişi bu modülün kapsamı dışında — PASS, diagnostic'te belirtilir)
  6. Trigger Validity    (trigger_confirmed)
  7. SL/TP/RR Validity   (sl_tp_rr_valid — trade_economics.allow)
  8. Setup Validity      (setup_type != NO_TRADE)
  9. Historical Edge     (historical_edge_strong_negative → blok; aksi halde sadece bilgi)
  10. Position Sizing     (size_multiplier > 0)
  11. Alignment/Consensus (alignment_status != CONFLICTED)
  12. Elliott/Technical Evidence (en düşük — asla tek başına bloklamaz/açmaz, sadece bilgi)

`blocked_by` her zaman otorite sırasına göre doldurulur; `conflict_resolution_path`
kronolojik değerlendirme sırasını taşır (bu ikisi farklı amaçlar için ayrı tutulur,
spec §28.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field

BLOCKED = "BLOCKED"
NO_TRADE = "NO_TRADE"
WATCH = "WATCH"
CANDIDATE_OPEN = "CANDIDATE_OPEN"  # "OPEN_PAPER" DEĞİL — bu modül hiçbir şey açmaz, sadece aday üretir.

_HARD_SAFETY_ACTIONS = {"KILL_SWITCH"}
_RISK_BLOCK_ACTIONS = {"NO_POSITION_INCREASE", "RISK_REDUCE", "KILL_SWITCH"}


@dataclass(frozen=True)
class ConflictInputs:
    """Tüm alanlar mevcut, zaten hesaplanmış kanıtlardan okunur (yeni I/O yok)."""

    dqs_status: str  # OK | DEGRADED | BAD
    risk_gate_action: str  # HOLD | WATCH | HEDGE_INCREASE | NO_POSITION_INCREASE | RISK_REDUCE | KILL_SWITCH
    trigger_confirmed: bool
    sl_tp_rr_valid: bool
    setup_type: str  # packages.setup.classifier sonucu
    historical_edge_strong_negative: bool
    size_multiplier: float
    alignment_status: str  # ALIGNED | PARTIAL | CONFLICTED | COUNTERTREND
    elliott_scenario: str | None = None
    elliott_confidence: float = 0.0
    # Faz 4 — additive. Default'lar eski davranışı korur (mode her zaman PASS,
    # trade_profile yoksa DQS_DEGRADED jenerik WATCH'a düşer).
    mode_filter_passed: bool = True
    mode_filter_blocked_reason: str | None = None
    trade_profile: str | None = None  # SCALP/INTRADAY/TACTICAL/SWING/POSITION (packages/mode)


@dataclass(frozen=True)
class ConflictResolution:
    final_action: str
    blocked_by: list[str] = field(default_factory=list)
    conflict_resolution_path: list[str] = field(default_factory=list)
    authority_order_applied: list[str] = field(default_factory=list)


def resolve(inputs: ConflictInputs) -> ConflictResolution:
    path: list[str] = []
    blocked_by: list[str] = []  # otorite sırasına göre doldurulur (1→12)

    # 1) Hard Safety
    path.append(f"hard_safety:dqs={inputs.dqs_status},risk={inputs.risk_gate_action}")
    hard_blocked = inputs.dqs_status == "BAD" or inputs.risk_gate_action in _HARD_SAFETY_ACTIONS
    if hard_blocked:
        blocked_by.append(f"hard_safety:{inputs.dqs_status}/{inputs.risk_gate_action}")
        return ConflictResolution(
            final_action=BLOCKED,
            blocked_by=blocked_by,
            conflict_resolution_path=path,
            authority_order_applied=["hard_safety"],
        )

    # 2) Data Validity (DQS_DEGRADED) — sert blok değil, sadece not edilir.
    path.append(f"data_validity:dqs={inputs.dqs_status}")
    dqs_degraded = inputs.dqs_status == "DEGRADED"

    # 3) Agent Mode Permission — Faz 4: packages/mode/filter.py'dan opsiyonel
    # girdi. Çağıran taraf değerlendirmezse default True (eski davranış).
    path.append(f"agent_mode_permission:{inputs.mode_filter_passed}")
    if not inputs.mode_filter_passed:
        blocked_by.append(f"agent_mode:{inputs.mode_filter_blocked_reason or 'blocked'}")

    # 4) RiskGate
    path.append(f"risk_gate:{inputs.risk_gate_action}")
    if inputs.risk_gate_action in _RISK_BLOCK_ACTIONS:
        blocked_by.append(f"risk_gate:{inputs.risk_gate_action}")

    # 5) Position Management — bu modülün kapsamı dışında (açık pozisyon girdisi yok).
    path.append("position_management:out_of_scope_pass")

    # 6) Trigger Validity
    path.append(f"trigger_validity:{inputs.trigger_confirmed}")
    if not inputs.trigger_confirmed:
        blocked_by.append("trigger_missing")

    # 7) SL/TP/RR Validity
    path.append(f"sl_tp_rr_validity:{inputs.sl_tp_rr_valid}")
    if not inputs.sl_tp_rr_valid:
        blocked_by.append("sl_tp_rr_invalid")

    # 8) Setup Validity
    path.append(f"setup_validity:{inputs.setup_type}")
    setup_invalid = inputs.setup_type == "NO_TRADE"
    if setup_invalid:
        blocked_by.append("setup_invalid")

    # 9) Historical Edge
    path.append(f"historical_edge:strong_negative={inputs.historical_edge_strong_negative}")
    if inputs.historical_edge_strong_negative:
        blocked_by.append("historical_edge_strong_negative")

    # 10) Position Sizing
    path.append(f"position_sizing:{inputs.size_multiplier}")
    if inputs.size_multiplier <= 0.0:
        blocked_by.append("position_size_zero")

    # 11) Alignment / Consensus
    path.append(f"alignment:{inputs.alignment_status}")
    if inputs.alignment_status == "CONFLICTED":
        blocked_by.append("alignment_conflicted")

    # 12) Elliott / Technical Evidence — asla tek başına bloklamaz, sadece bilgi.
    path.append(f"elliott_evidence:{inputs.elliott_scenario}@{inputs.elliott_confidence}")

    authority_order_applied = sorted(set(blocked_by))

    if blocked_by:
        # Trigger eksikse ve diğer her şey geçerliyse (setup valid, RR valid, risk
        # gate açık) sonuç WATCH'tır — "geçerli ama henüz tetiklenmedi" (spec §37.5).
        only_trigger_missing = blocked_by == ["trigger_missing"]
        final = WATCH if only_trigger_missing else NO_TRADE
        return ConflictResolution(final, blocked_by, path, authority_order_applied)

    if dqs_degraded:
        # Faz 4 — spec §29 DQS_DEGRADED karar matrisi (trade_profile bazlı).
        # trade_profile verilmezse jenerik WATCH'a düşülür (eski davranış).
        strong_confirmation = inputs.trigger_confirmed and not setup_invalid and inputs.sl_tp_rr_valid
        if inputs.trade_profile == "SCALP":
            return ConflictResolution(NO_TRADE, ["dqs_degraded_scalp_blocked"], path, ["data_validity"])
        if inputs.trade_profile in ("INTRADAY", "TACTICAL"):
            return ConflictResolution(WATCH, ["dqs_degraded_size_capped"], path, ["data_validity"])
        if inputs.trade_profile == "SWING" and strong_confirmation:
            return ConflictResolution(CANDIDATE_OPEN, [], path, [])
        return ConflictResolution(WATCH, ["dqs_degraded"], path, ["data_validity"])

    return ConflictResolution(CANDIDATE_OPEN, [], path, [])


__all__ = ["ConflictInputs", "ConflictResolution", "resolve", "BLOCKED", "NO_TRADE", "WATCH", "CANDIDATE_OPEN"]
