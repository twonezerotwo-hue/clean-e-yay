"""R2 — deterministic rolling replay / backtest runner.

Stored snapshot serisi (`snapshot_store`) üzerinde **deterministik** outcome
ölçümü. Hard kurallar:

- Yalnızca diske kaydedilmiş GERÇEK snapshot'lar okunur — live provider refetch
  YOK, sahte geçmiş üretilmez.
- Karar yalnızca KENDİ snapshot'ının verisinden gelir (decision_matrix). Outcome
  yalnızca GERÇEKTEN var olan GELECEK snapshot'larla ölçülür → look-ahead bias
  YOK (gelecekteki snapshot, karar zamanından *sonra* gelen ilk gözlem).
- Gelecek snapshot yoksa dürüstçe ``insufficient_future_data`` denir; hiç
  snapshot yoksa ``insufficient_snapshots``.
- PAPER_SAFE / NO_EXECUTION: runner emir üretmez, paper pozisyon açmaz,
  RiskGate'i bypass etmez, decide_matrix'i yeniden çalıştırmaz (kayıtlı kararı
  kullanır). Saf fonksiyon: store dict'lerini okur, metrik döner.

Outcome: her karar hücresi (symbol, timeframe) için 15m/1h/4h/1d horizon'da,
karar zamanından sonraki İLK snapshot'ın fiyatıyla ölçülür. Sinyal yönünde
(open_long/open_short) realize getiri hesaplanır; bloklanmış ama aday-açılışı
olan hücreler counterfactual olarak değerlendirilir (blok doğru muydu?).
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from packages.data import snapshot_store

# Algoritma versiyonu — metrik/run_id semantiği değişirse artır (drift guard).
ALGO_VERSION = 1

# (ad, saniye) — outcome ölçüm horizon'ları.
HORIZONS: tuple[tuple[str, int], ...] = (
    ("15m", 900),
    ("1h", 3600),
    ("4h", 14400),
    ("1d", 86400),
)
_HORIZON_NAMES = [name for name, _ in HORIZONS]

_OPEN_LONG = "open_long"
_OPEN_SHORT = "open_short"
_NO_EXEC = "no_live_execution"

STATUS_OK = "ok"
STATUS_NO_SNAPSHOTS = "insufficient_snapshots"
STATUS_NO_FUTURE = "insufficient_future_data"


def _epoch(value: object) -> float | None:
    """ISO `generated_at` → karşılaştırılabilir epoch sn (naive → UTC kabul)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _prices(doc: dict) -> dict[str, float]:
    """Snapshot'ın doğrulanabilir fiyat haritası (>0 olanlar)."""
    out: dict[str, float] = {}
    for q in ((doc.get("data_snapshot") or {}).get("prices") or []):
        if not isinstance(q, dict):
            continue
        sym = q.get("symbol")
        px = q.get("price")
        if sym and isinstance(px, (int, float)) and not isinstance(px, bool) and px > 0:
            out[str(sym)] = float(px)
    return out


def _cells(doc: dict) -> list[dict]:
    cells = (doc.get("decision_matrix") or {}).get("cells") or []
    return [c for c in cells if isinstance(c, dict)]


def _dir(action: object) -> int:
    """Sinyal yönü: +1 long / -1 short / 0 yön yok."""
    if action == _OPEN_LONG:
        return 1
    if action == _OPEN_SHORT:
        return -1
    return 0


def _future_price(seq: list[tuple], i: int, target: float, symbol: str) -> float | None:
    """Karar zamanından sonraki, target horizon'a İLK ulaşan snapshot'ın fiyatı.

    Look-ahead yok: ilk `epoch >= target` snapshot seçilir; o snapshot'ta fiyat
    yoksa ileriye atlanmaz (cherry-pick yasak) → None (insufficient_future_data).
    """
    for j in range(i + 1, len(seq)):
        if seq[j][0] >= target:
            return seq[j][2].get(symbol)
    return None


def _empty_metrics() -> dict:
    return {
        "signals_evaluated": 0,
        "hits": 0,
        "hit_rate": None,
        "false_positive": 0,
        "false_positive_rate": None,
        "false_negative": 0,
        "false_negative_rate": None,
        "suppressed_evaluated": 0,
        "avg_return": None,
        "max_drawdown": None,
        "blocked_decision_accuracy": None,
    }


