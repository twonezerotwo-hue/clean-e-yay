"""TF-target trainer — kapanmış paper trade'lerden TF başına SL/TP nudge.

Politika `auto_weight_trainer` ile aynı felsefe:
  - DATA_POLICY: yalnızca `data_verified=True` outcome'lar dataset'e girer.
  - Min örnek bantları: TF başına ≥MIN_TRADES_PER_TF (default 20) gerekir.
  - Trainer ÖNERİ üretir; uygulama kararını `tf_target_store` verir (hibrit:
    ±AUTO_APPLY_BAND_PCT içi auto, dışı owner onayı).

Nudge mantığı (TF başına, sınırlı delta):
  - SL-hit oranı yüksek (>HIGH_SL_HIT) VE ortalama MAE / SL_mesafe küçük
    (<TIGHT_MAE_RATIO) → SL gereksiz dar → `sl_atr_mult ↑ NUDGE_STEP`.
  - TP-hit düşük (<LOW_TP_HIT) VE time-stop oranı yüksek (>HIGH_TIMESTOP)
    VE ortalama MFE / TP_mesafe küçük (<DISTANT_TP_RATIO) → TP çok uzak →
    `rr ↓ NUDGE_STEP`.
  - MFE / TP_mesafe büyük (>RICH_MFE_RATIO, kâr masada kalıyor) → `rr ↑`.

Saf okuma + saf hesap; emir/karar üretmez (PAPER_SAFE / NO_EXECUTION).
Trainer çalıştığında verdict + öneri döner; persistance store'un işi.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from packages.data.registry.loader import load_thresholds
from packages.learning import outcomes as outcomes_mod
from packages.paper import state as paper_state

MIN_TRADES_PER_TF = 20


def _flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def auto_only_enabled() -> bool:
    """TF_TARGET_AUTO_ONLY=1 → trainer dataset'i yalnız AUTO kohort (fingerprint
    + verified). Denetim bulgusu 2026-07-03: owner_manual kayıtlar verified
    olabildiği için geometri öğrenmesine sızıyordu — tf_calibration'daki
    TF_CALIBRATION_AUTO_ONLY deseninin klonu. Default OFF (bayt-aynı)."""
    return _flag("TF_TARGET_AUTO_ONLY")


def forensics_nudge_enabled() -> bool:
    """EXIT_FORENSICS_NUDGE=1 → sabit ±%10 yerine ölçülen şiddete oranlı adım
    (klamp [0.05, 0.15]; AUTO_APPLY_BAND_PCT'yi asla aşmaz). Default OFF."""
    return _flag("EXIT_FORENSICS_NUDGE")

# Nudge eşikleri — muhafazakâr. Trigger'lar conservative kalır ki gürültüye
# nudge yapılmasın; ufak değişiklikler band içinde auto-apply olur.
HIGH_SL_HIT       = 0.45    # SL-hit oranı bu eşiğin üstünde → SL "çok sık vuruyor"
LOW_TP_HIT        = 0.25    # TP-hit oranı bu eşiğin altında → TP "ulaşılmıyor"
HIGH_TIMESTOP     = 0.30    # time-stop oranı bu eşiğin üstünde → "süre dolup düşmüş"
TIGHT_MAE_RATIO   = 0.50    # MAE / SL_mesafe < bu → SL kullanılmadan vurdu (dar)
DISTANT_TP_RATIO  = 0.50    # MFE / TP_mesafe < bu → TP'ye yaklaşmadı (uzak)
RICH_MFE_RATIO    = 0.90    # MFE / TP_mesafe > bu → TP'ye sık değdi, daha uzak çekilebilir

# CP4 slice 3 — trailing gevşetme (EXIT_EARLY). Trailing çıkış oranı yüksek VE
# yakalama (realize/MFE) düşükse trail çok sıkı kesiyor → trail_mult ↑.
HIGH_TRAILING_RATE = 0.30   # trailing-stop çıkış oranı bu eşiğin üstünde
LOW_CAPTURE        = 0.50   # ort. yakalama bu eşiğin altında → kâr masada kalıyor

# Tek seferde her parametreye uygulanan maksimum nudge oranı (%). Store ayrıca
# AUTO_APPLY_BAND_PCT ile sınırlar — bu trainer-içi ikinci güvenlik kemeri.
NUDGE_STEP = 0.10  # %10


@dataclass
class TfStats:
    timeframe: str
    trades: int
    wins: int
    win_rate: float
    sl_hit: int
    tp_hit: int
    time_stop: int
    other_exit: int
    sl_hit_rate: float
    tp_hit_rate: float
    time_stop_rate: float
    avg_mae_pct: float
    avg_mfe_pct: float
    avg_pnl: float
    # CP4 slice 3 — trailing/capture (default'lu → additive; eski testler kırılmaz).
    trailing_exit: int = 0
    trailing_rate: float = 0.0
    avg_capture: float = 1.0  # kazanan trade'lerde realize/MFE; 1.0 = tam yakalama


@dataclass
class TfNudge:
    timeframe: str
    param: str
    old: float
    new: float
    delta_pct: float
    reason: str
    # Dilim 5 additive — adımın kaynağı ("fixed" | "proportional(forensics)" |
    # "proportional(stats)") ve dayandığı ölçüm (onay kaydında/panelde görünür).
    step_source: str = "fixed"
    evidence: str = ""


# Dilim 5 (EXIT_FORENSICS_NUDGE) — oransal adım sınırları. Üst sınır
# AUTO_APPLY_BAND_PCT (0.15) ile aynı: oransal nudge hibrit-kapı semantiğini
# yapısal olarak KORUR (bant-içi auto / bant-dışı PENDING hiç değişmez).
STEP_MIN = 0.05
STEP_MAX = 0.15


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _step_for(
    rule: str, stats: TfStats, forensics_tf: dict | None, mfe_ratio: float
) -> tuple[float, str, str]:
    """Kural başına nudge adımı: flag OFF → sabit NUDGE_STEP (bayt-aynı).
    ON → ölçülen şiddete oranlı [STEP_MIN, STEP_MAX]; kanıt önce exit_forensics
    (trainer_evidence), yoksa TfStats fallback'i — ikisi de ölçüm, fake yok."""
    if not forensics_nudge_enabled():
        return NUDGE_STEP, "fixed", ""
    fx = forensics_tf or {}
    if rule == "TIGHT_SL":
        if "sl_roundtrip_share" in fx:
            s = _clamp01(float(fx["sl_roundtrip_share"]))
            src, ev = "proportional(forensics)", f"sl_roundtrip_share={fx['sl_roundtrip_share']}"
        else:
            s = _clamp01((stats.sl_hit_rate - HIGH_SL_HIT) / 0.30)
            src, ev = "proportional(stats)", f"sl_hit_rate={stats.sl_hit_rate}"
    elif rule == "DISTANT_TP":
        if "timestop_missed_ratio" in fx:
            s = _clamp01(float(fx["timestop_missed_ratio"]))
            src, ev = "proportional(forensics)", f"timestop_missed_ratio={fx['timestop_missed_ratio']}"
        else:
            s = _clamp01((DISTANT_TP_RATIO - mfe_ratio) / DISTANT_TP_RATIO)
            src, ev = "proportional(stats)", f"mfe_ratio={mfe_ratio:.2f}"
    elif rule == "RICH_MFE":
        s = _clamp01((mfe_ratio - RICH_MFE_RATIO) / 0.60)
        src, ev = "proportional(stats)", f"mfe_ratio={mfe_ratio:.2f}"
    elif rule == "TRAILING_LOOSE":
        if "trailing_giveback_ratio" in fx:
            s = _clamp01(float(fx["trailing_giveback_ratio"]))
            src, ev = "proportional(forensics)", f"trailing_giveback_ratio={fx['trailing_giveback_ratio']}"
        else:
            s = _clamp01((LOW_CAPTURE - stats.avg_capture) / LOW_CAPTURE)
            src, ev = "proportional(stats)", f"avg_capture={stats.avg_capture}"
    else:  # tanınmayan kural → güvenli sabit adım
        return NUDGE_STEP, "fixed", ""
    step = round(STEP_MIN + (STEP_MAX - STEP_MIN) * s, 4)
    return step, src, ev


@dataclass
class TfTargetProposal:
    generated_at: str
    dataset_size: int
    per_timeframe: dict[str, dict[str, float]]  # tf → params
    stats: list[TfStats]
    nudges: list[TfNudge]
    audit_note: str
    skipped: dict[str, str] = field(default_factory=dict)  # tf → neden atlandı


# close_reason → kategori. execution_sim sabitleri "SL_HIT"/"TP_HIT" (bkz.
# execution_sim.py:25-26); lifecycle bunları olduğu gibi yazar. Ayrıca
# "TIME_STOP_EXIT", "TRAILING_STOP_EXIT", "KILL_SWITCH_EXIT", "MANUAL".
# Bugfix 2026-07-03: eski eşleme "SL"/"TP" bekliyordu — canlı "SL_HIT"/"TP_HIT"
# değerleri "other"a düşüyor, sl_hit/tp_hit sayaçları HEP 0 kalıyordu (canlı
# proposal'da görüldü). TIGHT_SL/RICH_MFE kuralları bu yüzden hiç ateşlenemedi.
def _classify_close(reason: str | None) -> str:
    r = (reason or "").upper()
    if r in ("SL", "SL_HIT") or (
        "STOP" in r and "TIME" not in r and "TRAIL" not in r
    ):
        return "sl"
    if r in ("TP", "TP_HIT") or r.endswith("_TP"):
        return "tp"
    if "TIME_STOP" in r:
        return "time_stop"
    if "TRAILING" in r:
        return "trailing"
    return "other"


def _stats_for_tf(rows, timeframe: str) -> TfStats | None:
    items = [o for o in rows if o.timeframe == timeframe and o.data_verified]
    n = len(items)
    if n < MIN_TRADES_PER_TF:
        return None
    wins = sum(1 for o in items if o.pnl > 0)
    sl_hit = tp_hit = time_stop = trailing = other = 0
    captures: list[float] = []
    for o in items:
        cat = _classify_close(o.close_reason)
        if cat == "sl":
            sl_hit += 1
        elif cat == "tp":
            tp_hit += 1
        elif cat == "time_stop":
            time_stop += 1
        elif cat == "trailing":
            trailing += 1
        else:
            other += 1
        # Yakalama oranı: kazanan + lehe gitmiş trade'de realize/MFE (≤1).
        pnl_pct = getattr(o, "pnl_pct", None)
        if o.pnl > 0 and o.mfe_pct > 0.05 and pnl_pct is not None:
            captures.append(min(1.0, pnl_pct / o.mfe_pct))
    avg_mae = sum(o.mae_pct for o in items) / n
    avg_mfe = sum(o.mfe_pct for o in items) / n
    avg_pnl = sum(o.pnl for o in items) / n
    avg_capture = round(sum(captures) / len(captures), 4) if captures else 1.0
    return TfStats(
        timeframe=timeframe,
        trades=n, wins=wins, win_rate=round(wins / n, 3),
        sl_hit=sl_hit, tp_hit=tp_hit, time_stop=time_stop, other_exit=other,
        sl_hit_rate=round(sl_hit / n, 3),
        tp_hit_rate=round(tp_hit / n, 3),
        time_stop_rate=round(time_stop / n, 3),
        avg_mae_pct=round(avg_mae, 4),
        avg_mfe_pct=round(avg_mfe, 4),
        avg_pnl=round(avg_pnl, 2),
        trailing_exit=trailing,
        trailing_rate=round(trailing / n, 3),
        avg_capture=avg_capture,
    )


def _baseline_for_tf(tf: str, store_current: dict[str, dict[str, float]]) -> dict[str, float]:
    """Aktif (store override → değilse config defaults) parametreler."""
    cfg = (load_thresholds().get("timeframe_targets") or {}).get(tf) or {}
    base = {
        "sl_atr_mult": float(cfg.get("sl_atr_mult", 1.5)),
        "rr": float(cfg.get("rr", 2.0)),
        "sl_pct_floor": float(cfg.get("sl_pct_floor", 0.015)),
        "sl_pct_cap": float(cfg.get("sl_pct_cap", 0.050)),
        "trail_mult": 1.0,  # CP4 slice 3 — nötr taban; store override son sözü söyler
    }
    base.update({k: float(v) for k, v in (store_current.get(tf) or {}).items()})
    return base


def _nudge_tf(
    stats: TfStats,
    baseline: dict[str, float],
    forensics_tf: dict | None = None,
) -> tuple[dict[str, float], list[TfNudge]]:
    """TF stats + mevcut baseline → yeni parametreler + nudge gerekçeleri."""
    new = dict(baseline)
    nudges: list[TfNudge] = []
    # MAE oranı sl_distance ile değil, sl_pct_floor/baseline ile karşılaştır:
    # baseline sl_atr_mult'un yansıması ortalama SL %. Gerçek mesafe ATR'ye bağlı,
    # bu trainer TF düzeyinde nudge yapar; tam mesafe için Faz B2 tetik döngüsünde
    # ATR ortalaması da kullanılabilir. Şimdilik MAE/MFE'yi sl_pct_floor/cap'le ölç.
    typical_sl_pct = (baseline["sl_pct_floor"] + baseline["sl_pct_cap"]) / 2.0 * 100.0
    typical_tp_pct = typical_sl_pct * baseline["rr"]
    mae_ratio = stats.avg_mae_pct / typical_sl_pct if typical_sl_pct > 0 else 0.0
    mfe_ratio = stats.avg_mfe_pct / typical_tp_pct if typical_tp_pct > 0 else 0.0

    # Kural 1: SL gereksiz dar (sık vuruyor + MAE düşük) → sl_atr_mult ↑
    if stats.sl_hit_rate > HIGH_SL_HIT and mae_ratio < TIGHT_MAE_RATIO:
        step, src, ev = _step_for("TIGHT_SL", stats, forensics_tf, mfe_ratio)
        old = new["sl_atr_mult"]
        proposed = old * (1.0 + step)
        new["sl_atr_mult"] = round(proposed, 4)
        nudges.append(TfNudge(
            timeframe=stats.timeframe, param="sl_atr_mult",
            old=old, new=new["sl_atr_mult"], delta_pct=step,
            reason=f"sl_hit_rate={stats.sl_hit_rate} > {HIGH_SL_HIT}; "
                   f"avg_mae/typical_sl={mae_ratio:.2f} < {TIGHT_MAE_RATIO} → stop çok dar",
            step_source=src, evidence=ev,
        ))

    # Kural 2: TP çok uzak (ulaşılmıyor + time-stop yüksek + MFE düşük) → rr ↓
    if (stats.tp_hit_rate < LOW_TP_HIT
            and stats.time_stop_rate > HIGH_TIMESTOP
            and mfe_ratio < DISTANT_TP_RATIO):
        step, src, ev = _step_for("DISTANT_TP", stats, forensics_tf, mfe_ratio)
        old = new["rr"]
        proposed = old * (1.0 - step)
        new["rr"] = round(proposed, 4)
        nudges.append(TfNudge(
            timeframe=stats.timeframe, param="rr",
            old=old, new=new["rr"], delta_pct=-step,
            reason=f"tp_hit={stats.tp_hit_rate} < {LOW_TP_HIT}; "
                   f"time_stop={stats.time_stop_rate} > {HIGH_TIMESTOP}; "
                   f"avg_mfe/typical_tp={mfe_ratio:.2f} < {DISTANT_TP_RATIO} → TP çok uzak",
            step_source=src, evidence=ev,
        ))

    # Kural 3: Kâr masada kalıyor (MFE >> TP) → rr ↑
    elif mfe_ratio > RICH_MFE_RATIO and stats.tp_hit_rate > 0.5:
        step, src, ev = _step_for("RICH_MFE", stats, forensics_tf, mfe_ratio)
        old = new["rr"]
        proposed = old * (1.0 + step)
        new["rr"] = round(proposed, 4)
        nudges.append(TfNudge(
            timeframe=stats.timeframe, param="rr",
            old=old, new=new["rr"], delta_pct=step,
            reason=f"avg_mfe/typical_tp={mfe_ratio:.2f} > {RICH_MFE_RATIO}; "
                   f"tp_hit={stats.tp_hit_rate} > 0.5 → kâr genişletilebilir",
            step_source=src, evidence=ev,
        ))

    # Kural 4 (CP4 slice 3): trailing erken kesiyor (yüksek trailing oranı + düşük
    # yakalama) → trail_mult ↑ (trail gevşer, kâr daha çok koşar). entry_exit_quality
    # EXIT_EARLY bulgusunun geometriye uygulanan karşılığı.
    if stats.trailing_rate > HIGH_TRAILING_RATE and stats.avg_capture < LOW_CAPTURE:
        step, src, ev = _step_for("TRAILING_LOOSE", stats, forensics_tf, mfe_ratio)
        old = new.get("trail_mult", 1.0)
        proposed = old * (1.0 + step)
        new["trail_mult"] = round(proposed, 4)
        nudges.append(TfNudge(
            timeframe=stats.timeframe, param="trail_mult",
            old=old, new=new["trail_mult"], delta_pct=step,
            reason=f"trailing_rate={stats.trailing_rate} > {HIGH_TRAILING_RATE}; "
                   f"avg_capture={stats.avg_capture} < {LOW_CAPTURE} → trail çok sıkı",
            step_source=src, evidence=ev,
        ))

    return new, nudges


def train(
    timeframes: list[str] | None = None,
    store_overrides: dict[str, dict[str, float]] | None = None,
) -> TfTargetProposal | dict:
    """Trainer ana giriş. Yeterli veri yoksa açıklayıcı dict döner."""
    tfs = timeframes or ["15m", "1h", "4h", "1d"]
    s = paper_state.load()
    rows = outcomes_mod.outcomes_from_state(s)
    # Dilim 4 (TF_TARGET_AUTO_ONLY, default OFF): flag ON → yalnız AUTO kohort
    # (fingerprint + verified) — owner_manual verified kayıtlar geometri
    # öğrenmesine sızmaz. OFF → mevcut data_verified filtresi bayt-aynı.
    if auto_only_enabled():
        from packages.learning import cohorts  # döngüsel import kaçınması
        verified = [o for o in rows if cohorts.classify(o) == cohorts.AUTO]
        dataset_tag = "auto_cohort"
    else:
        verified = [o for o in rows if o.data_verified]
        dataset_tag = "verified"
    if not verified:
        return {"status": "INSUFFICIENT", "reason": "no_verified_trades",
                "dataset_size": 0}

    store_cur = store_overrides if store_overrides is not None else {}
    proposal_tfs: dict[str, dict[str, float]] = {}
    all_stats: list[TfStats] = []
    all_nudges: list[TfNudge] = []
    skipped: dict[str, str] = {}

    # Dilim 5 (EXIT_FORENSICS_NUDGE, default OFF): flag ON → exit_forensics'ten
    # TF-başı şiddet kanıtı çek; veri yetersiz/hata → {} (kural stats fallback'ine
    # veya sabit adıma düşer — sahte kanıt üretilmez). OFF → hiç dokunulmaz.
    forensics_evidence: dict[str, dict] = {}
    if forensics_nudge_enabled():
        try:
            from packages.learning import exit_forensics
            forensics_evidence = exit_forensics.trainer_evidence(rows) or {}
        except Exception:
            forensics_evidence = {}

    for tf in tfs:
        st = _stats_for_tf(verified, tf)
        if st is None:
            tf_count = sum(1 for o in verified if o.timeframe == tf)
            skipped[tf] = f"insufficient_trades (have={tf_count}, need={MIN_TRADES_PER_TF})"
            continue
        all_stats.append(st)
        baseline = _baseline_for_tf(tf, store_cur)
        new_params, nudges = _nudge_tf(st, baseline, forensics_evidence.get(tf))
        if nudges:  # sadece değişiklik varsa proposal'a koy
            proposal_tfs[tf] = new_params
            all_nudges.extend(nudges)

    return TfTargetProposal(
        generated_at=datetime.now(UTC).isoformat(),
        dataset_size=len(verified),
        per_timeframe=proposal_tfs,
        stats=all_stats,
        nudges=all_nudges,
        audit_note=(
            f"dataset={dataset_tag}; {len(verified)} outcome incelendi; "
            f"{len(all_stats)} TF MIN_TRADES_PER_TF={MIN_TRADES_PER_TF} eşiğini geçti; "
            f"{len(all_nudges)} nudge önerildi; {len(skipped)} TF atlandı."
        ),
        skipped=skipped,
    )


def proposal_to_dict(p: TfTargetProposal) -> dict:
    return {
        "generated_at": p.generated_at,
        "dataset_size": p.dataset_size,
        "per_timeframe": dict(p.per_timeframe),
        "stats": [asdict(s) for s in p.stats],
        "nudges": [asdict(n) for n in p.nudges],
        "audit_note": p.audit_note,
        "skipped": dict(p.skipped),
    }


__all__ = [
    "MIN_TRADES_PER_TF",
    "TfNudge",
    "TfStats",
    "TfTargetProposal",
    "proposal_to_dict",
    "train",
]
