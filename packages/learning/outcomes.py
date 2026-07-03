"""L1 — canonical paper-trade outcome record + timeframe-aware aggregation.

Kapalı paper trade'lerden tek **canonical outcome record** türetir. Yeni veri
kaynağı YOK — yalnızca mevcut `Trade` + fingerprint'ten türetir. Legacy kayıtlar
eksik alanlarla gelir → güvenli default (crash yok). Tüm outcome'lar `paper_only`.

PAPER_SAFE / NO_EXECUTION: yalnızca okuma + türetme; emir/karar üretmez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from packages.learning import decision_log
from packages.learning import fingerprint as fp
from packages.paper import state as paper_state
from packages.paper.state import Trade


@dataclass
class CanonicalOutcome:
    trade_id: str
    symbol: str
    timeframe: str
    opened_at: str | None
    closed_at: str | None
    duration_seconds: float | None
    direction: str
    open_price: float | None
    close_price: float | None
    pnl: float
    pnl_pct: float | None
    open_reason: str | None
    close_reason: str | None
    fingerprint: str | None
    regime: str
    dominant_module: str
    candidate_action: str | None
    final_action: str | None
    blocked_by: list[str] = field(default_factory=list)
    gates_applied: list[str] = field(default_factory=list)
    snapshot_id: str | None = None
    decision_id: str | None = None
    data_verified: bool = False
    source_quality: str = "unknown"
    paper_only: bool = True
    # MAE/MFE (TF-target trainer girdisi). Legacy kayıtlar 0.0 default ile gelir.
    mae_pct: float = 0.0
    mfe_pct: float = 0.0
    # Açılış anında damgalanmış KALİBRE güven (Trade + decision_log taşır).
    # Raporlama/reliability yüzeyi bunu okur. Legacy/eksik kayıtlar None.
    predicted_confidence: float | None = None
    # Calibration trainer'ın FIT girdisi — kalibrasyon ÖNCESİ ham güven.
    # predict_calibrated karar anında ham güvene uygulanır; fit de aynı
    # dağılımdan öğrenmeli (predicted ile fit = kendi çıktısıyla eğitim,
    # özyinelemeli kayma). Legacy/eksik kayıtlar None ile gelir (fit'e girmez).
    raw_confidence: float | None = None
    # F1-1 — açılış risk mesafesi |entry−SL|/entry (fraksiyon) ve R-multiple:
    # r = pnl_pct / (risk_pct×100). USD-expectancy pozisyon boyutuyla confound
    # olur (15m küçük poz + 1d büyük poz aynı havuzda); R-katı boyut-bağımsız
    # gerçek edge'i ölçer. Legacy/SL'siz kayıtlar None (uydurma yok).
    risk_pct: float | None = None
    r_multiple: float | None = None
    # Exit-forensics — pozisyon büyüklüğü ($). Kötü çıkışın $ maliyetini KESİN
    # hesaplamak için (notional çıkarımı pnl/(pnl_pct/100) başabaşta çöker).
    # Legacy kayıtlar None (uydurma yok).
    size_usd: float | None = None
    # F1-3 — açılış anındaki consensus modül katkı vektörü (modül → score×weight).
    # dominant_module tek-modül attribution'unun ham verisi; module_attribution()
    # bunu okur. Manuel/legacy açılışlar None.
    module_contributions: dict[str, float] | None = None


def _duration_seconds(opened_at: str | None, closed_at: str | None) -> float | None:
    if not opened_at or not closed_at:
        return None
    try:
        delta = datetime.fromisoformat(closed_at) - datetime.fromisoformat(opened_at)
        return round(delta.total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _pnl_pct(entry: float | None, exit_: float | None, side: str) -> float | None:
    try:
        if not entry or exit_ is None:
            return None
        raw = (exit_ - entry) / entry * 100.0
        return round(raw if side == "long" else -raw, 4)
    except (TypeError, ZeroDivisionError):
        return None


def _final_action(side: str) -> str | None:
    if side == "long":
        return "open_long"
    if side == "short":
        return "open_short"
    return None


def _r_multiple(pnl_pct: float | None, risk_pct: float | None) -> float | None:
    """R-katı: gerçekleşen % hareket / açılıştaki risk mesafesi (%).

    pnl_pct yön-düzeltilmiş % (long/short işareti uygulanmış), risk_pct
    fraksiyon (0.03 = %3). İkisinden biri yoksa None — uydurma yok."""
    if pnl_pct is None or risk_pct is None or risk_pct <= 0:
        return None
    return round((pnl_pct / 100.0) / risk_pct, 4)


def _module_contributions(raw) -> dict[str, float] | None:
    """Modül katkı vektörünü güvenli süz (bozuk değer → alan atlanır)."""
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out or None


def build_outcome(t: Trade) -> CanonicalOutcome:
    """Tek Trade → CanonicalOutcome (legacy default'larla; asla patlamaz)."""
    parsed = fp.parse(getattr(t, "fingerprint", None))
    side = getattr(t, "side", None) or "?"
    timeframe = getattr(t, "timeframe", None) or parsed["timeframe"] or "1d"
    verified = bool(getattr(t, "data_verified", False))
    final = _final_action(side)
    entry = getattr(t, "entry_price", None)
    exit_ = getattr(t, "exit_price", None)
    pnl_pct = _pnl_pct(entry, exit_, side)
    risk_pct = _opt_float(getattr(t, "open_risk_pct", None))
    return CanonicalOutcome(
        trade_id=str(getattr(t, "id", "") or ""),
        symbol=str(getattr(t, "symbol", "") or ""),
        timeframe=timeframe,
        opened_at=getattr(t, "opened_at", None),
        closed_at=getattr(t, "closed_at", None),
        duration_seconds=_duration_seconds(
            getattr(t, "opened_at", None), getattr(t, "closed_at", None)
        ),
        direction=side,
        open_price=entry,
        close_price=exit_,
        pnl=float(getattr(t, "pnl_usd", 0.0) or 0.0),
        pnl_pct=pnl_pct,
        open_reason=getattr(t, "open_reason", None),
        close_reason=getattr(t, "close_reason", None),
        fingerprint=getattr(t, "fingerprint", None),
        regime=parsed["regime"] or "UNKNOWN",
        dominant_module=parsed["dominant_module"] or "unknown",
        # P1 Trade candidate/final/gate attribution taşımıyor → açılmış trade
        # için final == candidate (open_*), bloklanmamış (blocked_by boş).
        candidate_action=final,
        final_action=final,
        blocked_by=[],
        gates_applied=[],
        snapshot_id=getattr(t, "snapshot_id", None),
        decision_id=None,
        data_verified=verified,
        source_quality="verified" if verified else "unverified",
        paper_only=True,
        mae_pct=float(getattr(t, "mae_pct", 0.0) or 0.0),
        mfe_pct=float(getattr(t, "mfe_pct", 0.0) or 0.0),
        predicted_confidence=_opt_float(getattr(t, "predicted_confidence", None)),
        raw_confidence=_opt_float(getattr(t, "raw_confidence", None)),
        risk_pct=risk_pct,
        r_multiple=_r_multiple(pnl_pct, risk_pct),
        size_usd=_opt_float(getattr(t, "size_usd", None)),
        module_contributions=_module_contributions(
            getattr(t, "open_module_contributions", None)
        ),
    )


def _opt_float(value) -> float | None:
    """None-güvenli float dönüşümü (bozuk değer → None, asla patlamaz)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_outcome_from_log_entry(entry: dict) -> CanonicalOutcome:
    """Tek decision_log kaydı → CanonicalOutcome (build_outcome'un dict ikizi).

    decision_log.jsonl, paper_state.recent_trades'in kalıcı (append-only) eşidir
    — recent_trades sadece son 200'lük bir penceredir ve state dosyası bozulup
    sıfırlanırsa (bkz. paper_state.corrupt-*.json yedekleri) bu pencere kaybolur.
    decision_log hiçbir zaman sıfırlanmaz, bu yüzden öğrenme verisinin asıl
    kaynağı budur; recent_trades sadece yazma hatası durumunda yedektir.
    """
    opening = entry.get("opening_signal") or {}
    exit_ = entry.get("exit") or {}
    outcome = entry.get("outcome") or {}
    fingerprint = opening.get("fingerprint")
    parsed = fp.parse(fingerprint)
    side = entry.get("side") or "?"
    timeframe = entry.get("timeframe") or parsed["timeframe"] or "1d"
    verified = bool(opening.get("data_verified", False))
    final = _final_action(side)
    entry_price = outcome.get("entry_price")
    exit_price = outcome.get("exit_price")
    pnl_pct = _pnl_pct(entry_price, exit_price, side)
    risk_pct = _opt_float(outcome.get("risk_pct"))
    return CanonicalOutcome(
        trade_id=str(entry.get("trade_id") or ""),
        symbol=str(entry.get("symbol") or ""),
        timeframe=timeframe,
        opened_at=entry.get("opened_at"),
        closed_at=entry.get("closed_at"),
        duration_seconds=_duration_seconds(entry.get("opened_at"), entry.get("closed_at")),
        direction=side,
        open_price=entry_price,
        close_price=exit_price,
        pnl=float(outcome.get("pnl_usd") or 0.0),
        pnl_pct=pnl_pct,
        open_reason=opening.get("reason"),
        close_reason=exit_.get("reason"),
        fingerprint=fingerprint,
        regime=parsed["regime"] or "UNKNOWN",
        dominant_module=parsed["dominant_module"] or "unknown",
        candidate_action=final,
        final_action=final,
        blocked_by=[],
        gates_applied=[],
        snapshot_id=opening.get("snapshot_id"),
        decision_id=None,
        data_verified=verified,
        source_quality="verified" if verified else "unverified",
        paper_only=True,
        mae_pct=float(outcome.get("mae_pct") or 0.0),
        mfe_pct=float(outcome.get("mfe_pct") or 0.0),
        predicted_confidence=_opt_float(opening.get("predicted_confidence")),
        raw_confidence=_opt_float(opening.get("raw_confidence")),
        risk_pct=risk_pct,
        r_multiple=_r_multiple(pnl_pct, risk_pct),
        size_usd=_opt_float(outcome.get("size_usd")),
        module_contributions=_module_contributions(opening.get("module_contributions")),
    )


def outcomes_from_state(
    state: paper_state.PaperState | None = None,
) -> list[CanonicalOutcome]:
    """recent_trades (volatile pencere) + decision_log (kalıcı kayıt) birleşimi.

    recent_trades öncelikli kaynaktır (mevcut davranış birebir korunur — id
    çakışsa bile hepsi sayılır). decision_log her kapanışta recent_trades ile
    birlikte yazılır (bkz. packages/paper/lifecycle.py); recent_trades'te
    OLMAYAN trade_id'leri (örn. paper_state.json bozulup sıfırlandıysa, bkz.
    paper_state.corrupt-*.json yedekleri) decision_log'dan kurtarıp ekliyoruz —
    veri kaybı yok.
    """
    s = state if state is not None else paper_state.load()
    primary = [build_outcome(t) for t in s.recent_trades]
    known_ids = {o.trade_id for o in primary if o.trade_id}
    recovered: list[CanonicalOutcome] = []
    for raw in decision_log.read_recent(limit=decision_log.DEFAULT_MAX_READ):
        try:
            o = build_outcome_from_log_entry(raw)
        except Exception:  # bozuk/eksik kayıt → atla, worker patlamasın
            continue
        if o.trade_id and o.trade_id not in known_ids:
            known_ids.add(o.trade_id)
            recovered.append(o)
    return primary + recovered


def outcome_to_dict(o: CanonicalOutcome) -> dict:
    return asdict(o)


# --------------------------------------------------------------------------
# Timeframe-aware aggregation — 15m outcome'u 1d bucket'ını ETKİLEMEZ.
# --------------------------------------------------------------------------

def _empty_bucket() -> dict:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        # F1-2 — başabaş (pnl==0, örn. time-stop BE çıkışı) ayrı sayılır;
        # eskiden loss sayılıp win_rate'i suni düşürüyordu.
        "breakeven": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "verified": 0,
        # F1-1 — R-multiple istatistikleri (yalnız r_multiple taşıyan outcome'lar;
        # legacy/SL'siz kayıtlar r_trades'e girmez — USD alanları herkes için sürer).
        "r_trades": 0,
        "total_r": 0.0,
        "avg_r": 0.0,
    }


def bucketize(outcomes: list[CanonicalOutcome], key) -> dict[str, dict]:
    """`key(outcome) -> str` ile grupla; bucket başına istatistik üret.

    F1-2 — win_rate paydası KARARLI trade'lerdir (wins+losses); başabaş
    (pnl==0) ayrı `breakeven` sayacında izlenir, win_rate'i sulandırmaz."""
    acc: dict[str, dict] = {}
    for o in outcomes:
        k = key(o)
        b = acc.setdefault(str(k if k is not None else "unknown"), _empty_bucket())
        b["trades"] += 1
        if o.pnl > 0:
            b["wins"] += 1
        elif o.pnl < 0:
            b["losses"] += 1
        else:
            b["breakeven"] += 1
        b["total_pnl"] = round(b["total_pnl"] + o.pnl, 2)
        if o.data_verified:
            b["verified"] += 1
        if o.r_multiple is not None:
            b["r_trades"] += 1
            b["total_r"] = round(b["total_r"] + o.r_multiple, 4)
    for b in acc.values():
        n = b["trades"]
        decided = b["wins"] + b["losses"]
        b["win_rate"] = round(b["wins"] / decided, 3) if decided else 0.0
        b["avg_pnl"] = round(b["total_pnl"] / n, 2) if n else 0.0
        b["avg_r"] = round(b["total_r"] / b["r_trades"], 4) if b["r_trades"] else 0.0
    return acc


def breakdowns(outcomes: list[CanonicalOutcome]) -> dict[str, dict]:
    return {
        "by_timeframe": bucketize(outcomes, lambda o: o.timeframe),
        "by_symbol": bucketize(outcomes, lambda o: o.symbol),
        "by_regime": bucketize(outcomes, lambda o: o.regime),
        "by_dominant_module": bucketize(outcomes, lambda o: o.dominant_module),
        "by_close_reason": bucketize(outcomes, lambda o: o.close_reason or "unknown"),
    }


def distribution(outcomes: list[CanonicalOutcome], key) -> dict[str, int]:
    """Sadece sayım (trainer evidence'ı için kompakt dağılım)."""
    out: dict[str, int] = {}
    for o in outcomes:
        k = str(key(o) if key(o) is not None else "unknown")
        out[k] = out.get(k, 0) + 1
    return out


def module_attribution(outcomes: list[CanonicalOutcome]) -> dict[str, dict]:
    """F1-3 — modül katkı vektöründen kazanç/kayıp attribution'u.

    dominant_module tüm sonucu TEK modüle yazar (skor bir karışımken); bu rapor
    her modülün kazanan ve kaybeden trade'lerdeki ORTALAMA katkısını (score×weight)
    yan yana koyar — "kazananlarda katkısı yüksek, kaybedenlerde düşük" modül
    gerçek edge taşıyandır. Yalnız vektör taşıyan outcome'lar girer (legacy/
    manuel None → dışarıda); başabaş (pnl==0) karara girmez (F1-2 ile tutarlı).
    Salt-okuma raporu — hiçbir karar/ağırlık BU fonksiyondan beslenmez (F3'te
    regresyon tabanı olacak ham veri yüzeyi)."""
    acc: dict[str, dict] = {}
    for o in outcomes:
        if not o.module_contributions or o.pnl == 0:
            continue
        won = o.pnl > 0
        for mod, contrib in o.module_contributions.items():
            m = acc.setdefault(mod, {
                "win_trades": 0, "loss_trades": 0,
                "_win_contrib_sum": 0.0, "_loss_contrib_sum": 0.0,
            })
            if won:
                m["win_trades"] += 1
                m["_win_contrib_sum"] += contrib
            else:
                m["loss_trades"] += 1
                m["_loss_contrib_sum"] += contrib
    out: dict[str, dict] = {}
    for mod, m in acc.items():
        wn, ln = m["win_trades"], m["loss_trades"]
        out[mod] = {
            "win_trades": wn,
            "loss_trades": ln,
            "avg_contrib_win": round(m["_win_contrib_sum"] / wn, 3) if wn else None,
            "avg_contrib_loss": round(m["_loss_contrib_sum"] / ln, 3) if ln else None,
        }
    return out
