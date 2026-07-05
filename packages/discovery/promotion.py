"""K-4 — Keşif adayı terfi kriteri (owner ÖNERİ paketi; KIRMIZI ÇİZGİ).

Keşif tarayıcısı (K-1) adayları GÖLGEDE analiz eder, defter (K-2) "açılırdı"
hükümlerini gerçek barlarla çözer (missed_win / avoided_loss / expired). Bu
modül bir adayın biriken gölge karnesini SAYIYA bağlar: aday, champion/challenger
terfi kriterinin (F5-2) aday-evrenine uyarlanmış ÜÇ eşiğini geçerse governor
defterine OWNER ONAY PAKETİ sunulur.

ÜÇ KRİTER (promotion_criteria/challenger_promotion ile aynı ruh):
  1. Çözülmüş kararlı sinyal hacmi: missed_win + avoided_loss ≥ min_resolved_
     decisive (expired paydaya girmez — cf_win_rate ile aynı sayım).
  2. TF çeşitliliği: aday ≥ min_timeframes farklı TF'de sinyal üretmiş (tek-TF
     şans/uydurma elenir).
  3. cf_win_rate %95 Wilson ALT sınırı > 0.5 — "adayın isabeti şans değil".

KIRMIZI ÇİZGİ (Anayasa/CP5): kriter TUTSA BİLE hiçbir varlık otomatik EKLENMEZ.
READY paketi STRATEGY_ENABLE governor önerisidir (`add_custom_asset: SEMBOL`);
onay bile YALNIZ defteri günceller — canlı evren (custom_assets/assets.yaml)
DEĞİŞMEZ. Terfinin kendisi owner'ın elle yürüteceği ayrı iştir.

Tüketim: learning worker her keşif koşusundan sonra bunu çağırır (governor
defteri + run meta status) — promotion_criteria/challenger_promotion ile aynı
yüzey; ayrı panel/kontrat gerektirmez.

PAPER_SAFE / NO_EXECUTION — yalnız gölge karneyi okur, sayar, paket üretir.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.discovery import scanner, shadow_ledger
from packages.learning.mistake_memory import wilson_bounds

_DEFAULTS = {
    "min_resolved_decisive": 20,
    "min_timeframes": 2,
}


def cfg() -> dict:
    try:
        raw = scanner.load_config().get("promotion") or {}
        return {
            "min_resolved_decisive": max(
                1,
                int(raw.get("min_resolved_decisive", _DEFAULTS["min_resolved_decisive"])),
            ),
            "min_timeframes": max(
                1, int(raw.get("min_timeframes", _DEFAULTS["min_timeframes"]))
            ),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return dict(_DEFAULTS)


def _evaluate_candidate(sym: str, sc: dict, c: dict) -> dict:
    """Bir adayın gölge karnesinden terfi hükmü (üç kriter bağımsız)."""
    missed = int(sc.get("missed_win") or 0)
    avoided = int(sc.get("avoided_loss") or 0)
    decisive = missed + avoided
    tfs = sorted(str(t) for t in (sc.get("timeframes") or []))
    ci_low, ci_high = wilson_bounds(missed, decisive)
    checks = {
        "resolved_decisive": {
            "value": decisive,
            "required": c["min_resolved_decisive"],
            "pass": decisive >= c["min_resolved_decisive"],
        },
        "timeframe_spread": {
            "value": len(tfs),
            "timeframes": tfs,
            "required": c["min_timeframes"],
            "pass": len(tfs) >= c["min_timeframes"],
        },
        "ci_disjoint": {
            "cf_win_rate": round(missed / decisive, 4) if decisive else None,
            "wilson_low": round(ci_low, 4),
            "wilson_high": round(ci_high, 4),
            "required": "wilson_low > 0.5",
            "pass": decisive > 0 and ci_low > 0.5,
        },
    }
    ready = all(chk["pass"] for chk in checks.values())
    return {
        "symbol": sym,
        "status": "READY" if ready else "NOT_READY",
        "checks": checks,
        "missed_win": missed,
        "avoided_loss": avoided,
        "expired": int(sc.get("expired") or 0),
        "avg_r": sc.get("avg_r"),
        "timeframes": tfs,
    }


def evaluate(*, candidates: dict | None = None) -> dict:
    """Tüm keşif adaylarını terfi kriterine göre değerlendir.

    `candidates` None → `shadow_ledger.candidate_summary()` (canlı gölge karne).
    (Enjeksiyon yalnız test/izole kıyas için.)"""
    c = cfg()
    if candidates is None:
        candidates = dict(shadow_ledger.candidate_summary().get("candidates") or {})
    per_candidate: dict[str, dict] = {}
    ready_symbols: list[str] = []
    for sym, sc in candidates.items():
        ev = _evaluate_candidate(str(sym), dict(sc or {}), c)
        per_candidate[str(sym)] = ev
        if ev["status"] == "READY":
            ready_symbols.append(str(sym))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "READY" if ready_symbols else "NOT_READY",
        "ready_symbols": sorted(ready_symbols),
        "candidates_evaluated": len(per_candidate),
        "per_candidate": per_candidate,
        "config": c,
        "note": (
            "READY = owner onay paketi (governor önerisi); varlık OTOMATİK "
            "eklenmez — KIRMIZI ÇİZGİ (onay bile canlı evreni değiştirmez)"
        ),
    }


def run() -> dict:
    """learning_worker giriş noktası: değerlendir; READY adaylar için governor
    defterine owner-onay paketi sun (aday başına submit dedupe'lu — tek PENDING)."""
    package = evaluate()
    submitted: list[str] = []
    if package["ready_symbols"]:
        from packages.governor import proposals

        for sym in package["ready_symbols"]:
            ev = package["per_candidate"][sym]
            ci = ev["checks"]["ci_disjoint"]
            n_dec = ev["missed_win"] + ev["avoided_loss"]
            p = proposals.submit(
                {
                    "proposal_type": "STRATEGY_ENABLE",
                    "title": f"Keşif adayı terfi kriterini karşıladı: {sym}",
                    "summary": (
                        f"{sym} gölge karnesi eşikleri geçti: {ev['missed_win']}/{n_dec} "
                        f"kararlı isabet {ci['cf_win_rate']}, %95 alt sınır {ci['wilson_low']} "
                        f"> 0.5, TF'ler {ev['timeframes']}. Hipotetik (işlem AÇILMADI). "
                        "custom_assets'e ekleme ÖNERİSİ — otomatik EKLENMEZ; sen "
                        "onaylasan bile canlı evren değişmez (elle iş). KIRMIZI ÇİZGİ."
                    ),
                    "evidence": ev,
                    # Aday başına SABİT anahtar → dedupe (sembol başına tek PENDING);
                    # promotion_criteria/challenger_promotion anahtarlarından FARKLI.
                    "requested_change": {"add_custom_asset": sym},
                    "rollback_plan": "Paket reddedilir/silinir; canlı evren değişmemiştir.",
                    "source": "discovery_promotion",
                }
            )
            if p:
                submitted.append(p.get("proposal_id"))
    package["proposal_ids"] = submitted
    return package


__all__ = ["cfg", "evaluate", "run"]