def _metrics(signals: list[dict], suppressed: list[dict]) -> dict:
    """Bir sinyal/bloklama kümesinden metrik seti (saf, deterministik).

    `signals` zaten kronolojik sıralı varsayılır (drawdown equity eğrisi için).
    """
    n = len(signals)
    if n == 0 and not suppressed:
        return _empty_metrics()

    hits = sum(1 for s in signals if s["hit"])
    fp = n - hits
    returns = [s["signed_return"] for s in signals]
    avg = sum(returns) / n if n else None

    # Equity eğrisi = sinyal getirilerinin kümülatif toplamı; max drawdown =
    # zirveden en derin düşüş (pozitif sayı).
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)

    sup_n = len(suppressed)
    fn = sum(1 for s in suppressed if s["missed"])
    blocked_correct = sum(1 for s in suppressed if s["blocked_correct"])

    return {
        "signals_evaluated": n,
        "hits": hits,
        "hit_rate": round(hits / n, 4) if n else None,
        "false_positive": fp,
        "false_positive_rate": round(fp / n, 4) if n else None,
        "false_negative": fn,
        "false_negative_rate": round(fn / sup_n, 4) if sup_n else None,
        "suppressed_evaluated": sup_n,
        "avg_return": round(avg, 6) if avg is not None else None,
        "max_drawdown": round(mdd, 6) if n else None,
        "blocked_decision_accuracy": (
            round(blocked_correct / sup_n, 4) if sup_n else None
        ),
    }


def _grouped(records: list[dict], key: str) -> dict:
    """records (signal+suppressed birleşik) → key bazında metrik sözlüğü."""
    groups: dict[str, dict[str, list[dict]]] = {}
    for rec in records:
        bucket = groups.setdefault(rec[key], {"signals": [], "suppressed": []})
        if rec["kind"] == "signal":
            bucket["signals"].append(rec)
        else:
            bucket["suppressed"].append(rec)
    return {
        k: _metrics(v["signals"], v["suppressed"])
        for k, v in sorted(groups.items())
    }


def _run_id(seq: list[tuple]) -> str:
    """Sıralı snapshot kümesi + horizon + algo versiyonundan deterministik id.

    Store değişmediği sürece aynı; değişince farklı → `{run_id}` endpoint'i
    bayat run isteğini dürüstçe reddedebilir (saklanan sahte geçmiş yok).
    """
    h = hashlib.sha256()
    h.update(f"v{ALGO_VERSION}".encode())
    for name, sec in HORIZONS:
        h.update(f"|{name}:{sec}".encode())
    for _e, doc, _px in seq:
        h.update(f"|{doc.get('snapshot_id')}@{doc.get('generated_at')}".encode())
    return h.hexdigest()[:16]


