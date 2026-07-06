"""R5 — tf_scoring_v2 GÖLGE YARIŞ DEFTERİ (İZOLE, salt-gözlem).

D6/R4 gölge üreticisi her cycle "yeni beyin" (rejim-anahtarlı v2) yönünü ÜRETİR
ama o yönün DOĞRU çıkıp çıkmadığını kimse tutmuyordu. Bu modül o eksik halkayı
kapatır: her yeni konuşan-bar kapanışında gölge yönünü fiyat damgasıyla DEFTERE
yazar, ufuk dolunca barı gerçekleşen ileri-getiriyle ÇÖZER ve ÜÇ tasarımı yan
yana puanlar:

    yeni beyin (regime_directed)   — rejim-anahtarlı v2 yönü (BİRİNCİL)
    kontrol   (blend_legacy)       — eski yumuşak harman (A/B kontrol grubu)
    taban     (buy-hold)           — "hep yukarı de" (boğa yanlılığı kontrolü)

Rapor "yeni beyin eskiyi/tabanı geçiyor mu"yu SAYIYA bağlar. Kriter tutarsa
`promotion_rail` ile OWNER ONAY PAKETİ sunulur — terfi OTOMATİK DEĞİL (KIRMIZI
ÇİZGİ: yön motoru terfisi owner onayı ŞART; onay bile canlı yönü değiştirmez).

Sözleşme (mevcut gölge/terfi desenleri):
- Flag `TF_SCORING_V2_SHADOW` (gölgeyle AYNI kapı — gölge yoksa yarış yoktur);
  yeni env-flag YOK (flag-sync yükü yok). Eşikler `tf_scoring_race` YAML bloğunda.
- Defter append-only JSONL; çözüm STATELESS: rapor her koşuda son N satırı arşive
  karşı yeniden çözer (mutasyon yok → replay-dostu, davranış-nötr).
- Karneyle AYNI birleşik pencere (arşiv + canlı) + AYNI ufuk → tutarlı ölçüm.
- ASLA raise etmez; canlı skora/karara/paper'a SIFIR dokunuş.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds
from packages.learning import promotion_rail as rail
from packages.learning import tf_scoring_shadow

_LEDGER = "data/runtime/tf_scoring_race.jsonl"
_REPORT = "data/runtime/tf_scoring_race_report.json"
_ENGINE = "tf_scoring_race_v1"

# Konuşan TF → ileri-getiri ufku (bar). subsignal_scorecard._HORIZON ile AYNI
# değerler (aynı ölçüm bilimi); regime_directed yalnız 1d/4h konuşur.
_HORIZON = {"1d": 5, "4h": 6}
# Rejim → konuşan TF (v2 regime_directed ile aynı eşleme).
_SPEAKER = {"UP": "1d", "DOWN": "4h"}
# Çözümde okunacak azami satır (defter büyüse de bellek/pencere sınırlı).
_MAX_READ = 5000

_DEFAULTS = {
    "min_resolved": 30,       # kararlı çözülmüş yeni-beyin çağrısı (terfi kapısı)
    "neutral_band_pct": 0.5,  # |ileri-getiri| bu bandın altındaysa "kararsız" (elenir)
}


def cfg() -> dict:
    try:
        raw = load_thresholds().get("tf_scoring_race") or {}
        return {
            "min_resolved": max(1, int(raw.get("min_resolved", _DEFAULTS["min_resolved"]))),
            "neutral_band_pct": max(
                0.0, float(raw.get("neutral_band_pct", _DEFAULTS["neutral_band_pct"]))
            ),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return dict(_DEFAULTS)


def ledger_path() -> Path:
    return Path(os.environ.get("TF_SCORING_RACE_LEDGER", _LEDGER))


def report_path() -> Path:
    return Path(os.environ.get("TF_SCORING_RACE_REPORT", _REPORT))


# ── defter yazımı ────────────────────────────────────────────────────────────

def _tail(path: Path, limit: int) -> list[str]:
    """Dosyanın son `limit` satırı (sondan chunk'la; tam-dosya okuma yok)."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    chunks: list[bytes] = []
    newlines = 0
    try:
        with path.open("rb") as fh:
            pos = size
            while pos > 0 and newlines <= limit:
                step = min(1_048_576, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step)
                chunks.append(chunk)
                newlines += chunk.count(b"\n")
    except OSError:
        return []
    data = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return data.splitlines()[-max(1, limit):]


def read_ledger(limit: int = _MAX_READ) -> list[dict]:
    """Son `limit` defter satırı (en yeni en sonda); bozuk satır atlanır."""
    path = ledger_path()
    if not path.exists():
        return []
    out: list[dict] = []
    for line in _tail(path, limit):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def append_ledger(artifact: dict | None = None) -> int:
    """Gölge artifact'ından her sembolün konuşan-bar çağrısını deftere ekle.

    (symbol, speaker_tf, bar_ts) bazında DEDUPE: aynı bar için ikinci kez yazmaz
    (5-dk cycle'lar aynı barı tekrar tekrar üretir). Yalnız yeni kapanan bar →
    yeni satır. best-effort; asla raise etmez. Eklenen satır sayısını döner."""
    if artifact is None:
        artifact = _load_shadow_artifact()
    per_symbol = (artifact or {}).get("per_symbol") or {}
    if not per_symbol:
        return 0
    recent = read_ledger(200)
    seen = {(r.get("symbol"), r.get("speaker_tf"), r.get("bar_ts")) for r in recent}
    rows: list[dict] = []
    for sym, r in per_symbol.items():
        if r.get("status") != "OK" or r.get("direction") is None:
            continue
        regime = ((r.get("regime") or {}).get("regime")) if r.get("regime") else None
        speaker = _SPEAKER.get(regime or "")
        mark = (r.get("bar_marks") or {}).get(speaker or "")
        if speaker is None or not mark or mark.get("close") in (None, 0):
            continue
        key = (sym, speaker, mark.get("ts"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "ts": datetime.now(UTC).isoformat(),
            "symbol": sym,
            "speaker_tf": speaker,
            "regime": regime,
            "bar_ts": mark.get("ts"),
            "price_at": mark.get("close"),
            "new_dir": r.get("direction"),
            "legacy_dir": r.get("direction_blend_legacy"),
        })
    if rows:
        _write_ledger(rows)
    return len(rows)


def _write_ledger(rows: list[dict]) -> None:
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # gözlem ASLA cycle'ı kesmez


def _load_shadow_artifact() -> dict:
    try:
        path = tf_scoring_shadow.artifact_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


# ── çözümleme + puanlama ─────────────────────────────────────────────────────

def _forward_pct(row: dict) -> float | None:
    """Defter satırının konuşan-bar'ından `H` bar sonraki gerçekleşen ileri-getiri
    (%). Arşivde yeterli ileri bar yoksa None (henüz ÇÖZÜLMEDİ — dürüst)."""
    from packages.data.providers.ohlcv import get_bars, history

    tf = row.get("speaker_tf")
    horizon = _HORIZON.get(tf or "")
    base = row.get("price_at")
    if horizon is None or not base:
        return None
    try:
        bars = history.merged(history.load(row["symbol"], tf), get_bars(row["symbol"], tf) or [])
    except Exception:
        return None
    idx = next((i for i, b in enumerate(bars) if b.ts.isoformat() == row.get("bar_ts")), None)
    if idx is None or idx + horizon >= len(bars):
        return None
    fwd = bars[idx + horizon].close
    return (fwd - base) / base * 100.0


def _sign(x: float | None) -> int:
    if x is None or x == 0:
        return 0
    return 1 if x > 0 else -1


def _blank_design() -> dict:
    return {"decisive": 0, "hits": 0, "returns": []}


def _score(rows: list[dict], band: float) -> dict:
    """Çözülebilen satırları üç tasarım için puanla. `band` altı hareket kararsız
    (elenir — düz piyasada yön çağrısı notlanamaz)."""
    designs = {"new_brain": _blank_design(), "legacy": _blank_design(), "baseline": _blank_design()}
    per_regime: dict[str, dict] = {}
    resolved = 0
    for row in rows:
        fwd = _forward_pct(row)
        if fwd is None:
            continue
        resolved += 1
        if abs(fwd) < band:
            continue  # kararsız — hiçbir tasarım notlanmaz
        calls = {
            "new_brain": _sign(row.get("new_dir")),
            "legacy": _sign(row.get("legacy_dir")),
            "baseline": 1,  # buy-hold: her zaman yukarı
        }
        reg = row.get("regime") or "?"
        rbucket = per_regime.setdefault(reg, {
            "new_brain": _blank_design(), "legacy": _blank_design(), "baseline": _blank_design(),
        })
        for name, call in calls.items():
            if call == 0:
                continue  # yön yok (ör. eski-harman None) → o tasarım bu satırı atlar
            aligned = fwd if call > 0 else -fwd
            for tgt in (designs[name], rbucket[name]):
                tgt["decisive"] += 1
                tgt["hits"] += 1 if aligned > 0 else 0
                tgt["returns"].append(aligned)
    return {
        "resolved": resolved,
        "designs": {k: _summ(v) for k, v in designs.items()},
        "per_regime": {
            reg: {k: _summ(v) for k, v in d.items()} for reg, d in sorted(per_regime.items())
        },
    }


def _summ(d: dict) -> dict:
    n = d["decisive"]
    returns = d["returns"]
    return {
        "decisive": n,
        "hits": d["hits"],
        "hit_rate": round(d["hits"] / n, 4) if n else None,
        "avg_return_pct": round(sum(returns) / n, 4) if n else None,
    }


def evaluate() -> dict:
    """Yarış raporu (pure-ish; defter + arşiv okur). Owner paketi girdisi."""
    c = cfg()
    rows = read_ledger()
    scored = _score(rows, c["neutral_band_pct"])
    designs = scored["designs"]
    new_d, leg_d, base_d = designs["new_brain"], designs["legacy"], designs["baseline"]

    beats_baseline = _beats(new_d["avg_return_pct"], base_d["avg_return_pct"])
    beats_legacy = _beats(new_d["avg_return_pct"], leg_d["avg_return_pct"])

    checks = {
        "resolved_decisive": rail.count_check(new_d["decisive"], c["min_resolved"]),
        "ci_disjoint": rail.wilson_check(
            new_d["hits"], new_d["decisive"], rate_key="new_brain_hit_rate"
        ),
        "beats_baseline": {
            "new_avg_return_pct": new_d["avg_return_pct"],
            "baseline_avg_return_pct": base_d["avg_return_pct"],
            "required": "new_avg > baseline_avg",
            "pass": bool(beats_baseline),
        },
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": _ENGINE,
        # Terfi statüsü: READY/NOT_READY. Anahtar `race_status` (endpoint zarfının
        # OK/NO_DATA `status`'uyla çakışmasın — worker-meta *_status deseni).
        "race_status": rail.status_of(checks),
        "ledger_rows": len(rows),
        "resolved": scored["resolved"],
        "designs": designs,
        "per_regime": scored["per_regime"],
        "beats_baseline": beats_baseline,
        "beats_legacy": beats_legacy,
        "checks": checks,
        "config": c,
        "note": (
            "READY = owner onay paketi (governor önerisi) üretilir; yön motoru "
            "terfisi OTOMATİK DEĞİL — KIRMIZI ÇİZGİ (onay bile canlı yönü değiştirmez)."
        ),
    }


def _beats(a: float | None, b: float | None) -> bool | None:
    if a is None or b is None:
        return None
    return a > b


def _write_report(payload: dict) -> None:
    try:
        path = report_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def run() -> dict:
    """learning_worker adımı (gölgeyle AYNI kapı): defteri güncelle → çöz+raporla →
    yaz; READY ise governor defterine owner-onay paketi sun (submit dedupe'lu).
    Gölge flag'i KAPALIYKEN tam no-op."""
    if not tf_scoring_shadow.enabled():
        return {"status": "DISABLED"}
    appended = append_ledger()
    report = evaluate()
    _write_report(report)
    if report["race_status"] == "READY":
        ci = report["checks"]["ci_disjoint"]
        submitted = rail.submit_enable(
            title="Yeni beyin (rejim-anahtarlı v2 yön) yarış kriterini karşıladı",
            summary=(
                f"Kararlı çözülmüş çağrı ≥ eşik + yeni-beyin isabeti {ci['new_brain_hit_rate']} "
                f"(%95 alt sınır {ci['wilson_low']} > 0.5) + tabanı geçti "
                f"(yeni {report['designs']['new_brain']['avg_return_pct']}% > "
                f"taban {report['designs']['baseline']['avg_return_pct']}%). "
                "Terfi OTOMATİK DEĞİL — owner inceleyip ayrı işle yürütür (KIRMIZI ÇİZGİ)."
            ),
            evidence={k: v for k, v in report.items() if k != "note"},
            requested_change={"promote_tf_scoring_v2_direction": True},
            rollback_plan="Paket reddedilir/silinir; canlı yön motoru değişmemiştir.",
            source="tf_scoring_race",
        )
        report["proposal_id"] = (submitted or {}).get("proposal_id")
    return {
        "status": "OK",
        "appended": appended,
        "ledger_rows": report["ledger_rows"],
        "resolved": report["resolved"],
        "race_status": report["race_status"],
    }


__all__ = [
    "append_ledger",
    "cfg",
    "evaluate",
    "ledger_path",
    "read_ledger",
    "report_path",
    "run",
]
