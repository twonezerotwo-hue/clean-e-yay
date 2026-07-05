"""B-3 — Challenger ağırlık eğitimi + quantum ayrım karnesi (cat 6).

Amaç (owner kararı 2026-07-05): B-2'nin ürettiği rejim-çeşitli GERÇEK-veri
challenger outcome'larıyla (`backtest_challenger.jsonl`) rejim başına CHALLENGER
ağırlık seti eğit + quantum'un rejim-bazlı AYRIM karnesini çıkar (cat 6'nın
doğrudan cevabı: quantum boğa/ayı/kriz'de ayrım yapıyor mu?).

PAZARLIKSIZ İZOLASYON:
- Eğitim/öneri matematiği CANLI `auto_weight_trainer`'ın KENDİSİDİR (kopya yok →
  drift yok): `_module_score`/`_loss_aware_score`/`_propose_for_regime` reuse.
- Canlı ağırlığa / config'e / paper state'e ASLA yazmaz — yalnız izole rapor
  `backtest_challenger_report.json`. Champion (canlı) ağırlıkla SHADOW kıyas
  (delta). Owner terfi (B-4) AYRI; oto-uygulama YOK (KIRMIZI ÇİZGİ).
- win_rate = WIN / (WIN + LOSS): FLAT (nötr/ölü-bant) paydadan düşer — codebase
  konvansiyonu (başabaş kayıp değil; win_rate paydası wins+losses).

Quantum karnesi quantum'un DOMINANT olmasına bağlı DEĞİL (ağırlığı 0.1 → nadiren
baskın); skoru HER kaydın `module_contributions`'ından okunur → rejimde quantum
skoru ile forward-return ayrımı ölçülür (ayrı yüzey; attribution değil).

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_active_weights
from packages.learning import auto_weight_trainer as awt
from packages.learning import backtest_recon
from packages.learning.auto_weight_trainer import ModulePerf, WeightDelta

_DEFAULT_REPORT = "data/runtime/backtest_challenger_report.json"
# Quantum ayrım eşikleri (consensus bandıyla aynı ruh: >55 bullish, <45 bearish).
_Q_BULL, _Q_BEAR = 55.0, 45.0
# Karne için rejim başına minimum kayıt (gürültü freni).
_MIN_SCORECARD_N = 8
# Ayrım anlamlılık eşiği (forward-return puanı; separation bunun üstündeyse ayırt).
_SEP_EPS = 0.002


def _report_path() -> Path:
    return Path(os.environ.get("BACKTEST_CHALLENGER_REPORT_PATH", _DEFAULT_REPORT))


def _known_regimes() -> list[str]:
    return list((load_active_weights().get("regimes") or {}).keys())


# --------------------------------------------------------------- ağırlık eğitimi

def _perfs_for(records: list[dict]) -> list[ModulePerf]:
    """Bir rejimin kayıtlarından modül-bazlı performans — CANLI skor fonksiyonları
    reuse. Bucketleme `dominant_module` alanından (fingerprint round-trip yok).
    win_rate = WIN/(WIN+LOSS); FLAT paydadan düşer ama profit-factor için WIN/LOSS
    directional_return'leri kullanılır."""
    by_module: dict[str, list[dict]] = {}
    for r in records:
        mod = r.get("dominant_module")
        if mod and r.get("directional_return") is not None:
            by_module.setdefault(str(mod), []).append(r)

    loss_aware = awt._loss_aware_enabled()
    perfs: list[ModulePerf] = []
    for mod, items in by_module.items():
        n = len(items)
        if n < awt.MIN_TRADES_PER_MODULE:
            continue
        wins = sum(1 for r in items if r.get("label") == "WIN")
        losses = sum(1 for r in items if r.get("label") == "LOSS")
        decisive = wins + losses
        if decisive == 0:
            continue  # hepsi FLAT → anlamlı yön yok
        win_rate = wins / decisive
        # Skor girdisi: kararlı (WIN/LOSS) kayıtların directional_return'leri.
        drs = [
            float(r["directional_return"])
            for r in items
            if r.get("label") in ("WIN", "LOSS")
        ]
        total = sum(drs)
        avg = total / len(drs) if drs else 0.0
        score = (
            awt._loss_aware_score(win_rate, drs)
            if loss_aware
            else awt._module_score(win_rate, avg)
        )
        perfs.append(
            ModulePerf(
                module=mod, trades=n, wins=wins, win_rate=round(win_rate, 3),
                avg_pnl=round(avg, 6), total_pnl=round(total, 6), score=score,
            )
        )
    perfs.sort(key=lambda p: -p.score)
    return perfs


