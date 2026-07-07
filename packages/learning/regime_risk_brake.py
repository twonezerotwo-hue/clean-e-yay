"""Y-1 — Rejim risk freni: kanıtı NEGATİF rejimde açılış boyutunu YALNIZ KÜÇÜLTEN çarpan.

Gerekçe (2026-07-06/07 modül karnesi): en büyük kaçak modül farkı değil, OFFENSIVE
rejimde yön kararının kendisi (backtest v1 −77.7% / v2 −74.3%; canlı OFFENSIVE
kohortu da negatif). Ağırlık terfisi OFFENSIVE'da challenger'dan çıkamıyor
(no_module_diversity — touche 185 kaydın 183'ünde baskın) → dürüst kaldıraç,
yön değil BOYUT: kanıtı negatif rejimde küçül.

Fren kuralı (yanlış-pozitif freni için kanıt ÇİFT kaynaklı olmak ZORUNDA):
- CANLI: AUTO kohort (cohorts.classify == AUTO) outcome'ları rejim bazında —
  n >= min_live_n VE toplam pnl_usd < 0.
- BACKTEST: challenger kayıtları (B-2 İZOLE kanal, backtest_recon.read_challenger)
  rejim bazında — yönlü karar n >= min_backtest_n VE directional_return toplamı < 0.
İkisi de negatifse mult = brake_mult; guardrail [floor, 1.0] — ASLA büyütmez
(no-boost invariant), ASLA floor altına inmez (fren kapatma değil kısma).

Akış: `compute()` learning worker'da OFF-TICK koşar → data/runtime/regime_risk_brake.json.
Sıcak yol (decision engine) yalnız mtime-cache'li `active_mult()` okur; artifact
yok/bayat (> max_age_hours) → 1.0 (dürüst düşüş — uydurma fren yok, öğrenme durursa
canlı tik bağımsız kalır). Flag `regime_risk_brake.enabled` DEFAULT OFF = bayt-aynı;
engine flag'ten BAĞIMSIZ shadow raporu taşır (aktivasyon kanıtı flag açılmadan birikir).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds


def _cfg() -> dict:
    try:
        return load_thresholds().get("regime_risk_brake") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def enabled() -> bool:
    """`regime_risk_brake.enabled` owner-flag (DEFAULT OFF = fren uygulanmaz,
    yalnız shadow raporu). Geri-alma = false (kod değişikliği gerekmez)."""
    return bool(_cfg().get("enabled", False))


def _path() -> Path:
    return Path(os.environ.get("REGIME_RISK_BRAKE_PATH", "data/runtime/regime_risk_brake.json"))


def _live_by_regime(outcomes) -> dict[str, dict]:
    """AUTO kohort canlı outcome'ları rejim bazında n + toplam pnl (USD)."""
    from packages.learning import cohorts
    agg: dict[str, dict] = {}
    for o in outcomes:
        if cohorts.classify(o) != cohorts.AUTO:
            continue
        reg = (o.regime or "UNKNOWN").upper()
        row = agg.setdefault(reg, {"n": 0, "pnl_usd": 0.0})
        row["n"] += 1
        row["pnl_usd"] += float(o.pnl or 0.0)
    for row in agg.values():
        row["pnl_usd"] = round(row["pnl_usd"], 2)
    return agg


def _backtest_by_regime(records) -> dict[str, dict]:
    """Challenger kayıtları (B-2) rejim bazında yönlü n + directional_return toplamı."""
    agg: dict[str, dict] = {}
    for r in records:
        reg = str(r.get("regime_label") or "UNKNOWN").upper()
        dr = r.get("directional_return")
        if r.get("direction") not in ("bullish", "bearish") or dr is None:
            continue  # nötr/outcome'suz kayıt fren kanıtı değil
        row = agg.setdefault(reg, {"n": 0, "sum_directional_return": 0.0})
        row["n"] += 1
        row["sum_directional_return"] += float(dr)
    for row in agg.values():
        row["sum_directional_return"] = round(row["sum_directional_return"], 4)
    return agg


