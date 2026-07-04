"""RiskEngine — tek kopya. Hard gates dahil.

Eski projedeki `risk_engine.py` (services/) + `engine/risk_engine.py` duplikatı
burada birleştirildi. Action sıralaması (priority):

  HOLD < WATCH < HEDGE_INCREASE < NO_POSITION_INCREASE < RISK_REDUCE < KILL_SWITCH

G5: aktif halt (daily-loss / max-DD, file-backed) ek candidate olarak
okunur — sadece kısıtlayıcı; mevcut gate'leri gevşetmez. Halt yalnızca
owner reset ile kalkar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.data.registry.loader import load_thresholds
from packages.risk import halt as halt_store

RiskAction = Literal[
    "HOLD",
    "WATCH",
    "HEDGE_INCREASE",
    "NO_POSITION_INCREASE",
    "RISK_REDUCE",
    "KILL_SWITCH",
]

PRIORITY: dict[RiskAction, int] = {
    "HOLD": 0,
    "WATCH": 1,
    "HEDGE_INCREASE": 2,
    "NO_POSITION_INCREASE": 3,
    "RISK_REDUCE": 4,
    "KILL_SWITCH": 5,
}


@dataclass
class RiskInput:
    dqs_score: float
    equity_usd: float
    peak_equity_usd: float
    daily_pnl_usd: float
    open_position_count: int
    # S2-1 (F2-1 gate bağlama) — mark-to-market equity (açık pozisyonlar dahil).
    # None = ölçüm yok (eski çağıranlar, API yolları) → davranış birebir eski.
    # Yalnız tick_worker doldurur; flag `risk_gates.mtm_equity_enabled` AÇIKKEN
    # drawdown kontrolü min(realized, mtm) ile SIKILAŞIR (asla gevşemez).
    mtm_equity_usd: float | None = None


@dataclass
class RiskDecision:
    action: RiskAction
    reason: str
    evidence: list[str]


def evaluate(
    inp: RiskInput,
    event_candidates: list[tuple[RiskAction, str, list[str]]] | None = None,
) -> RiskDecision:
    """Risk gate kararı.

    `event_candidates` (P0 — olay riski) yalnızca **kısıtlayıcı** ek aday
    listesidir (packages.risk.event_risk üretir). Diğer adaylarla aynı havuza
    girer ve max-priority seçilir; yani DQS KILL_SWITCH / halt her zaman event
    riskini ezer (bypass yok), event riski de hiçbir gate'i gevşetemez.
    """
    th = load_thresholds()["risk_gates"]
    candidates: list[tuple[RiskAction, str, list[str]]] = []

    # 1) DQS — düşükse karar yok
    if inp.dqs_score < 55:
        candidates.append(
            ("KILL_SWITCH", "Veri kalitesi karar için yetersiz", [f"DQS {inp.dqs_score:.1f} < 55"])
        )

    # 2) Günlük zarar
    daily_limit = -th["max_daily_loss_pct"] * inp.equity_usd
    if inp.daily_pnl_usd <= daily_limit:
        candidates.append(
            (
                "KILL_SWITCH",
                "Günlük zarar limiti aşıldı",
                [f"daily pnl {inp.daily_pnl_usd:.0f} ≤ {daily_limit:.0f}"],
            )
        )

    # 3) Max drawdown
    # S2-1 — flag açık + MTM ölçümü varsa efektif equity = min(realized, mtm):
    # açık pozisyonlar toplamda eriyorsa fren realized kapanışı BEKLEMEZ.
    # min() garantisi: MTM kârı gate'i asla gevşetemez (yalnız sıkılaştırır).
    dd_equity = inp.equity_usd
    dd_label = "DD"
    if (
        bool(th.get("mtm_equity_enabled", False))
        and inp.mtm_equity_usd is not None
        and inp.mtm_equity_usd < dd_equity
    ):
        dd_equity = inp.mtm_equity_usd
        dd_label = "DD(mtm)"
    if inp.peak_equity_usd > 0:
        dd = (inp.peak_equity_usd - dd_equity) / inp.peak_equity_usd
        if dd >= th["max_drawdown_pct"]:
            candidates.append(
                (
                    "RISK_REDUCE",
                    "Maksimum drawdown sınırı aşıldı",
                    [f"{dd_label} {dd:.1%} ≥ {th['max_drawdown_pct']:.0%}"],
                )
            )

    # 4) Çok fazla açık pozisyon — 2026-07-04: hardcoded 6 → owner-tunable
    #    (risk_gates.max_open_positions). Default aynı (6); davranış bayt-aynı.
    max_open = int(th.get("max_open_positions", 6))
    if inp.open_position_count >= max_open:
        candidates.append(
            (
                "NO_POSITION_INCREASE",
                "Açık pozisyon sayısı yüksek",
                [f"{inp.open_position_count} pozisyon ≥ limit {max_open}"],
            )
        )

    # 5) Hafif uyarılar
    if inp.dqs_score < 70:
        candidates.append(("WATCH", "DQS marjinal", [f"DQS {inp.dqs_score:.1f}"]))

    # 6) G5 — aktif halt (persist edilmiş; sadece owner reset ile kalkar).
    #    Sadece kısıtlayıcı candidate ekler, mevcut gate'leri etkilemez.
    for h in halt_store.active_halts():
        candidates.append(
            (
                h.level,  # DAILY_LOSS→KILL_SWITCH, MAX_DRAWDOWN→RISK_REDUCE
                f"{h.type} halt aktif — owner reset gerekli",
                [h.reason, *h.evidence],
            )
        )

    # 7) P0 — Olay riski (event_risk). Yalnızca kısıtlayıcı; aynı havuza eklenir,
    #    max-priority seçimi DQS/halt KILL_SWITCH'i asla ezdirmez.
    for action, reason, evidence in event_candidates or []:
        candidates.append((action, reason, list(evidence)))

    if not candidates:
        return RiskDecision(action="HOLD", reason="Risk kapısı açık.", evidence=[])

    # En yüksek öncelikli olanı seç
    best = max(candidates, key=lambda c: PRIORITY[c[0]])
    return RiskDecision(action=best[0], reason=best[1], evidence=best[2])