def train_challenger(records: list[dict]) -> dict:
    """Rejim başına challenger ağırlık önerisi (champion'la shadow kıyas).

    Champion taban = canlı aktif ağırlıklar; öneri matematiği canlı trainer'ın
    `_propose_for_regime`'i. Yetersiz veri → o rejim INSUFFICIENT (uydurma yok)."""
    weights_cfg = load_active_weights()
    regimes_cfg = weights_cfg.get("regimes") or {}
    constraints = weights_cfg.get("constraints", {})
    by_regime: dict[str, list[dict]] = {}
    for r in records:
        by_regime.setdefault(str(r.get("regime_label") or "NEUTRAL"), []).append(r)

    out: dict[str, dict] = {}
    for regime in regimes_cfg:
        recs = by_regime.get(regime, [])
        perfs = _perfs_for(recs)
        champion = dict(regimes_cfg.get(regime) or regimes_cfg.get("NEUTRAL") or {})
        if len(perfs) < awt.MIN_MODULES_FOR_REBALANCE:
            out[regime] = {
                "status": "INSUFFICIENT",
                "reason": "no_module_diversity" if perfs else "no_module_meets_min",
                "records": len(recs),
                "modules_ready": [p.__dict__ for p in perfs],
                "champion_weights": champion,
            }
            continue
        challenger_w, deltas = awt._propose_for_regime(perfs, regime, champion, constraints)
        out[regime] = {
            "status": "PROPOSED",
            "records": len(recs),
            "module_performance": [p.__dict__ for p in perfs],
            "champion_weights": champion,
            "challenger_weights": challenger_w,
            "deltas": [d.__dict__ for d in _sorted_deltas(deltas)],
        }
    return out


def _sorted_deltas(deltas: list[WeightDelta]) -> list[WeightDelta]:
    return sorted(deltas, key=lambda d: -abs(d.delta))


# ----------------------------------------------- quantum ayrım karnesi (cat 6)

def _quantum_score(rec: dict) -> float | None:
    q = (rec.get("module_contributions") or {}).get("quantum")
    if not isinstance(q, dict):
        return None
    s = q.get("score")
    return float(s) if s is not None else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson korelasyon; n<3 veya sıfır varyans → None (uydurma yok)."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    return round(sxy / (sxx ** 0.5 * syy ** 0.5), 4)


def _q_verdict(sep: float | None, corr: float | None) -> str:
    if sep is None:
        return "NO_SPLIT"          # tek yönlü (hep bull ya da hep bear quantum)
    if sep > _SEP_EPS:
        return "DISCRIMINATES"     # quantum bullish → daha yüksek forward-return
    if sep < -_SEP_EPS:
        return "INVERSE"           # quantum bullish → daha DÜŞÜK return (TERS)
    return "FLAT"                  # ayırt etmiyor