def compute(outcomes=None, challenger_records=None, now: datetime | None = None) -> dict:
    """Fren tablosunu üret (OFF-TICK — learning worker). Girdiler enjekte edilebilir (test).

    Karar zincirine DOKUNMAZ — yalnız artifact yazar; tüketim engine'de flag'le."""
    now = now or datetime.now(UTC)
    cfg = _cfg()
    min_live = int(cfg.get("min_live_n", 10))
    min_bt = int(cfg.get("min_backtest_n", 30))
    floor = max(0.0, min(1.0, float(cfg.get("floor", 0.4))))
    brake_mult = max(floor, min(1.0, float(cfg.get("brake_mult", 0.6))))

    if outcomes is None:
        from packages.learning import outcomes as outcomes_mod
        outcomes = outcomes_mod.outcomes_from_state()
    if challenger_records is None:
        from packages.learning import backtest_recon
        challenger_records = backtest_recon.read_challenger()

    live = _live_by_regime(outcomes)
    backtest = _backtest_by_regime(challenger_records)

    per_regime: dict[str, dict] = {}
    for reg in sorted(set(live) | set(backtest)):
        lv = live.get(reg, {"n": 0, "pnl_usd": 0.0})
        bt = backtest.get(reg, {"n": 0, "sum_directional_return": 0.0})
        live_negative = lv["n"] >= min_live and lv["pnl_usd"] < 0
        bt_negative = bt["n"] >= min_bt and bt["sum_directional_return"] < 0
        braked = bool(live_negative and bt_negative)
        per_regime[reg] = {
            "mult": brake_mult if braked else 1.0,
            "braked": braked,
            "evidence": {
                "live": {**lv, "min_required": min_live, "negative": live_negative},
                "backtest": {**bt, "min_required": min_bt, "negative": bt_negative},
            },
        }

    report = {
        "generated_at": now.isoformat(),
        "engine": "regime_risk_brake_v1",
        "enabled": enabled(),
        "config": {"min_live_n": min_live, "min_backtest_n": min_bt,
                   "brake_mult": brake_mult, "floor": floor},
        "per_regime": per_regime,
        "braked_regimes": sorted(r for r, v in per_regime.items() if v["braked"]),
        "note": "fren YALNIZ kucultur; iki kaynak da negatif degilse 1.0; flag OFF iken salt-gozlem",
    }
    _write(report)
    return report


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ── sıcak yol okuyucu (decision engine) — mtime cache, ağ/hesap yok ─────────────
_cache: dict = {"mtime": None, "data": None}


def _load_cached() -> dict | None:
    try:
        p = _path()
        if not p.exists():
            return None
        mtime = p.stat().st_mtime
        if _cache["mtime"] != mtime:
            _cache["data"] = json.loads(p.read_text(encoding="utf-8"))
            _cache["mtime"] = mtime
        return _cache["data"]
    except (OSError, ValueError, TypeError):
        return None


def active_mult(regime_label: str | None, now: datetime | None = None) -> tuple[float, dict | None]:
    """(mult, evidence) — sıcak yol. Artifact yok/bayat/rejim yok → (1.0, None).

    Flag kontrolü BURADA DEĞİL: engine shadow için her zaman okur, yalnız
    flag açıkken uygular (aktivasyon kanıtı flag'siz birikir)."""
    data = _load_cached()
    if not data:
        return 1.0, None
    try:
        max_age_h = float(_cfg().get("max_age_hours", 48))
        gen = datetime.fromisoformat(str(data.get("generated_at")))
        now = now or datetime.now(UTC)
        if (now - gen).total_seconds() > max_age_h * 3600:
            return 1.0, None  # öğrenme durmuş → fren düşer, uydurma yok
        row = (data.get("per_regime") or {}).get(str(regime_label or "").upper())
        if not row or not row.get("braked"):
            return 1.0, None
        mult = float(row.get("mult", 1.0))
        mult = max(0.0, min(1.0, mult))  # no-boost: okurken de tavan 1.0
        return mult, {"mult": mult, "regime": str(regime_label).upper(),
                      "generated_at": data.get("generated_at"),
                      "evidence": row.get("evidence")}
    except (ValueError, TypeError, KeyError):
        return 1.0, None


def viewmodel() -> dict:
    """GET /learning/regime-risk-brake — artifact'tan türetilir, hesap yapmaz."""
    data = _load_cached()
    if not data:
        return {"status": "NO_ARTIFACT", "enabled": enabled(), "per_regime": {},
                "braked_regimes": [],
                "note": "learning worker henuz compute() kosmadi"}
    return {"status": "OK", "enabled": enabled(),
            "generated_at": data.get("generated_at"),
            "per_regime": data.get("per_regime") or {},
            "braked_regimes": data.get("braked_regimes") or [],
            "config": data.get("config") or {},
            "note": data.get("note")}
