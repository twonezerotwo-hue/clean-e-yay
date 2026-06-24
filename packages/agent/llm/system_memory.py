"""Read-only system memory answers for Layer 0 chat.

This module turns existing paper/audit/learning logs into short, evidence-backed
answers. It does not call market providers, does not open/close trades, and never
feeds data back into decision/risk/paper execution.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.learning import decision_log, mistake_memory
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state

_CLOSE_ACTIONS = {"CLOSED", "KILL_SWITCH_EXIT", "RISK_REDUCE_EXIT"}


def _as_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _fmt_usd(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0"
    sign = "+" if amount > 0 else ""
    return f"{sign}${amount:,.2f}"


def _latest_trade(ps: paper_state.PaperState) -> paper_state.Trade | None:
    trades = list(ps.recent_trades or [])
    if not trades:
        return None
    return max(trades, key=lambda t: _as_dt(getattr(t, "closed_at", None)) or datetime.min.replace(tzinfo=UTC))


def _latest_decision_record(trade_id: str) -> dict | None:
    rows = decision_log.read_recent(300)
    matches = [r for r in rows if r.get("trade_id") == trade_id]
    return matches[-1] if matches else None


def _latest_audit_event(trade_id: str, *, actions: set[str] | None = None) -> dict | None:
    events = paper_audit.read_recent(500)
    wanted = actions or _CLOSE_ACTIONS
    matches = [
        e for e in events
        if e.get("position_id") == trade_id and str(e.get("action")) in wanted
    ]
    return matches[-1] if matches else None


def _latest_close_audit_event() -> dict | None:
    events = [
        e for e in paper_audit.read_recent(1000)
        if str(e.get("action")) in _CLOSE_ACTIONS
    ]
    if not events:
        return None
    return max(events, key=lambda e: _as_dt(e.get("timestamp")) or datetime.min.replace(tzinfo=UTC))


def _today_close_events() -> list[dict]:
    today = datetime.now(UTC).date()
    out: list[dict] = []
    for event in paper_audit.read_recent(1000):
        if str(event.get("action")) not in _CLOSE_ACTIONS:
            continue
        ts = _as_dt(event.get("timestamp"))
        if ts and ts.date() == today:
            out.append(event)
    return out


def _last_close_from_audit_answer(event: dict) -> tuple[str, list[str]]:
    trade_id = str(event.get("position_id") or "")
    record = _latest_decision_record(trade_id) if trade_id else None
    record_dict = record if isinstance(record, dict) else {}
    opening = (record or {}).get("opening_signal") or {}
    outcome = (record or {}).get("outcome") or {}
    exit_info = (record or {}).get("exit") or {}
    symbol = event.get("symbol") or record_dict.get("symbol")
    side = event.get("side") or record_dict.get("side")
    timeframe = event.get("timeframe") or record_dict.get("timeframe")
    reason = event.get("reason") or exit_info.get("reason") or "unknown"
    entry = outcome.get("entry_price")
    exit_price = event.get("price_used") or outcome.get("exit_price")
    exit_display = exit_price or "state'te yok"
    pnl = event.get("pnl") if event.get("pnl") is not None else outcome.get("pnl_usd")
    open_reason = event.get("open_reason") or opening.get("reason") or "state'te yok"
    size = event.get("size")
    entry_part = f"Giriş {entry}, " if entry is not None else ""
    size_part = f", kapanan büyüklük {_fmt_usd(size)}" if size is not None else ""
    diagnostics = record.get("diagnostics") if isinstance(record, dict) else None
    diag_part = (
        f" Eksik attribution: {', '.join(diagnostics)}."
        if isinstance(diagnostics, list) and diagnostics else ""
    )
    answer = (
        f"Paper state onarılmış ve recent_trades boş; bu yüzden audit fallback kullandım. "
        f"Son kapanış {symbol or '?'} {side or '?'} {timeframe or '?'}: {reason} nedeniyle kapandı. "
        f"{entry_part}çıkış {exit_display}, realized PnL {_fmt_usd(pnl)}{size_part}. "
        f"Açılış gerekçesi: {open_reason}.{diag_part} Emir üretmez; sadece audit/decision log okumasıdır."
    )
    evidence = ["paper:recent_trades:empty", f"paper_audit:{event.get('event_id') or event.get('action')}"]
    if record:
        evidence.append(f"decision_log:{record.get('record_id')}")
        if outcome.get("pnl_usd") is not None:
            evidence.append(f"outcome:pnl:{outcome.get('pnl_usd')}")
    return answer, evidence


def _last_close_answer() -> tuple[str, list[str]]:
    ps = paper_state.load()
    trade = _latest_trade(ps)
    if trade is None:
        audit_close = _latest_close_audit_event()
        if audit_close is not None:
            return _last_close_from_audit_answer(audit_close)
        return (
            "State'te kapanmış paper trade yok. Kontrol yeri: paper state recent_trades ve paper_audit CLOSED olayları.",
            ["paper:recent_trades:none", "paper_audit:closed:none"],
        )
    audit = _latest_audit_event(trade.id)
    record = _latest_decision_record(trade.id)
    opening = (record or {}).get("opening_signal") or {}
    exit_info = (record or {}).get("exit") or {}
    outcome = (record or {}).get("outcome") or {}
    reason = trade.close_reason or exit_info.get("reason") or "unknown"
    open_reason = trade.open_reason or opening.get("reason") or "state'te yok"
    size = (audit or {}).get("size")
    size_part = f", kapanan büyüklük {_fmt_usd(size)}" if size is not None else ""
    diagnostics = record.get("diagnostics") if isinstance(record, dict) else None
    diag_part = (
        f" Eksik attribution: {', '.join(diagnostics)}."
        if isinstance(diagnostics, list) and diagnostics else ""
    )
    answer = (
        f"Son kapanan pozisyon {trade.symbol} {trade.side} {trade.timeframe}: "
        f"{reason} nedeniyle kapandı. Giriş {trade.entry_price}, çıkış {trade.exit_price}, "
        f"realized PnL {_fmt_usd(trade.pnl_usd)}{size_part}. Açılış gerekçesi: {open_reason}."
        f"{diag_part} Bu cevap paper state + audit/decision log okumasıdır; emir üretmez."
    )
    evidence = [f"paper:trade:{trade.id}"]
    if audit:
        evidence.append(f"paper_audit:{audit.get('event_id') or audit.get('action')}")
    if record:
        evidence.append(f"decision_log:{record.get('record_id')}")
        if outcome.get("pnl_usd") is not None:
            evidence.append(f"outcome:pnl:{outcome.get('pnl_usd')}")
    return answer, evidence


def _today_performance_answer() -> tuple[str, list[str]]:
    ps = paper_state.load()
    events = _today_close_events()
    turnover = 0.0
    pnl = 0.0
    sized = 0
    for event in events:
        try:
            turnover += float(event.get("size") or 0.0)
            sized += 1 if event.get("size") is not None else 0
        except (TypeError, ValueError):
            pass
        try:
            pnl += float(event.get("pnl") or 0.0)
        except (TypeError, ValueError):
            pass
    if not events:
        return (
            f"Bugün kapanan paper trade görünmüyor. Günlük realized PnL state değeri {_fmt_usd(ps.daily_pnl_usd)}; "
            "audit'te kapanış olmadığı için ciro/hacim proxy'si $0.",
            ["paper:daily_pnl", "paper_audit:today_closed:none"],
        )
    return (
        f"Bugünkü paper özeti: {len(events)} kapanış, audit size toplamı {_fmt_usd(turnover)} "
        f"(ciro/hacim proxy'si; broker cirosu değil), kapanış PnL toplamı {_fmt_usd(pnl)}, "
        f"paper state daily PnL {_fmt_usd(ps.daily_pnl_usd)}. Size alanı olan kayıt sayısı {sized}.",
        ["paper:daily_pnl", f"paper_audit:today_closed:{len(events)}"],
    )


def _bad_trade_answer() -> tuple[str, list[str]]:
    ps = paper_state.load()
    losses = [t for t in ps.recent_trades if float(getattr(t, "pnl_usd", 0.0) or 0.0) < 0]
    memories = [
        m for m in mistake_memory.summary()
        if (
            m.trades >= mistake_memory.MIN_TRADES
            and (m.total_pnl < 0 or m.streak_losses > 0 or m.win_rate < mistake_memory.WARNING_WIN_RATE)
        )
        or m.streak_losses >= mistake_memory.STREAK_AVOID
    ]
    if memories:
        memories.sort(key=lambda m: (m.streak_losses, -m.win_rate, abs(m.total_pnl)), reverse=True)
        m = memories[0]
        return (
            f"Öne çıkan hatalı/kayıplı fingerprint: {m.fingerprint}. {m.trades} trade, "
            f"{m.losses} kayıp, win rate {m.win_rate:.0%}, toplam PnL {_fmt_usd(m.total_pnl)}, "
            f"son görülme {m.last_seen_at or 'yok'}. Sebep etiketi: tekrar eden kayıp davranışı; "
            "mistake memory bunu karar zincirinde yalnızca kısıtlayıcı kullanır.",
            [f"mistake:{m.fingerprint}", f"mistake:losses:{m.losses}"],
        )
    if not losses:
        return (
            "State'te kayıplı recent trade veya mistake fingerprint yok. Bu yüzden 'hatalı işlem' diye işaretlenmiş kayıt bulunmuyor.",
            ["paper:losses:none", "mistake:none"],
        )
    trade = max(losses, key=lambda t: _as_dt(getattr(t, "closed_at", None)) or datetime.min.replace(tzinfo=UTC))
    record = _latest_decision_record(trade.id)
    opening = (record or {}).get("opening_signal") or {}
    open_reason = trade.open_reason or opening.get("reason") or "state'te yok"
    return (
        f"Son kayıplı işlem {trade.symbol} {trade.side} {trade.timeframe}: PnL {_fmt_usd(trade.pnl_usd)}, "
        f"kapanış nedeni {trade.close_reason}, açılış gerekçesi {open_reason}. "
        f"Fingerprint {trade.fingerprint or opening.get('fingerprint') or 'yok'}. Bunu 'hata' diye kesin hükümlemiyorum; "
        "state'teki son kayıplı/audit edilebilir kayıt olarak gösteriyorum.",
        [f"paper:loss_trade:{trade.id}", f"decision_log:{(record or {}).get('record_id')}"],
    )


def _audit_where_answer() -> tuple[str, list[str]]:
    return (
        "Kapanış nedenlerini üç yerde kontrol edersin: Katman 3'te Paper & Learning / audit panelleri, "
        "paper state `recent_trades.close_reason`, ve `data/runtime/paper_audit.jsonl` içindeki CLOSED/KILL_SWITCH/RISK_REDUCE olayları. "
        "En temiz açıklama için bana 'son pozisyon neden kapandı?' diye sorabilirsin.",
        ["paper:recent_trades", "paper_audit:closed", "decision_log:close_attribution"],
    )


def answer(message: str) -> tuple[str, list[str]] | None:
    folded = message.casefold()
    close_words = ("kapandı", "kapandi", "kapatıldı", "kapatildi", "neden kap", "close reason")
    if any(k in folded for k in close_words) and any(k in folded for k in ("pozisyon", "işlem", "islem", "trade")):
        return _last_close_answer()
    if any(k in folded for k in ("ciro", "hacim", "bugünkü pnl", "bugunku pnl", "günlük pnl", "gunluk pnl", "bugün p&l", "bugun p&l")):
        return _today_performance_answer()
    if any(k in folded for k in ("hatalı işlem", "hatali islem", "hatalı trade", "hatali trade", "kayıplı işlem", "kayipli islem", "zararlı işlem", "zararli islem")):
        return _bad_trade_answer()
    if any(k in folded for k in ("nereden kontrol", "nerede kontrol", "audit nerede", "log nerede")) and any(k in folded for k in ("kapan", "kapat", "close")):
        return _audit_where_answer()
    return None


__all__ = ["answer"]
