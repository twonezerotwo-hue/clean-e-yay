"""CP4 (slice 1) — giriş/çıkış kalitesi öğrenicisi (saf, deterministik, observe-only).

Mevcut TF-target trainer SL/TP geometrisini yalnız **timeframe** bazında öğrenir;
"hangi MODÜLÜN girişi erken / çıkışı erken / stop'u dar" sorusu bugün hiçbir
yerde öğrenilmiyor (granülerlik boşluğu). Bu modül o boşluğu kapatır: her kapanan
verified outcome'un MAE/MFE excursion'ından üç dersi çıkarır ve kovaları
**dominant_module × timeframe** bazında kırar.

Yeni veri kaynağı YOK — yalnızca mevcut `CanonicalOutcome` alanlarını (pnl_pct,
mae_pct, mfe_pct, close_reason) okur. Üç ders:

  * **Erken çıkış (EXIT_EARLY)** — yakalama oranı (pnl_pct / mfe_pct) düşük ve
    bırakılan kâr (mfe - pnl) yüksek → trailing çok sıkı / R:R düşük.
  * **Dar stop (STOP_TOO_TIGHT)** — SL_HIT oranı yüksek ve stop'a yenen
    işlemlerin adverse mesafesi, aynı kovadaki kazananların tipik MFE'sinden
    küçük → stop normal dalgalanmanın içinde tetikleniyor.
  * **Erken giriş (ENTER_EARLY)** — kazananlar lehe dönmeden önce tipik olarak
    MFE'lerinin büyük kısmı kadar aleyhte dalıyor → giriş tetiği erken.

Slice 1 SADECE ÖLÇER + ÖNERİR (panel/endpoint ile tüketilir). Önerileri otonom
uygulama (modül-bazlı SL×ATR / trailing nudge'ı, rollback net'iyle, edge STABLE
kapısından geçince) AYRI bir slice'tır — bu modül karar zincirine DOKUNMAZ.

PAPER_SAFE / NO_EXECUTION — observe-only.
"""
from __future__ import annotations

from packages.learning import outcomes as outcomes_mod
from packages.learning.outcomes import CanonicalOutcome

# --- eşikler (açık, sabit; magic-number değil) ---------------------------------
# Anlamlı hareket tabanı: mfe/mae bunun altındaysa "hareketsiz" sayılır (gürültü).
_MIN_MOVE_PCT = 0.05
# Bir kovada ders üretmek için gereken minimum kullanılabilir (excursion'lı) örnek.
_MIN_BUCKET = 4
# Yakalama oranı bunun altındaysa "kâr masada bırakılıyor" (erken çıkış sinyali).
_CAPTURE_LOW = 0.50
# Bırakılan ortalama kâr bunun üstündeyse erken-çıkış teyidi (yüzde puan).
_GIVE_BACK_HIGH_PCT = 0.40
# SL_HIT oranı bunun üstündeyse stop-baskısı incelenir.
_SL_RATE_HIGH = 0.25
# Kazananların lehe dönmeden önceki adverse dalışı, MFE'lerinin bu oranından
# fazlaysa "erken giriş" (önce eziliyor, sonra kazanıyor).
_ADVERSE_RATIO_HIGH = 0.60


def _is_winner(o: CanonicalOutcome) -> bool:
    return o.pnl > 0


def _went_favorable(o: CanonicalOutcome) -> bool:
    return o.mfe_pct > _MIN_MOVE_PCT


def _has_excursion(o: CanonicalOutcome) -> bool:
    """MAE veya MFE anlamlı → outcome bu analizde kullanılabilir (hareketsiz/0-0
    legacy kayıtlar düşer; istatistiği kirletmez)."""
    return o.mae_pct > _MIN_MOVE_PCT or o.mfe_pct > _MIN_MOVE_PCT


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _bucket_metrics(outs: list[CanonicalOutcome]) -> dict:
    """Tek kova (module×tf) için excursion metrikleri. Yalnız excursion'lı
    outcome'lar sayılır; alt-örneklemler boşsa None döner (uydurma yok)."""
    usable = [o for o in outs if _has_excursion(o)]
    winners = [o for o in usable if _is_winner(o)]
    favorable = [o for o in usable if _went_favorable(o)]
    sl_trades = [o for o in usable if (o.close_reason or "") == "SL_HIT"]

    # Yakalama oranı: kazananın realize ettiği kârın, ulaştığı tepe lehe harekete
    # oranı. mfe >= pnl olduğundan [0,1]; düşükse trailing/TP erken kesmiş.
    captures = [
        min(1.0, o.pnl_pct / o.mfe_pct)
        for o in winners
        if o.pnl_pct is not None and o.mfe_pct > _MIN_MOVE_PCT
    ]
    # Bırakılan kâr (yüzde puan): lehe giden işlemlerde tepe ile realize farkı.
    give_backs = [
        max(0.0, o.mfe_pct - (o.pnl_pct or 0.0))
        for o in favorable
    ]
    # Erken-giriş sinyali: kazananların lehe dönmeden önceki adverse dalışının
    # MFE'lerine oranı (önce ne kadar ezildiler).
    adverse_ratios = [
        o.mae_pct / o.mfe_pct
        for o in winners
        if o.mfe_pct > _MIN_MOVE_PCT
    ]
    return {
        "n": len(outs),
        "n_usable": len(usable),
        "n_winners": len(winners),
        "n_sl_hit": len(sl_trades),
        "sl_hit_rate": round(len(sl_trades) / len(usable), 3) if usable else 0.0,
        "avg_capture_ratio": _avg(captures),
        "avg_give_back_pct": _avg(give_backs),
        "avg_winner_mfe_pct": _avg([o.mfe_pct for o in winners]),
        "avg_sl_adverse_pct": _avg([o.mae_pct for o in sl_trades]),
        "avg_winner_adverse_ratio": _avg(adverse_ratios),
    }


def _verdicts(m: dict) -> list[dict]:
    """Kova metriğinden ders(ler) + somut öneri (slice 2 nudge ipucu). Bir kovada
    birden çok ders olabilir; yeterli örnek yoksa boş (sessiz)."""
    out: list[dict] = []
    if m["n_usable"] < _MIN_BUCKET:
        return out

    cap = m["avg_capture_ratio"]
    gb = m["avg_give_back_pct"]
    if cap is not None and gb is not None and cap < _CAPTURE_LOW and gb >= _GIVE_BACK_HIGH_PCT:
        out.append({
            "code": "EXIT_EARLY",
            "detail": (
                f"yakalama %{cap * 100:.0f} · ort. bırakılan kâr %{gb:.2f} → "
                f"çıkış erken / trailing sıkı"
            ),
            "nudge": {"dimension": "trailing", "direction": "loosen"},
        })

    sl_adv = m["avg_sl_adverse_pct"]
    win_mfe = m["avg_winner_mfe_pct"]
    if (
        m["sl_hit_rate"] >= _SL_RATE_HIGH
        and sl_adv is not None
        and win_mfe is not None
        and sl_adv < win_mfe
    ):
        out.append({
            "code": "STOP_TOO_TIGHT",
            "detail": (
                f"SL oranı %{m['sl_hit_rate'] * 100:.0f} · stop adverse %{sl_adv:.2f} "
                f"< kazanan MFE %{win_mfe:.2f} → stop gürültüde tetikleniyor"
            ),
            "nudge": {"dimension": "sl_atr", "direction": "widen"},
        })

    ar = m["avg_winner_adverse_ratio"]
    if ar is not None and ar >= _ADVERSE_RATIO_HIGH:
        out.append({
            "code": "ENTER_EARLY",
            "detail": (
                f"kazananlar lehe dönmeden önce MFE'lerinin %{ar * 100:.0f}'i kadar "
                f"aleyhte dalıyor → giriş tetiği erken"
            ),
            "nudge": {"dimension": "entry_timing", "direction": "delay"},
        })
    return out


def _bucket_key(o: CanonicalOutcome) -> tuple[str, str]:
    return (o.dominant_module or "unknown", o.timeframe or "?")


def report() -> dict:
    """Giriş/çıkış kalitesi özeti: module×tf kovaları + ders/öneri + en sorunlu
    kovalar. Observe-only — karar zincirine etkisi yoktur."""
    outs = [o for o in outcomes_mod.outcomes_from_state() if o.data_verified]

    grouped: dict[tuple[str, str], list[CanonicalOutcome]] = {}
    for o in outs:
        grouped.setdefault(_bucket_key(o), []).append(o)

    buckets: list[dict] = []
    verdict_counts: dict[str, int] = {}
    for (module, tf), bucket_outs in grouped.items():
        metrics = _bucket_metrics(bucket_outs)
        verdicts = _verdicts(metrics)
        for v in verdicts:
            verdict_counts[v["code"]] = verdict_counts.get(v["code"], 0) + 1
        buckets.append({
            "module": module,
            "timeframe": tf,
            "metrics": metrics,
            "verdicts": verdicts,
        })

    # Sıralama: ders taşıyan + en çok kullanılan kovalar önce (owner'ın bakacağı).
    buckets.sort(key=lambda b: (len(b["verdicts"]) > 0, b["metrics"]["n_usable"]), reverse=True)
    flagged = [b for b in buckets if b["verdicts"]]

    usable_total = sum(b["metrics"]["n_usable"] for b in buckets)
    return {
        "total": len(outs),
        "usable": usable_total,
        "min_bucket": _MIN_BUCKET,
        "verdict_counts": verdict_counts,
        "flagged_count": len(flagged),
        "buckets": buckets,
        # Slice 2 (otonom uygula) bu raporu okuyacak; observe-only şu an.
        "thresholds": {
            "capture_low": _CAPTURE_LOW,
            "give_back_high_pct": _GIVE_BACK_HIGH_PCT,
            "sl_rate_high": _SL_RATE_HIGH,
            "adverse_ratio_high": _ADVERSE_RATIO_HIGH,
        },
    }
