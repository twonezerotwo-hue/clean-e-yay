"""FAZ-4 — Sinyal kalitesi ayrım karnesi (rejim başına modül; salt-gözlem).

Amaç (kat 6/7 10/10 hedefi): "skorlar iyi/kötü işlemi AYIRIYOR mu?" sorusunu
SAYIYA bağlar. `module_attribution` (F1-3) her modülün kazanan vs kaybeden
trade'lerdeki ortalama katkısını verir ama KABA: rejim ayrımı yok, hüküm yok.
Denetim bulgusu: pooled'da touche 23.6(win)/24.3(loss) → kazanan≈kaybeden, yani
ağırlık trainer'ı neyi öğreneceğini AYIRT EDEMİYOR. Bu karne aynı veri yüzeyini
(outcome.module_contributions = score×weight) REJİM başına böler + ayrım hükmü
üretir (B-3 quantum karnesinin tüm modüllere + CANLI veriye genellenmişi).

separation = avg_contrib(win) − avg_contrib(loss); pozitif+anlamlı → modül o
rejimde kazananları kaybedenlerden AYIRIYOR (gerçek edge). ~0 → ayırmıyor
(gürültü). Negatif → TERS (kaybedenlerde katkısı daha yüksek). rel_separation =
sep / (|avg_win|+|avg_loss|) ∈ [−1,1] → ölçek-bağımsız, modül/rejim arası
kıyaslanabilir; FLAT bandı bunun üstünde.

Rejim içinde ağırlık SABİT olduğundan katkı (score×weight) skorla ORANTILIDIR →
rejim-içi ayrım skorun ayrımını yansıtır (ham skor gerekmez). pnl==0 başabaş
girmez (F1-2 ile tutarlı); vektör taşımayan legacy/manuel outcome atlanır.

KIRMIZI ÇİZGİ: SALT-GÖZLEM. Hiçbir karar/ağırlık BU karneden beslenmez. Bu,
WEIGHT_REGIME_FILTER aktivasyonu için KANIT kapısıdır (owner kararı ayrı) —
modüllerin gerçekten rejim-bazlı ayrıştığını (ya da ayrışmadığını) gösterir.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

# Modül×rejim başına anlamlı hüküm için minimum kazanan/kaybeden trade (gürültü
# freni — az örnekte ayrım şansa döner).
_MIN_WIN = 5
_MIN_LOSS = 5
# |rel_separation| bu bandın altında → modül ayırt ETMİYOR (FLAT/gürültü).
_FLAT_BAND = 0.05


def _verdict(rel_sep: float | None) -> str:
    if rel_sep is None:
        return "INSUFFICIENT"
    if rel_sep > _FLAT_BAND:
        return "DISCRIMINATES"
    if rel_sep < -_FLAT_BAND:
        return "INVERSE"
    return "FLAT"


def _module_split(outcomes) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """modül → (kazanan katkıları, kaybeden katkıları). pnl==0 ve vektörsüz atlanır."""
    wins: dict[str, list[float]] = {}
    losses: dict[str, list[float]] = {}
    for o in outcomes:
        contribs = getattr(o, "module_contributions", None)
        pnl = getattr(o, "pnl", 0.0)
        if not contribs or pnl == 0:
            continue
        bucket = wins if pnl > 0 else losses
        for mod, contrib in contribs.items():
            try:
                bucket.setdefault(str(mod), []).append(float(contrib))
            except (TypeError, ValueError):
                continue
    return wins, losses


def _scorecard_for(outcomes) -> dict[str, dict]:
    """Bir outcome kümesinde modül başına ayrım karnesi (rejim-agnostik çekirdek)."""
    wins, losses = _module_split(outcomes)
    out: dict[str, dict] = {}
    for mod in sorted(set(wins) | set(losses)):
        w = wins.get(mod, [])
        loss = losses.get(mod, [])
        nw, nl = len(w), len(loss)
        if nw < _MIN_WIN or nl < _MIN_LOSS:
            out[mod] = {
                "n_win": nw, "n_loss": nl,
                "status": "INSUFFICIENT", "verdict": "INSUFFICIENT",
            }
            continue
        avg_w = sum(w) / nw
        avg_l = sum(loss) / nl
        denom = abs(avg_w) + abs(avg_l)
        rel_sep = round((avg_w - avg_l) / denom, 4) if denom > 0 else None
        out[mod] = {
            "n_win": nw, "n_loss": nl,
            "avg_contrib_win": round(avg_w, 3),
            "avg_contrib_loss": round(avg_l, 3),
            "separation": round(avg_w - avg_l, 3),
            "rel_separation": rel_sep,
            "verdict": _verdict(rel_sep),
            "status": "OK",
        }
    return out


def _summary(per_regime: dict[str, dict]) -> str:
    disc: list[str] = []
    inverse: list[str] = []
    for reg, mods in per_regime.items():
        for mod, d in mods.items():
            if d.get("verdict") == "DISCRIMINATES":
                disc.append(f"{mod}@{reg}")
            elif d.get("verdict") == "INVERSE":
                inverse.append(f"{mod}@{reg}")
    parts = [f"ayırt eden (modül@rejim): {disc or 'yok'}"]
    if inverse:
        parts.append(f"TERS: {inverse}")
    return "; ".join(parts)


def regime_module_scorecard(outcomes) -> dict:
    """FAZ-4 ana giriş: rejim başına modül kalite-ayrım karnesi + pooled + özet.

    `outcomes`: CanonicalOutcome listesi (yalnız `regime`/`pnl`/
    `module_contributions` okunur → salt-gözlem)."""
    by_regime: dict[str, list] = {}
    for o in outcomes:
        by_regime.setdefault(str(getattr(o, "regime", None) or "UNKNOWN"), []).append(o)
    per_regime = {reg: _scorecard_for(recs) for reg, recs in by_regime.items()}
    return {
        "per_regime": per_regime,
        # pooled (rejim-agnostik) — module_attribution ikizi + ayrım hükmü;
        # denetimdeki "kazanan≈kaybeden" bulgusunu hüküm'le doğrular.
        "overall": _scorecard_for(outcomes),
        "summary": _summary(per_regime),
        "note": (
            "salt-gözlem; hiçbir karar/ağırlık beslemez — WEIGHT_REGIME_FILTER "
            "aktivasyonu için kanıt kapısı (modüller rejim-bazlı ayrışıyor mu?)"
        ),
    }


__all__ = ["regime_module_scorecard"]
