"""Notification detector — state diff'inden event üretir.

Her tick'in sonunda çağrılır:
  - Önceki ve şimdiki ticket/position/recheck/risk state'ini karşılaştır
  - Değişimlere göre Notification listesi üret (append edilir)

Karar VERMEZ, sadece gözlemler. PAPER_SAFE.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.notifications import Notification, make_id


def _format_pct(x: float) -> str:
    if x >= 1:
        return f"%{int(round(x))}"
    return f"%{int(round(x * 100))}"


def _ticket_short(t: dict[str, Any]) -> str:
    s = t.get("summary", {}) or {}
    side_label = "AL" if t.get("side") == "long" else "SAT"
    entry = s.get("entry_price")
    conf = s.get("confidence_calibrated")
    parts = [t.get("timeframe", "?").upper()]
    if entry is not None:
        parts.append(f"giriş {entry:,.2f}")
    if conf is not None:
        parts.append(f"güven {_format_pct(conf)}")
    return f"{t.get('symbol', '?')} {side_label} · " + " · ".join(parts)


def detect_new_tickets(
    prev_ids: set[str],
    current_tickets: list[dict[str, Any]],
) -> list[Notification]:
    """Bu tick'te ilk kez görülen active ticket'lar için bildirim."""
    out: list[Notification] = []
    for t in current_tickets:
        if t.get("status") != "active":
            continue
        tid = t.get("id")
        if not tid or tid in prev_ids:
            continue
        s = t.get("summary", {}) or {}
        side_label = "AL" if t.get("side") == "long" else "SAT"
        title = f"Yeni {t.get('symbol')} {side_label} sinyali"
        out.append(Notification(
            id=make_id("ticket_created"),
            ts=datetime.now(UTC).isoformat(),
            type="ticket_created",
            priority="high",
            title=title,
            body_short=_ticket_short(t),
            body_long=(
                f"{t.get('symbol')} sembolünde {t.get('timeframe', '?').upper()} "
                f"zaman diliminde {side_label} sinyali oluştu. "
                f"Giriş: {s.get('entry_price')}, "
                f"Zarar Durdur: {s.get('stop_loss')}, "
                f"Kâr Al: {s.get('take_profit')}, "
                f"R/R: 1:{s.get('rr_ratio', 0):.1f}, "
                f"Güven: {_format_pct(s.get('confidence_calibrated', 0))}."
            ),
            ticket_id=tid,
        ))
    return out


def detect_expiring_tickets(
    current_tickets: list[dict[str, Any]],
    *,
    warn_minutes: int = 5,
) -> list[Notification]:
    """Son N dakikada bitiyor olan ticket'lar için tek-seferlik bildirim.

    Detector idempotent değil; çağıran kod prev_notified_ids ile çakışma
    önlemelidir (router katmanında session-set tutar).
    """
    out: list[Notification] = []
    now = datetime.now(UTC)
    for t in current_tickets:
        if t.get("status") != "active":
            continue
        exp = t.get("expires_at")
        if not exp:
            continue
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        mins_left = (exp_dt - now).total_seconds() / 60.0
        if 0 < mins_left <= warn_minutes:
            out.append(Notification(
                id=make_id("ticket_expiring"),
                ts=now.isoformat(),
                type="ticket_expiring",
                priority="medium",
                title="Ticket süresi bitiyor",
                body_short=f"{t.get('symbol')} {t.get('timeframe', '?').upper()} {int(mins_left)}dk sonra geçersiz",
                body_long=(
                    f"{t.get('symbol')} {t.get('timeframe', '?').upper()} ticket'ı "
                    f"{int(mins_left)} dakika sonra geçerliliğini kaybedecek."
                ),
                ticket_id=t.get("id"),
            ))
    return out


def detect_recheck_changes(
    prev_verdicts: dict[str, str],
    current_rechecks: list[dict[str, Any]],
) -> list[Notification]:
    """Verdict EXIT_RECOMMEND'a döndüyse veya REDUCE yeni geldiyse bildirim."""
    out: list[Notification] = []
    now = datetime.now(UTC)
    for r in current_rechecks:
        pid = r.get("position_id")
        verdict = r.get("verdict")
        if not pid or not verdict:
            continue
        prev = prev_verdicts.get(pid)
        if verdict == prev:
            continue  # değişmedi
        side_label = "LONG" if r.get("side") == "long" else "SHORT"
        if verdict == "EXIT_RECOMMEND":
            out.append(Notification(
                id=make_id("recheck_exit"),
                ts=now.isoformat(),
                type="recheck_exit_recommend",
                priority="high",
                title=f"Çıkış önerisi: {r.get('symbol')} {side_label}",
                body_short=f"{r.get('symbol')} {r.get('timeframe', '?').upper()} sinyali tersine döndü",
                body_long=(
                    f"Açık {r.get('symbol')} {side_label} pozisyonun için sistem "
                    f"sinyalin çıkış önerisine döndüğünü tespit etti. Sebep: {r.get('reason', '-')}."
                ),
                position_id=pid,
            ))
        elif verdict == "REDUCE":
            out.append(Notification(
                id=make_id("recheck_reduce"),
                ts=now.isoformat(),
                type="recheck_reduce",
                priority="medium",
                title=f"Boyut azaltma önerisi: {r.get('symbol')} {side_label}",
                body_short=f"{r.get('symbol')} {r.get('timeframe', '?').upper()} risk kontrolü kısıtlama uyguluyor",
                body_long=(
                    f"Açık {r.get('symbol')} {side_label} pozisyonun için risk kontrolleri "
                    f"yeni girişe izin vermiyor — mevcut boyutu azaltmayı öner. "
                    f"Sebep: {r.get('reason', '-')}."
                ),
                position_id=pid,
            ))
    return out