def run_backtest() -> dict:
    """Stored snapshot serisi üzerinde deterministik rolling backtest.

    Live provider çağırmaz, decide_matrix'i yeniden çalıştırmaz, paper açmaz.
    Dürüst durum: hiç snapshot yoksa insufficient_snapshots; ölçülebilir
    gelecek yoksa insufficient_future_data.
    """
    docs = snapshot_store.all_docs()

    seq: list[tuple[float, dict, dict[str, float]]] = []
    for doc in docs:
        epoch = _epoch(doc.get("generated_at"))
        if epoch is None:
            continue
        seq.append((epoch, doc, _prices(doc)))
    seq.sort(key=lambda x: x[0])

    run_id = _run_id(seq)
    snapshot_count = len(docs)
    window = None
    if seq:
        window = {
            "from": seq[0][1].get("generated_at"),
            "to": seq[-1][1].get("generated_at"),
        }

    base = {
        "run_id": run_id,
        "algo_version": ALGO_VERSION,
        "execution": _NO_EXEC,
        "snapshot_count": snapshot_count,
        "usable_snapshot_count": len(seq),
        "horizons": list(_HORIZON_NAMES),
        "window": window,
    }

    if snapshot_count == 0:
        return {
            **base,
            "status": STATUS_NO_SNAPSHOTS,
            "available": False,
            "reason": (
                "insufficient_snapshots — store boş; tick_worker çalışınca "
                "snapshot birikir. Sahte geçmiş üretilmez."
            ),
            "evaluated_snapshots": 0,
            "metrics": _empty_metrics(),
            "per_timeframe": {},
            "per_symbol": {},
            "per_horizon": {},
            "coverage": _coverage(0, 0, {}, 0),
        }

    signals: list[dict] = []
    suppressed: list[dict] = []
    insufficient_future: dict[str, int] = dict.fromkeys(_HORIZON_NAMES, 0)
    skipped_no_base = 0
    evaluated_decision_epochs: set[float] = set()

    for i, (epoch_i, doc_i, px_i) in enumerate(seq):
        for cell in _cells(doc_i):
            symbol = cell.get("symbol")
            timeframe = cell.get("timeframe")
            if not symbol or not timeframe:
                continue
            base_price = px_i.get(str(symbol))
            sig_dir = _dir(cell.get("action"))
            cand_dir = _dir(cell.get("candidate_action"))
            is_signal = sig_dir != 0
            # Bastırılmış aday: açılış adayıydı ama final sinyal değil
            # (blocked / hold'a düştü) → counterfactual değerlendirme.
            is_suppressed = (not is_signal) and cand_dir != 0
            if not (is_signal or is_suppressed):
                continue
            if base_price is None or base_price <= 0:
                skipped_no_base += 1
                continue

            for name, sec in HORIZONS:
                future_price = _future_price(seq, i, epoch_i + sec, str(symbol))
                if future_price is None or future_price <= 0:
                    insufficient_future[name] += 1
                    continue
                fwd = (future_price - base_price) / base_price
                evaluated_decision_epochs.add(epoch_i)
                if is_signal:
                    signed = sig_dir * fwd
                    signals.append({
                        "kind": "signal",
                        "epoch": epoch_i,
                        "symbol": str(symbol),
                        "timeframe": str(timeframe),
                        "horizon": name,
                        "signed_return": signed,
                        "hit": signed > 0,
                    })
                else:  # suppressed counterfactual
                    cf = cand_dir * fwd
                    suppressed.append({
                        "kind": "suppressed",
                        "epoch": epoch_i,
                        "symbol": str(symbol),
                        "timeframe": str(timeframe),
                        "horizon": name,
                        "cf_return": cf,
                        # Blok doğru: alınsaydı kâr etmezdi (<=0).
                        "blocked_correct": cf <= 0,
                        # False negative: blok kazanan bir işlemi bastırdı.
                        "missed": cf > 0,
                    })

    # Drawdown/equity için kronolojik determinizm.
    signals.sort(key=lambda s: (s["epoch"], s["symbol"], s["timeframe"], s["horizon"]))
    suppressed.sort(
        key=lambda s: (s["epoch"], s["symbol"], s["timeframe"], s["horizon"])
    )
    records = signals + suppressed

    evaluated_any = bool(signals or suppressed)
    status = STATUS_OK if evaluated_any else STATUS_NO_FUTURE
    if status == STATUS_NO_FUTURE:
        reason = (
            "insufficient_future_data — kararlardan sonra ölçülebilir gelecek "
            "snapshot yok (tek snapshot veya horizon'a ulaşan kayıt yok). "
            "Sahte gelecek üretilmez."
        )
    else:
        reason = (
            "Deterministik rolling backtest: kayıtlı snapshot serisi üzerinde "
            "outcome ölçüldü. Live refetch yok, paper açılmadı, RiskGate bypass "
            "yok. Eksik gelecek dürüstçe insufficient_future_data sayıldı."
        )

    return {
        **base,
        "status": status,
        "available": evaluated_any,
        "reason": reason,
        "evaluated_snapshots": len(evaluated_decision_epochs),
        "metrics": _metrics(signals, suppressed),
        "per_timeframe": _grouped(records, "timeframe"),
        "per_symbol": _grouped(records, "symbol"),
        "per_horizon": _grouped(records, "horizon"),
        "coverage": _coverage(
            len(signals), len(suppressed), insufficient_future, skipped_no_base
        ),
    }


def _coverage(
    signals: int, suppressed: int, insufficient_future: dict[str, int], no_base: int
) -> dict:
    return {
        "signals_evaluated": signals,
        "suppressed_evaluated": suppressed,
        "insufficient_future_data": {
            "total": sum(insufficient_future.values()),
            "per_horizon": dict(insufficient_future),
        },
        "skipped_no_base_price": no_base,
    }


__all__ = ["ALGO_VERSION", "HORIZONS", "run_backtest"]
