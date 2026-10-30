"""Fikir → paper pozisyon (owner onayıyla). SALT PAPER / NO_EXECUTION — gerçek broker emri YOK.

Fikir Panosu'ndaki (packages/discovery/ideas) bir fikri, owner'ın açık onayıyla MEVCUT manuel emir
yolundan (`manual_order.place`) paper pozisyona çevirir. Yeni karar/risk mantığı YOK:

* RiskGate (DQS, günlük zarar, max drawdown, maks. açık pozisyon, halt), canlı fiyat, price-sanity ve
  bakiye denetimi `manual_order.place` içinde olduğu gibi, defter kilidi altında çalışır.
* Bu modül yalnız fikre özgü ön koşulları ekler — hepsi KISITLAYICIDIR: sinyal geçerli/taze mi, aynı
  sembolde açık pozisyon/bekleyen emir, seans kapısı, korelasyon kümesi, state-anomali, toplam
  maruziyet ve boyut. Sonuç, kullanıcıya gerçek engel nedenini taşıyan yapılandırılmış durum koduyla döner.

İki giriş noktası aynı kontrolleri paylaşır:

* `annotate_board(view)` — `GET /ideas` için fikir başına `paper_open` ön-durumu. AĞ ÇAĞRISI YOK
  (kalıcı snapshot + defter dosyası); butonun pasif/aktif halini belirler, emir açmaz.
* `open_from_idea(symbol)` — onay: taze snapshot ile `manual_order.place`; aynı ön koşullar defter
  kilidi İÇİNDE (guard) yeniden denetlenir → çift tıklama/yarışta tek pozisyon.

Fikirler yalnız LONG'dur (keşif: WOULD_OPEN_LONG ∪ haber YUKARI); yön fikirden türetilir, istemciden
alınmaz. Pozisyon `open_reason="owner_idea"` ile açılır: öğrenme kohortları "owner" önekini MANUAL
sayar, otomatik kalibrasyona sızmaz.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.data import snapshot_store
from packages.data.providers import price as price_provider
from packages.data.registry.loader import load_thresholds
from packages.discovery import ideas, scanner
from packages.ops.system_health import DEFAULT_TICK_STALE_SEC
from packages.paper import manual_order
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity, state_anomaly
from packages.paper.lifecycle import _TF_SECONDS, _ensure_daily_anchor
from packages.paper.session_gate import evaluate_open as evaluate_session
from packages.paper.sizing import compute_size_usd
from packages.risk import correlation
from packages.risk.engine import evaluate as evaluate_risk
from packages.risk.engine import risk_input_from_state

OPEN_REASON = "owner_idea"
DEFAULT_SIZE_MULTIPLIER = 0.25  # base boyut çarpanı (max_position_usd'nin payı); yalnız KÜÇÜLTÜLÜR

# Durum kodları (UI etiketi frontend'de; sebep metni backend'den gelir).
READY = "READY"
OPENED = "OPENED"
NO_IDEA = "NO_IDEA"
NO_SIGNAL = "NO_SIGNAL"
SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
ALREADY_OPEN = "ALREADY_OPEN"
RISK_BLOCKED = "RISK_BLOCKED"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

_MANUAL_REASON_STATE = {
    "risk_gate": RISK_BLOCKED,
    "insufficient_balance": RISK_BLOCKED,
    "no_price": DATA_UNAVAILABLE,
    "price_insane": DATA_UNAVAILABLE,
}


class IdeaBlocked(manual_order.ManualOrderError):
    """Fikre özgü ön koşul başarısız — `state` UI durumunu, mesaj gerçek nedeni taşır."""

    def __init__(self, state: str, message: str) -> None:
        super().__init__(message, 409)
        self.state = state


@dataclass(frozen=True)
class Plan:
    symbol: str
    side: str
    timeframe: str
    size_usd: float
    expires_at: datetime


def _parse(ts: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def _human_age(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes // 60} sa {minutes % 60} dk" if minutes >= 60 else f"{minutes} dk"


def _size_multiplier() -> float:
    cfg = (load_thresholds().get("paper_trading") or {}).get("idea_open_size_multiplier")
    try:
        return max(0.0, min(1.0, float(cfg))) if cfg is not None else DEFAULT_SIZE_MULTIPLIER
    except (TypeError, ValueError):
        return DEFAULT_SIZE_MULTIPLIER


def _executable(timeframe: str | None) -> bool:
    """TF pozisyon açabiliyor mu? (timeframe_risk.paper_execution; 1w = yalnız bias)."""
    if timeframe not in _TF_SECONDS:
        return False
    pol = (load_thresholds().get("timeframe_risk") or {}).get(timeframe) or {}
    return bool(pol.get("paper_execution", False))


def signal_max_age(timeframe: str) -> timedelta:
    """Sinyal geçerlilik süresi = max(giriş TF'inin bir barı, keşif taramasının yenileme ritmi).

    Tarayıcı bir adayı en sık `scan.result_ttl_sec` (varsayılan 4 sa) aralıkla yeniden analiz eder;
    süreyi bir barla sınırlamak 1sa/4sa fikirlerini neredeyse hiç onaylanamaz kılardı."""
    ttl = int(((scanner.load_config().get("scan") or {}).get("result_ttl_sec")) or 14400)
    return timedelta(seconds=max(_TF_SECONDS.get(timeframe, 3600), ttl))


def _verdict(state: str, reason: str, **extra: Any) -> dict:
    return {"state": state, "can_open": state == READY, "reason": reason, **extra}


def _signal(idea: dict, board_at: str | None, now: datetime) -> tuple[dict | None, str, datetime | None]:
    """Fikrin sinyal ön koşulları → (engel_verdict | None, yön, bitiş). Yalnız LONG fikir."""
    tech = idea.get("technical") or {}
    news = idea.get("news") or {}
    if tech.get("verdict") != "WOULD_OPEN_LONG":
        return (
            _verdict(NO_SIGNAL, f"teknik teyit yok (hüküm: {tech.get('verdict') or 'yok'}) — "
                                "yalnız haber öngörüsüyle işlem açılmaz"),
            "", None,
        )
    if news.get("direction") == "down":
        return _verdict(NO_SIGNAL, "haber öngörüsü AŞAĞI, teknik yön YUKARI — çelişen sinyal"), "", None
    tf = tech.get("entry_timeframe")
    if not _executable(tf):
        return _verdict(NO_SIGNAL, f"giriş zaman dilimi işlem açmaya uygun değil ({tf or 'belirsiz'})"), "", None
    stamp = _parse(tech.get("checked_at")) or _parse(board_at)
    if stamp is None:
        return _verdict(SIGNAL_EXPIRED, "sinyalin zaman damgası yok — güncelliği doğrulanamadı"), "", None
    expires = stamp + signal_max_age(str(tf))
    if now > expires:
        return (
            _verdict(SIGNAL_EXPIRED, f"{tf} sinyali {_human_age(now - stamp)} önce üretildi; "
                                     f"geçerlilik {_human_age(expires - stamp)} idi"),
            "", expires,
        )
    return None, "long", expires


def _planned_size(ps: paper_state.PaperState, symbol: str, side: str, tf: str, risk_action: str | None,
                  now: datetime) -> tuple[float, str | None]:
    """Planlanan paper boyutu (USD) ve varsa engel nedeni. Çarpanlar yalnız KÜÇÜLTÜR."""
    gate = evaluate_session(symbol, side, tf, now_utc=now, risk_action=risk_action)
    if gate.route == "block":
        return 0.0, f"seans kapısı engelledi: {gate.decision.reason}"
    cluster = correlation.cluster_exposure(ps.open_positions, symbol, side, ps.equity_usd)
    if cluster.size_factor <= 0.0:
        return 0.0, (f"korelasyon kümesi sınırı: aynı yönlü maruziyet %{cluster.cluster_pct:.0%} "
                     f"≥ sınır %{cluster.max_cluster_pct:.0%}")
    mult = _size_multiplier() * min(1.0, gate.effective_multiplier) * min(1.0, cluster.size_factor)
    size = compute_size_usd(mult)
    return (size, None) if size > 0 else (0.0, "hesaplanan pozisyon boyutu sıfır")


def _existing(ps: paper_state.PaperState, symbol: str) -> tuple[str, str] | None:
    """Aynı sembolde açık pozisyon / bekleyen emir (yön ve TF fark etmez) → (kimlik, neden)."""
    for pos in ps.open_positions:
        if pos.symbol == symbol:
            return pos.id, (f"{symbol} için zaten açık pozisyon var ({pos.side}, {pos.timeframe}, "
                            f"kimlik {pos.id}) — ikinci pozisyon açılmaz")
    for order in ps.pending_orders:
        if order.symbol == symbol:
            return order.id, f"{symbol} için bekleyen emir var (kimlik {order.id}) — ikinci emir açılmaz"
    return None


def _portfolio_block(ps: paper_state.PaperState, symbol: str, size_usd: float) -> tuple[str, str] | None:
    """Defter durumundan gelen engeller (kilit İÇİNDE de, dışında da aynı)."""
    existing = _existing(ps, symbol)
    if existing is not None:
        return ALREADY_OPEN, existing[1]
    anomaly = state_anomaly.detect_state(ps)
    if anomaly.detected:
        return RISK_BLOCKED, "defter tutarsız, yeni pozisyon açılmaz: " + "; ".join(anomaly.reasons)
    exposure = sum(float(p.size_usd) for p in ps.open_positions)
    if exposure + size_usd > ps.equity_usd:
        return RISK_BLOCKED, (f"toplam maruziyet {exposure + size_usd:,.0f} USD bakiyeyi "
                              f"({ps.equity_usd:,.0f} USD) aşar")
    max_pos = float((load_thresholds().get("paper_trading") or {}).get("max_position_usd", 0.0))
    if max_pos > 0 and size_usd > max_pos:
        return RISK_BLOCKED, f"pozisyon boyutu {size_usd:,.0f} USD, tek pozisyon sınırı {max_pos:,.0f} USD"
    return None


def _risk_action(ps: paper_state.PaperState, dqs: float) -> tuple[str, str]:
    _ensure_daily_anchor(ps)
    risk = evaluate_risk(
        risk_input_from_state(ps, dqs)
    )
    return risk.action, risk.reason


def _data_block(symbol: str, tf: str, latest: dict | None, now: datetime) -> str | None:
    """Ağ çağrısız veri ön-kontrolü: canlı fiyat kaynağı, OHLCV referansı, taze tick."""
    if not price_provider.has_live_source(symbol):
        return (f"{symbol} için canlı fiyat kaynağı tanımlı değil — paper emri için fiyat alınamaz "
                "(sembol işlem evrenine terfi ettirilmeli)")
    reference, _ = price_sanity.ohlcv_reference_price(symbol, tf)
    if reference is None:
        return f"{symbol} için doğrulanmış OHLCV referansı yok — fiyat doğrulanamaz"
    stamp = _parse((latest or {}).get("generated_at"))
    if stamp is None:
        return "sistem snapshot'ı yok — veri güncelliği doğrulanamaz"
    age = (now - stamp).total_seconds()
    if age > DEFAULT_TICK_STALE_SEC:
        return f"sistem verisi eski ({_human_age(now - stamp)}) — güncel veri bekleniyor"
    # A source/old OHLCV cache alone is not enough for a market paper fill.
    # The opener uses the current snapshot quote; keep the read-only verdict
    # identical so the button cannot advertise READY and then fail silently.
    if "prices" in (latest or {}):
        price_rows = (latest or {}).get("prices")
    elif "data_snapshot" in (latest or {}):
        price_rows = ((latest or {}).get("data_snapshot") or {}).get("prices")
    else:
        price_rows = None
    if price_rows is not None:
        quote = next(
            (
                row
                for row in (price_rows or [])
                if isinstance(row, dict)
                and str(row.get("symbol") or "").upper() == symbol.upper()
            ),
            None,
        )
        if quote is None or float(quote.get("price") or 0.0) <= 0:
            return f"{symbol} için güncel fiyat yok — işlem açılamaz (uydurma fiyat yok)"
        if "verified" in quote and not bool(quote.get("verified")):
            return f"{symbol} için fiyat doğrulanmadı — doğrulanmış veri bekleniyor"
    return None


def evaluate(idea: dict, board_at: str | None, ps: paper_state.PaperState,
             latest: dict | None, now: datetime) -> dict:
    """Bir fikir için ağ çağrısız ön-durum (`paper_open`). Emir AÇMAZ."""
    blocked, side, expires = _signal(idea, board_at, now)
    if blocked is not None:
        return blocked
    symbol = str(idea["symbol"])
    tf = str((idea.get("technical") or {})["entry_timeframe"])
    extra = {"side": side, "timeframe": tf, "expires_at": expires.isoformat() if expires else None}
    existing = _existing(ps, symbol)
    if existing is not None:
        return _verdict(ALREADY_OPEN, existing[1], position_id=existing[0], **extra)
    data = _data_block(symbol, tf, latest, now)
    if data is not None:
        return _verdict(DATA_UNAVAILABLE, data, **extra)
    dqs = float((((latest or {}).get("dqs")) or {}).get("score", 0.0) or 0.0)
    action, why = _risk_action(ps, dqs)
    if action in manual_order.RISK_BLOCKS_NEW_OPEN:
        return _verdict(RISK_BLOCKED, f"RiskGate engelledi: {action} — {why}", **extra)
    size, size_block = _planned_size(ps, symbol, side, tf, action, now)
    if size_block is not None:
        return _verdict(RISK_BLOCKED, size_block, **extra)
    portfolio = _portfolio_block(ps, symbol, size)
    if portfolio is not None:
        return _verdict(portfolio[0], portfolio[1], **extra)
    return _verdict(READY, "doğrulamalar geçti — onayınızla paper pozisyon açılabilir", size_usd=size, **extra)


def annotate_board(view: dict, now: datetime | None = None) -> dict:
    """`GET /ideas` görünümüne fikir başına `paper_open` ekler (ağ çağrısı yok, salt-okuma)."""
    now = now or datetime.now(UTC)
    ps = paper_state.load()
    latest = snapshot_store.latest()
    board_at = view.get("generated_at")
    for idea in view.get("ideas") or []:
        try:
            verdict = evaluate(idea, board_at, ps, latest, now)
        except Exception as exc:  # ön-durum hatası /ideas'ı düşürmez; neden görünür kalır
            verdict = _verdict(DATA_UNAVAILABLE, f"ön-doğrulama yapılamadı: {type(exc).__name__}: {exc}")
        verdict["checked_at"] = now.isoformat()
        idea["paper_open"] = verdict
    return view


def _plan(symbol: str, now: datetime) -> tuple[Plan | None, dict | None]:
    idea, board_at = ideas.find(symbol)
    if idea is None:
        return None, _verdict(NO_IDEA, f"{symbol} fikir panosunda yok (süresi dolmuş ya da kaldırılmış)")
    blocked, side, expires = _signal(idea, board_at, now)
    if blocked is not None or expires is None:
        return None, blocked or _verdict(NO_SIGNAL, "sinyal doğrulanamadı")
    tf = str((idea.get("technical") or {})["entry_timeframe"])
    ps = paper_state.load()
    latest = snapshot_store.latest()
    data = _data_block(symbol, tf, latest, now)
    if data is not None:
        return None, _verdict(DATA_UNAVAILABLE, data)
    action, _ = _risk_action(ps, float((((latest or {}).get("dqs")) or {}).get("score", 0.0) or 0.0))
    size, size_block = _planned_size(ps, symbol, side, tf, action, now)
    if size_block is not None:
        return None, _verdict(RISK_BLOCKED, size_block)
    return Plan(symbol, side, tf, size, expires), None


def _guard(plan: Plan) -> Callable[[paper_state.PaperState, float], None]:
    def check(ps: paper_state.PaperState, size_usd: float) -> None:
        # Kilit İÇİNDE yeniden denetim: yarışta/çift tıklamada ikinci istek burada durur.
        block = _portfolio_block(ps, plan.symbol, size_usd)
        if block is not None:
            raise IdeaBlocked(block[0], block[1])
        if datetime.now(UTC) > plan.expires_at:
            raise IdeaBlocked(SIGNAL_EXPIRED, "sinyal onay sırasında geçerlilik süresini aştı")

    return check


def open_from_idea(symbol: str, now: datetime | None = None) -> dict:
    """Owner onayı: fikri paper pozisyona çevirir. Her sonuç yapılandırılmış döner:
    {"status": "opened"|"blocked", "state", "reason", "position"?}. Gerçek broker emri YOK."""
    now = now or datetime.now(UTC)
    plan, blocked = _plan(symbol, now)
    if blocked is not None or plan is None:
        return {"status": "blocked", **(blocked or _verdict(NO_IDEA, "fikir bulunamadı"))}
    try:
        res = manual_order.place(
            plan.symbol, plan.side, plan.size_usd, timeframe=plan.timeframe, order_type="market",
            open_reason=OPEN_REASON, guard=_guard(plan),
        )
    except IdeaBlocked as exc:
        return {"status": "blocked", **_verdict(exc.state, str(exc))}
    except manual_order.ManualOrderError as exc:
        state = _MANUAL_REASON_STATE.get(exc.reason or "", RISK_BLOCKED)
        return {"status": "blocked", **_verdict(state, str(exc))}
    return {
        "status": "opened", "state": OPENED, "can_open": False,
        "reason": f"{plan.symbol} için paper {plan.side} pozisyon açıldı (gerçek emir yok)",
        "position": {k: res.get(k) for k in (
            "position_id", "symbol", "side", "entry_price", "size_usd", "opened_at", "timeframe", "sl", "tp")},
    }


__all__ = ["OPEN_REASON", "IdeaBlocked", "annotate_board", "evaluate", "open_from_idea", "signal_max_age"]