def detect_risk_gate_change(
    prev_action: str | None,
    current_action: str | None,
    current_reason: str | None,
) -> list[Notification]:
    """RiskGate seviyesi yükseldiğinde (kısıtlama arttı) bildirim."""
    if prev_action == current_action or current_action is None:
        return []
    severity = {
        "ALLOW_NORMAL": 0,
        "NO_POSITION_INCREASE": 1,
        "RISK_REDUCE": 2,
        "KILL_SWITCH": 3,
    }
    cur_s = severity.get(current_action, -1)
    prev_s = severity.get(prev_action or "", -1)
    if cur_s <= prev_s:
        return []  # gevşedi veya değişmedi

    now = datetime.now(UTC)
    priority = "critical" if current_action == "KILL_SWITCH" else "high"
    title_map = {
        "NO_POSITION_INCREASE": "Risk: yeni giriş durdu",
        "RISK_REDUCE": "Risk: boyut azaltılmalı",
        "KILL_SWITCH": "Risk: tüm girişler durduruldu",
    }
    # Ham enum değerleri (KILL_SWITCH, RISK_REDUCE, ...) kullanıcıya hiç
    # gösterilmez — body_short/body_long her zaman Türkçe etiket kullanır.
    short_label_map = {
        "NO_POSITION_INCREASE": "Yeni giriş durduruldu",
        "RISK_REDUCE": "Boyut azaltma gerekiyor",
        "KILL_SWITCH": "Tüm girişler durduruldu",
    }
    long_label_map = {
        "ALLOW_NORMAL": "normal",
        "NO_POSITION_INCREASE": "yeni giriş durduruldu",
        "RISK_REDUCE": "boyut azaltma gerekiyor",
        "KILL_SWITCH": "tüm girişler durduruldu",
    }
    return [Notification(
        id=make_id("risk_gate"),
        ts=now.isoformat(),
        type="risk_gate_changed" if current_action != "KILL_SWITCH" else "risk_kill_switch",
        priority=priority,
        title=title_map.get(current_action, "Risk seviyesi değişti"),
        body_short=(
            f"{short_label_map.get(current_action, 'Risk seviyesi değişti')} "
            f"— {current_reason or 'detay yok'}"
        ),
        body_long=(
            f"Risk motoru seviyesi {long_label_map.get(prev_action or '', 'belirsiz')} → "
            f"{long_label_map.get(current_action, current_action)} olarak değişti. "
            f"Sebep: {current_reason or 'detay yok'}."
        ),
    )]


def detect_catalyst_imminent(
    prev_imminent_ids: set[str],
    catalysts: list[dict[str, Any]],
) -> list[Notification]:
    """Önemli catalyst'ler T-15dk ve T-5dk'da bildirim (idempotent değil; caller
    set tutar)."""
    out: list[Notification] = []
    now = datetime.now(UTC)
    for cat in catalysts:
        cid = cat.get("id") or cat.get("catalyst_id")
        if not cid or cid in prev_imminent_ids:
            continue
        importance = (cat.get("importance") or "").upper()
        if importance not in {"HIGH", "CRITICAL"}:
            continue
        mins_to = cat.get("minutes_to_event")
        if mins_to is None:
            continue
        try:
            mins_to = float(mins_to)
        except (ValueError, TypeError):
            continue
        if not (0 < mins_to <= 15):
            continue
        title = cat.get("title") or cat.get("event_type") or "Önemli olay"
        out.append(Notification(
            id=make_id("catalyst"),
            ts=now.isoformat(),
            type="catalyst_imminent",
            priority="high",
            title=f"Yaklaşan olay: {title}",
            body_short=f"{title} · {int(mins_to)}dk sonra · {importance}",
            body_long=(
                f"{title} olayı {int(mins_to)} dakika içinde gerçekleşecek "
                f"({importance} önem). Pozisyonlarını ve yeni girişleri gözden geçir."
            ),
        ))
    return out


def detect_dqs_drop(
    prev_dqs: float | None,
    current_dqs: float | None,
    *,
    threshold: int = 70,
) -> list[Notification]:
    """DQS eşiğin altına ilk kez düştüğünde bildirim."""
    if current_dqs is None or prev_dqs is None:
        return []
    if prev_dqs >= threshold and current_dqs < threshold:
        return [Notification(
            id=make_id("dqs_drop"),
            ts=datetime.now(UTC).isoformat(),
            type="dqs_dropped",
            priority="medium",
            title="Veri kalitesi düştü",
            body_short=f"DQS {int(prev_dqs)} → {int(current_dqs)} (eşik {threshold})",
            body_long=(
                f"Veri kalitesi skoru {int(prev_dqs)}'dan {int(current_dqs)}'a düştü. "
                f"Sinyallere temkinli bak — fiyat verisi şu an güvenilir aralığın altında."
            ),
        )]
    return []


__all__ = [
    "detect_new_tickets",
    "detect_expiring_tickets",
    "detect_recheck_changes",
    "detect_risk_gate_change",
    "detect_catalyst_imminent",
    "detect_dqs_drop",
]
