"""Canonical read-only decision lifecycle.

This module is deliberately a pure projection. It does not open/close paper
positions and it cannot bypass RiskGate. Every UI/LLM surface can therefore
describe the same state without inventing a second lifecycle.

Etiketler yalnız açıkça ölçülmüş gerçeklerden türetilir: teknik teyit ve haber
kurulumu çağıranın hesapladığı bool'lardır (sözlük ya da sayı "doğru" sayılmaz),
açık pozisyon (varlık, zaman dilimi) düzeyinde eşleşir.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class DecisionState(StrEnum):
    OBSERVED = "OBSERVED"
    TECHNICAL_CONFIRMED = "TECHNICAL_CONFIRMED"
    NEWS_CONFIRMED = "NEWS_CONFIRMED"
    CONFLUENCE_READY = "CONFLUENCE_READY"
    RISK_CHECKED = "RISK_CHECKED"
    PAPER_READY = "PAPER_READY"
    OWNER_APPROVAL = "OWNER_APPROVAL"
    PAPER_OPEN = "PAPER_OPEN"
    BLOCKED = "BLOCKED"


# Son kapının kanıt bekleyen engelleri: RiskGate ve yürütme kapıları geçilmiş,
# yalnız teknik teyit ya da haber-teknik kurulumu eksik. Bunlar "BLOCKED" değil,
# yaşam döngüsünde ilerleme durumudur.
EVIDENCE_BLOCKERS = frozenset({"technical_confirmation", "news_confluence"})


def derive_decision_state(
    cell: dict[str, Any],
    *,
    open_symbols: set[str] | None = None,
    open_keys: set[tuple[str, str]] | None = None,
    technical_confirmed: bool | None = None,
    news_confirmed: bool | None = None,
) -> tuple[str, str]:
    """Return one canonical lifecycle state and a human-readable reason.

    ``open_keys`` (varlık, zaman dilimi) çiftleridir; verilmezse eski çağıranlar
    için ``open_symbols`` varlık düzeyinde eşleşir. ``technical_confirmed`` ve
    ``news_confirmed`` yalnız ``True`` olduğunda teyit sayılır; ``None`` ölçüm yok.
    """
    symbol = str(cell.get("symbol") or "")
    timeframe = str(cell.get("timeframe") or "")
    if open_keys is not None:
        if (symbol, timeframe) in open_keys:
            return DecisionState.PAPER_OPEN.value, "Bu varlık ve zaman diliminde açık paper pozisyon var."
    elif symbol in (open_symbols or set()):
        return DecisionState.PAPER_OPEN.value, "Aynı varlıkta açık paper pozisyon var."

    blockers = [str(x) for x in (cell.get("blocked_by") or [])]
    hard = [b for b in blockers if b not in EVIDENCE_BLOCKERS]
    if cell.get("status") == "SUSPENDED" or hard or (cell.get("execution_state") == "BLOCKED" and not blockers):
        return DecisionState.BLOCKED.value, "; ".join(hard[:3]) or "Risk/veri kapısı bekletiyor."

    ready = cell["final_execution_ready"] if "final_execution_ready" in cell else cell.get("execution_ready")
    if ready:
        actionable = cell["final_actionable"] if "final_actionable" in cell else cell.get("actionable")
        if actionable:
            return DecisionState.PAPER_READY.value, "Tüm kanıt ve RiskGate kontrolleri geçti."
        return DecisionState.OWNER_APPROVAL.value, "Paper açılışı için owner onayı bekleniyor."

    tech = technical_confirmed is True or cell.get("confluence_aligned") is True
    news = news_confirmed is True
    if tech and news:
        return DecisionState.CONFLUENCE_READY.value, "Haber ve teknik kanıt aynı yöne hizalanıyor."
    if blockers:
        # Yalnız kanıt engelleri kaldı: RiskGate ve yürütme kapıları geçildi.
        if tech:
            return DecisionState.TECHNICAL_CONFIRMED.value, "Teknik teyit var; aynı yönde canlı haber kurulumu bekleniyor."
        if news:
            return DecisionState.NEWS_CONFIRMED.value, "Haber kurulumu hazır; teknik göstergelerin teyidi bekleniyor."
        return DecisionState.RISK_CHECKED.value, "RiskGate ve yürütme kapıları geçti; teknik ve haber teyidi bekleniyor."
    if tech:
        return DecisionState.TECHNICAL_CONFIRMED.value, "Teknik teyit var; nihai giriş kapıları bekleniyor."
    if news:
        return DecisionState.NEWS_CONFIRMED.value, "Haber kurulumu hazır; teknik teyit bekleniyor."
    if cell.get("direction") in {"bullish", "bearish"} or cell.get("score") not in (None, 50):
        return DecisionState.OBSERVED.value, "Teknik yön var; henüz teyitli giriş adayı değil."
    return DecisionState.OBSERVED.value, "Yalnızca izleme kanıtı mevcut."


__all__ = ["EVIDENCE_BLOCKERS", "DecisionState", "derive_decision_state"]