def quantum_scorecard(records: list[dict]) -> dict:
    """Rejim başına quantum skoru ↔ forward-return AYRIMI (cat 6 cevabı).

    separation = mean(fr | quantum≥55) − mean(fr | quantum≤45): pozitif → quantum
    o rejimde ayırt ediyor; negatif → TERS. correlation = corr(quantum_score,
    forward_return). Quantum'un DOMINANT olmasına bağlı değil — skoru her kaydın
    module_contributions'ından okunur (nadiren baskın olsa da ölçülür)."""
    by_regime: dict[str, list[dict]] = {}
    for r in records:
        by_regime.setdefault(str(r.get("regime_label") or "NEUTRAL"), []).append(r)

    per_regime: dict[str, dict] = {}
    for regime in _known_regimes():
        recs = by_regime.get(regime, [])
        pairs = [
            (qs, float(r["forward_return"]))
            for r in recs
            if (qs := _quantum_score(r)) is not None and r.get("forward_return") is not None
        ]
        n = len(pairs)
        if n < _MIN_SCORECARD_N:
            per_regime[regime] = {"n": n, "status": "INSUFFICIENT"}
            continue
        qs = [p[0] for p in pairs]
        frs = [p[1] for p in pairs]
        bull = [fr for q, fr in pairs if q >= _Q_BULL]
        bear = [fr for q, fr in pairs if q <= _Q_BEAR]
        sep = (
            round(sum(bull) / len(bull) - sum(bear) / len(bear), 5)
            if (bull and bear)
            else None
        )
        corr = _pearson(qs, frs)
        per_regime[regime] = {
            "n": n,
            "mean_quantum": round(sum(qs) / n, 2),
            "bull_n": len(bull),
            "bear_n": len(bear),
            "separation": sep,
            "correlation": corr,
            "verdict": _q_verdict(sep, corr),
            "status": "OK",
        }
    return {"per_regime": per_regime, "summary": _scorecard_summary(per_regime)}


def _scorecard_summary(per_regime: dict) -> str:
    scored = [
        (reg, d["separation"])
        for reg, d in per_regime.items()
        if d.get("separation") is not None
    ]
    if not scored:
        return "quantum ayrımı ölçülemedi (yetersiz veri / tek yönlü)."
    scored.sort(key=lambda t: t[1], reverse=True)
    best_reg, best_sep = scored[0]
    parts = [f"quantum en güçlü {best_reg}'da ayrışıyor (sep={best_sep:+.4f})"]
    worst_reg, worst_sep = scored[-1]
    if worst_sep < -_SEP_EPS:
        parts.append(f"{worst_reg}'da TERS (sep={worst_sep:+.4f})")
    disc = [reg for reg, d in per_regime.items() if d.get("verdict") == "DISCRIMINATES"]
    parts.append(f"ayırt eden rejimler: {disc or 'yok'}")
    return "; ".join(parts)


# ----------------------------------------------------------------- rapor / run

def run(records: list[dict] | None = None) -> dict:
    """B-3 ana giriş: challenger ağırlık + quantum karnesi → İZOLE rapor.

    `records` None → `backtest_recon.read_challenger()` (B-2 çıktısı). Canlı
    ağırlığa/config'e/paper'a YAZMAZ."""
    now = datetime.now(UTC).isoformat()
    if records is None:
        records = backtest_recon.read_challenger()
    if not records:
        report = {
            "generated_at": now, "engine": "challenger_trainer_v1",
            "status": "NO_DATA", "reason": "no_challenger_records", "source_records": 0,
        }
        _write_report(report)
        return report

    weights = train_challenger(records)
    scorecard = quantum_scorecard(records)
    proposed = [reg for reg, d in weights.items() if d.get("status") == "PROPOSED"]
    report = {
        "generated_at": now,
        "engine": "challenger_trainer_v1",
        "status": "OK",
        "source_records": len(records),
        "loss_aware": awt._loss_aware_enabled(),
        "proposed_regimes": proposed,
        "regimes": weights,
        "quantum_scorecard": scorecard,
        "isolation": "shadow-only; canlı ağırlık/config/paper'a YAZMAZ (owner terfi=B-4)",
        "note": (
            "challenger ağırlık = canlı auto_weight_trainer matematiğiyle (reuse) "
            "rejim başına; champion delta shadow. quantum karnesi = skor↔forward-"
            "return ayrımı (attribution değil)."
        ),
    }
    _write_report(report)
    return report


def _write_report(report: dict) -> None:
    """İzole rapor (best-effort; yazım hatası worker'ı kesmez)."""
    try:
        p = _report_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass
