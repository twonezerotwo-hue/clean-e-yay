"""Y-1 — Rejim risk freni: kanıtı NEGATİF rejimde açılış boyutunu YALNIZ KÜÇÜLTEN çarpan.

Gerekçe (2026-07-06/07 modül karnesi): en büyük kaçak modül farkı değil, OFFENSIVE
rejimde yön kararının kendisi (backtest v1 −77.7% / v2 −74.3%; canlı OFFENSIVE
kohortu da negatif). Ağırlık terfisi OFFENSIVE'da challenger'dan çıkamıyor
(no_module_diversity — touche 185 kaydın 183'ünde baskın) → dürüst kaldıraç,
yön değil BOYUT: kanıtı negatif rejimde küçül.

Fren kuralı (26 Kasım 2026, owner onayı, revizyon L2 + L6): AUTO kohort
(cohorts.classify == AUTO) canlı sonuçları rejim bazında — R taşıyan en az min_live_n
işlem VE maliyet sonrası ortalama R (net_r) < 0 → mult = brake_mult; guardrail
[floor, 1.0] — ASLA büyütmez (no-boost invariant), ASLA floor altına inmez (fren kapatma
değil kısma). (Eskiden ikinci kanıt backtest challenger kayıtlarıydı; challenger 29 Ekim
2026'dan beri kapalı ve kaydı donuktu, canlı ayak da boyuta duyarlı brüt USD toplamıydı.)

Akış: `compute()` learning worker'da OFF-TICK koşar → öneri tablosu
(regime_risk_brake_proposal.json). Sıcak yol (decision engine) yalnız mtime-cache'li
`active_mult()` ile CANLI tabloyu okur; canlı tablo 26 Kasım 2026'dan beri donmuştur ve
yalnız owner onayıyla (öneri kopyası) değişir; tablo yoksa 1.0. Frenlenen kararda engine
fren kanıtını raporda taşır.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds
from packages.ops.store import write_text_atomic


def _cfg() -> dict:
    try:
        return load_thresholds().get("regime_risk_brake") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _path() -> Path:
    """Canlı (donmuş) fren tablosu; karar motoru yalnız bunu okur."""
    return Path(os.environ.get("REGIME_RISK_BRAKE_PATH", "data/runtime/regime_risk_brake.json"))


def _proposal_path() -> Path:
    """compute()'un yazdığı öneri tablosu (canlının yanında). 26 Kasım 2026 owner
    kararı: canlı tablo kendiliğinden değişmez, öneri owner onayıyla kopyalanır."""
    live = _path()
    return live.with_name(f"{live.stem}_proposal{live.suffix}")


def _live_by_regime(outcomes) -> dict[str, dict]:
    """AUTO kohort canlı sonuçları rejim bazında: R taşıyan işlem sayısı, ortalama net R
    ve net USD toplamı (gösterim)."""
    from packages.learning import cohorts
    agg: dict[str, dict] = {}
    for o in outcomes:
        if cohorts.classify(o) != cohorts.AUTO:
            continue
        net_r = getattr(o, "net_r", None)
        if net_r is None:
            continue
        reg = (o.regime or "UNKNOWN").upper()
        row = agg.setdefault(reg, {"n": 0, "sum_net_r": 0.0, "net_pnl_usd": 0.0})
        row["n"] += 1
        row["sum_net_r"] += float(net_r)
        row["net_pnl_usd"] += float(getattr(o, "net_pnl", getattr(o, "pnl", 0.0)) or 0.0)
    for row in agg.values():
        row["mean_net_r"] = round(row.pop("sum_net_r") / row["n"], 4)
        row["net_pnl_usd"] = round(row["net_pnl_usd"], 2)
    return agg


def compute(outcomes=None, now: datetime | None = None) -> dict:
    """Fren tablosu önerisini üret (OFF-TICK — learning worker). Girdi enjekte edilebilir
    (test). Karar zincirine DOKUNMAZ — öneri dosyasına yazar; canlı tablo owner onayıyla."""
    now = now or datetime.now(UTC)
    cfg = _cfg()
    min_live = int(cfg.get("min_live_n", 10))
    floor = max(0.0, min(1.0, float(cfg.get("floor", 0.4))))
    brake_mult = max(floor, min(1.0, float(cfg.get("brake_mult", 0.6))))

    if outcomes is None:
        from packages.learning import outcomes as outcomes_mod
        # Veri hijyeni (2026-07-12): legacy kayıtlar fren tablosuna girmez.
        outcomes = outcomes_mod.learning_grade(outcomes_mod.outcomes_from_state())

    live = _live_by_regime(outcomes)
    per_regime: dict[str, dict] = {}
    for reg in sorted(live):
        lv = live[reg]
        negative = lv["n"] >= min_live and lv["mean_net_r"] < 0
        per_regime[reg] = {
            "mult": brake_mult if negative else 1.0,
            "braked": bool(negative),
            "evidence": {"live": {**lv, "min_required": min_live, "negative": negative}},
        }

    report = {
        "generated_at": now.isoformat(),
        "engine": "regime_risk_brake_v2",
        "config": {"min_live_n": min_live, "brake_mult": brake_mult, "floor": floor},
        "per_regime": per_regime,
        "braked_regimes": sorted(r for r, v in per_regime.items() if v["braked"]),
        "note": "fren YALNIZ kucultur; AUTO kohort ortalama net R < 0 ise",
    }
    _write(report)
    return report


def _write(report: dict) -> None:
    write_text_atomic(_proposal_path(), json.dumps(report, ensure_ascii=False, indent=1))


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
    """(mult, evidence) — sıcak yol. Canlı tablo yok/rejim yok → (1.0, None).

    Canlı tablo donmuştur (26 Kasım 2026): yaşı yüzünden düşmez; yalnız owner
    onayıyla değişir. (Eskiden 48 saatten eski tablo freni kaldırıyordu.)"""
    data = _load_cached()
    if not data:
        return 1.0, None
    try:
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
        return {"status": "NO_ARTIFACT", "per_regime": {},
                "braked_regimes": [],
                "note": "learning worker henuz compute() kosmadi"}
    return {"status": "OK",
            "generated_at": data.get("generated_at"),
            "per_regime": data.get("per_regime") or {},
            "braked_regimes": data.get("braked_regimes") or [],
            "config": data.get("config") or {},
            "note": data.get("note")}
