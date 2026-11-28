"""Learning worker — periyodik kalibrasyon + walk-forward + auto-weight proposal.

L1 — her koşu run metadata üretir (run_id / status / skipped_reason /
outcomes_seen / proposals_generated / calibration_status / errors). Boş veri →
NO_DATA; beklenmedik hata → COMPLETED_WITH_ERRORS (worker ASLA patlamaz).
active weights owner approval olmadan DEĞİŞMEZ.

Çalıştırma:
    python -m apps.learning_worker.main
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from packages.ops.env import load_repo_dotenv

load_repo_dotenv(skip_pytest=True)

# Learning modules read provider/threshold credentials during import.
# ruff: noqa: E402
from packages import discovery
from packages.discovery import sector_rotation
from packages.learning import (
    activation_watchdog,
    calibration_trainer,
    empirical_pwin,
    exit_forensics,
    guard_safety,
    rebalance_store,
    run_store,
    tf_calibration,
    tf_target_store,
    tf_target_trainer,
    tf_weight_trainer,
    threshold_trainer,
)
from packages.learning import auto_weight_trainer as trainer
from packages.learning import (
    outcomes as outcomes_mod,
)
from packages.learning.summary import build_summary
from packages.ops import heartbeat
from packages.ops.store import write_text_atomic

log = logging.getLogger("learning_worker")

WORKER_NAME = "learning_worker"

# Learning run status → heartbeat status eşlemesi.
_HB_STATUS = {
    "COMPLETED": "OK",
    "COMPLETED_WITH_ERRORS": "DEGRADED",
    "NO_DATA": "NO_DATA",
}

OUT_PATH = Path(os.environ.get("LEARNING_OUT_PATH", "data/runtime/learning_summary.json"))
TF_CALIBRATION_OUT_PATH = Path(
    os.environ.get("TF_CALIBRATION_OUT_PATH", "data/runtime/tf_calibration.json")
)
TF_WEIGHT_PROPOSAL_OUT_PATH = Path(
    os.environ.get("TF_WEIGHT_PROPOSAL_OUT_PATH", "data/runtime/tf_weight_proposal.json")
)
TF_TARGET_PROPOSAL_OUT_PATH = Path(
    os.environ.get("TF_TARGET_PROPOSAL_OUT_PATH", "data/runtime/tf_target_proposal.json")
)
# Son tf_target çalışmasının dataset_size'ını burada tutuyoruz; bir sonraki
# döngüde yalnızca outcomes_seen bundan ≥ TF_TARGET_MIN_NEW kadar arttıysa
# trainer'ı tekrar çağırıyoruz (örnek-kapılı tetik). Periyodik kısım loop'un
# kendisi (her gecelik koşu).
TF_TARGET_TRIGGER_PATH = Path(
    os.environ.get("TF_TARGET_TRIGGER_PATH", "data/runtime/tf_target_trigger.json")
)
TF_TARGET_MIN_NEW = int(os.environ.get("TF_TARGET_MIN_NEW", "20"))


# CP1 — performans bütçesi: learning koşusu bu süreyi aşarsa WARN + run meta'da
# over_budget=True. Tick'e dokunmaz; yalnız off-tick learning loop'unu izler ki
# yeni öğrenici eklendikçe sistem sessizce AĞIRLAŞMASIN (ana kural).
LEARNING_BUDGET_MS = int(os.environ.get("LEARNING_BUDGET_MS", "60000"))

# Salt-gözlem gölgeleri canlı karar döngüsünü beslemez; bu yüzden her learning
# tick'inde aynı tarihçeyi baştan hesaplamak gereksiz CPU/IO yüküdür.  Artifact
# yaşını kapı olarak kullanıyoruz: dosya yoksa ilk koşu yapılır, mevcutsa yalnız
# gözlem aralığı dolduğunda yeniden hesaplanır. Tarihçe silinmez ve karar motoru
# bu kapılardan etkilenmez.
NEWS_EVENT_STUDY_PATH = Path(
    os.environ.get("NEWS_EVENT_STUDY_PATH", "data/runtime/news_event_study.json")
)
CAUSAL_CALIBRATION_PATH = Path(
    os.environ.get("CAUSAL_CALIBRATION_PATH", "data/runtime/causal_calibration.json")
)
NEWS_EVENT_STUDY_INTERVAL_SEC = int(
    os.environ.get("NEWS_EVENT_STUDY_INTERVAL_SEC", "900")
)
CAUSAL_OBSERVE_INTERVAL_SEC = int(
    os.environ.get("CAUSAL_OBSERVE_INTERVAL_SEC", "604800")
)


def _artifact_due(path: Path, interval_sec: int) -> bool:
    """Return whether a shadow artifact is due for a fresh calculation.

    Missing/unreadable files are treated as due so a damaged observation
    artifact is self-healed on the next learning run. This helper is deliberately
    independent of decision/risk code.
    """
    if interval_sec <= 0 or not path.exists():
        return True
    try:
        age_sec = datetime.now(UTC).timestamp() - path.stat().st_mtime
    except OSError:
        return True
    return age_sec >= interval_sec


def _tf_target_should_run(outcomes_seen: int) -> tuple[bool, int]:
    """Örnek-kapılı tetik: son çalıştırmadan beri ≥TF_TARGET_MIN_NEW yeni outcome
    biriktiyse True. İlk çalıştırma (state yoksa) True. (gate, last_seen)."""
    try:
        if TF_TARGET_TRIGGER_PATH.exists():
            data = json.loads(TF_TARGET_TRIGGER_PATH.read_text(encoding="utf-8"))
            last = int(data.get("last_outcomes_seen", 0))
            return (outcomes_seen - last >= TF_TARGET_MIN_NEW, last)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return True, 0


def _tf_target_save_trigger(outcomes_seen: int) -> None:
    try:
        write_text_atomic(
            TF_TARGET_TRIGGER_PATH,
            json.dumps({"last_outcomes_seen": outcomes_seen,
                        "updated_at": datetime.now(UTC).isoformat()}, indent=2),
        )
    except OSError:
        pass


def _learned_drift() -> dict:
    """Donmuş canlı tablolar ile son öneri arasındaki fark (26 Kasım 2026, owner: "önce
    dondur"). Canlı tablo yalnız owner onayıyla (öneri dosyasının kopyası) değişir."""
    from packages.learning import calibration_store, empirical_pwin, regime_risk_brake

    def _read(path) -> dict:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    out: dict = {}
    live, prop = _read(calibration_store._store_path()), _read(calibration_store._proposal_path())
    if prop:
        tfs = sorted({*(live.get("per_timeframe") or {}), *(prop.get("per_timeframe") or {})})
        out["calibration"] = {
            tf: [(src.get("per_timeframe") or {}).get(tf, {}).get(k) for src in (live, prop) for k in ("a", "b")]
            for tf in tfs
        }
    live, prop = _read(empirical_pwin._path()), _read(empirical_pwin._proposal_path())
    if prop:
        need = int(prop.get("min_samples") or 20)
        lc, pc = live.get("cells") or {}, prop.get("cells") or {}
        changed = [
            k for k in sorted({*lc, *pc})
            if ((lc.get(k) or {}).get("n", 0) >= need) != ((pc.get(k) or {}).get("n", 0) >= need)
            or abs(float((lc.get(k) or {}).get("p_win") or 0) - float((pc.get(k) or {}).get("p_win") or 0)) >= 0.05
        ]
        out["empirical_pwin"] = {"cells_changed": changed, "cells_live": len(lc), "cells_proposal": len(pc)}
    live, prop = _read(regime_risk_brake._path()), _read(regime_risk_brake._proposal_path())
    if prop:
        out["regime_brake"] = {"live": live.get("braked_regimes") or [], "proposal": prop.get("braked_regimes") or []}
    return out


def _err(step: str, exc: BaseException) -> str:
    """Hata kaydı: 'adım:Tür: mesaj' (mesaj ilk 200 karakter; 26 Kasım 2026'ya dek yalnız tür)."""
    msg = " ".join(str(exc).split())[:200]
    return f"{step}:{type(exc).__name__}" + (f": {msg}" if msg else "")


def run_once() -> dict:
    """Tek learning koşusu; run metadata döner + run_store'a yazar."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    errors: list[str] = []
    laps: list[tuple[str, float]] = []  # adım süreleri (26 Kasım 2026)
    proposals_generated = 0
    calibration_status = "UNKNOWN"
    tf_calibration_status = "UNKNOWN"
    tf_weights_trusted = False
    tf_weight_proposal_status = "UNKNOWN"
    skipped_reason: str | None = None
    rebalance_decision: str | None = None  # pending | no_change
    guard_safety_status: dict = {}          # CP3: yön guard kasası (armed/rolled_back/...)
    activation_watchdog_status: dict = {}   # F5-3: owner-flag izleyici (yalnız-öneri)

    laps.append(("outcomes", time.monotonic()))
    try:
        outcomes_seen = len(outcomes_mod.outcomes_from_state())
    except Exception as exc:  # defensive — worker patlamamalı
        outcomes_seen = 0
        errors.append(_err("outcomes", exc))

    # Makro arşiv derinlik bekçisi (2026-07-13): fundamental_v4/rejim-momentum
    # 379+ gün DXY/US10Y ister; data/runtime git'e girmediği için her ortam
    # kendi arşivini kendisi doldurur (lokal↔AWS senkron, kural 6). Derinse
    # no-op; sığsa tek-seferlik 5y backfill (süreç-memo + 6h retry guard).
    macro_backfill_status: dict = {}
    laps.append(("macro_backfill", time.monotonic()))
    try:
        from packages.learning import macro_backfill
        macro_backfill_status = macro_backfill.ensure_depth()
        if macro_backfill_status.get("status") != "DEEP":
            log.info("macro_backfill: %s", macro_backfill_status)
    except Exception as exc:  # defensive
        errors.append(_err("macro_backfill", exc))

    # Piyasa şoku bildirimi (salt gözlem, 13 Kasım 2026 owner onayı): son tamamlanmış
    # 1h barlarda oynaklığa göre sert hareket varsa owner'a "ne oluyor, kimi etkiler,
    # sistem ne görüyor" özeti. Karara, kapılara ve pozisyonlara dokunmaz.
    laps.append(("market_shock", time.monotonic()))
    try:
        from packages.notifications import append_many as _notify_many
        from packages.notifications import market_shock as _market_shock
        _shock_notifs = _market_shock.check()
        if _shock_notifs:
            _notify_many(_shock_notifs)
            log.info("market_shock: %d bildirim", len(_shock_notifs))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("market_shock", exc))

    # Günlük "neden kaçırdım" incelemesi (salt gözlem, 13 Kasım 2026 owner onayı): dünün
    # büyük hareketleri, sistemin onlara karşı ne yaptığı ve hangi kapının durdurduğu.
    # Günde bir kez (00:15 UTC sonrası ilk koşu); karara dokunmaz.
    laps.append(("daily_review", time.monotonic()))
    try:
        from packages.learning import daily_review as _daily_review
        _review = _daily_review.run_if_due()
        if _review is not None:
            log.info("daily_review: %s, %d büyük hareket", _review["day"], len(_review["movers"]))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("daily_review", exc))

    # Özet (boş state'te de güvenli — total=0).
    laps.append(("summary", time.monotonic()))
    try:
        summary = build_summary()
        write_text_atomic(OUT_PATH, json.dumps(summary, indent=2, default=str))
        log.info(
            "learning_summary written: total=%s win_rate=%s sharpe=%s",
            summary.get("total_trades"),
            summary.get("win_rate"),
            summary.get("sharpe"),
        )
    except Exception as exc:  # defensive
        errors.append(_err("summary", exc))

    # G6: confidence calibration. Yetersiz veri → identity (a=1, b=0).
    laps.append(("calibration", time.monotonic()))
    try:
        cal = calibration_trainer.train()
        calibration_status = str(cal.get("status", "UNKNOWN"))
        # F4-1 — per-TF Platt gözlemi: hangi TF'ler fit edildi (aktivasyon kanıtı).
        log.info(
            "calibration: %s n=%s tf_fitted=%s",
            calibration_status, cal.get("samples"), cal.get("tf_fitted") or [],
        )
    except Exception as exc:  # defensive
        errors.append(_err("calibration", exc))

    # F4-2 — ampirik p(win) tablosu: (tf|rejim) hit-rate artifact'ı. Karar
    # motoru okur (flag kapalıyken salt-gözlem alanları için).
    laps.append(("empirical_pwin", time.monotonic()))
    try:
        emp_table = empirical_pwin.write_table()
        log.info(
            "empirical_pwin: cells=%s sufficient=%s",
            emp_table.get("cell_count"), emp_table.get("sufficient_count"),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("empirical_pwin", exc))

    # Çıkış Otopsisi (denetim 2026-07-03) — kötü çıkışın nerede/kaça olduğu
    # (AUTO kohort, observe-only). Snapshot + trend geçmişi; panel/API okur.
    exit_forensics_status = "SKIPPED"
    laps.append(("exit_forensics", time.monotonic()))
    try:
        ef = exit_forensics.write_snapshot()
        ef_latest = ef.get("latest") or {}
        exit_forensics_status = "OK"
        log.info(
            "exit_forensics: usable=%s buckets=%s top_costs=%s",
            ef_latest.get("usable"),
            len(ef_latest.get("buckets") or []),
            len(ef_latest.get("top_costs") or []),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        exit_forensics_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("exit_forensics", exc))

    # Step 8 — per-TF calibration + tf_weights trust gate. Derives per-timeframe
    # hit-rate/expectancy from VERIFIED outcomes and the trust verdict (PRIOR until a
    # TF has enough evidence). Persisted as a durable artifact so the trust gate reads
    # a stable as-of-last-run verdict. Attribution-based weight AUTO-TUNE stays deferred
    # (no faking): this lands the honest calibration + trust gate, not weight moves.
    laps.append(("tf_calibration", time.monotonic()))
    try:
        tf_report = tf_calibration.calibration_report()
        tf_weights_trusted = bool(tf_report.get("tf_weights_trusted", False))
        tf_calibration_status = "TRUSTED" if tf_weights_trusted else "PRIOR"
        write_text_atomic(TF_CALIBRATION_OUT_PATH, json.dumps(tf_report, indent=2, default=str))
        log.info(
            "tf_calibration: %s trusted_tfs=%s",
            tf_calibration_status,
            tf_report.get("calibrated_timeframes"),
        )
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("tf_calibration", exc))

    # Step 8 — tf_weights auto-tune PROPOSAL (trust-gated). Owner approves; live weights
    # are NEVER auto-moved here. Until a TF is calibrated this skips (the normal state).
    laps.append(("tf_weight", time.monotonic()))
    try:
        proposal = tf_weight_trainer.propose()
        if isinstance(proposal, tf_weight_trainer.TfWeightProposal):
            tf_weight_proposal_status = "PROPOSED"
            payload = tf_weight_trainer.proposal_to_dict(proposal)
        else:
            tf_weight_proposal_status = str(proposal.get("reason", "skipped"))
            payload = proposal
        write_text_atomic(TF_WEIGHT_PROPOSAL_OUT_PATH, json.dumps(payload, indent=2, default=str))
        log.info("tf_weight proposal: %s", tf_weight_proposal_status)
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("tf_weight", exc))

    # TF-target trainer (Faz B): TF başına SL/TP geometri nudge önerisi; store'a PENDING
    # yazılır, yalnız owner uygular. Tetik örnek-kapılı: son koşudan beri
    # ≥TF_TARGET_MIN_NEW yeni outcome biriktiyse çalışır.
    tf_target_status = "SKIPPED"
    tf_target_decisions: dict[str, str] = {}
    laps.append(("tf_target", time.monotonic()))
    try:
        should_run, last_seen = _tf_target_should_run(outcomes_seen)
        if not should_run:
            tf_target_status = (
                f"GATE_PENDING (have={outcomes_seen} last={last_seen} "
                f"need_new>={TF_TARGET_MIN_NEW})"
            )
            log.info("tf_target_trainer: %s", tf_target_status)
        else:
            tt_result = tf_target_trainer.train(
                store_overrides=tf_target_store.active_overrides()
            )
            if isinstance(tt_result, tf_target_trainer.TfTargetProposal):
                payload = tf_target_trainer.proposal_to_dict(tt_result)
                if tt_result.per_timeframe:
                    rec = tf_target_store.submit_proposal(payload)
                    tf_target_decisions = dict(rec.get("decisions") or {})
                    tf_target_status = "PROPOSED"
                else:
                    tf_target_status = "NO_NUDGE"
                write_text_atomic(TF_TARGET_PROPOSAL_OUT_PATH, json.dumps(payload, indent=2, default=str))
            else:
                tf_target_status = str(tt_result.get("status", "UNKNOWN"))
            _tf_target_save_trigger(outcomes_seen)
            log.info("tf_target_trainer: %s decisions=%s",
                     tf_target_status, tf_target_decisions)
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("tf_target", exc))

    # Ağırlık eğiticisi: yeterli veri varsa öneri üretilir ve PENDING kaydedilir; ağırlık
    # yalnız owner onayıyla değişir (oto-uygulama 26 Kasım 2026'da kalktı).
    laps.append(("trainer", time.monotonic()))
    try:
        result = trainer.train()
        if isinstance(result, trainer.RebalanceProposal):
            saved = rebalance_store.set_pending(trainer.proposal_to_dict(result))
            rebalance_decision = "no_change" if saved.get("status") == "NO_CHANGE" else "pending"
            proposals_generated = 1
            log.info(
                "rebalance proposal %s: %s → %s (n=%s)",
                rebalance_decision,
                result.from_version,
                result.to_version,
                result.dataset_size,
            )
        else:
            skipped_reason = result.get("reason")
            log.info("rebalance trainer skipped: %s", result)
    except Exception as exc:  # defensive
        errors.append(_err("trainer", exc))

    # Eşik önericisi: allowlist eşiklerini backtest'le dener, öneriyi geçmişe yazar.
    # Canlı eşiği DEĞİŞTİRMEZ (otomatik uygulama 21 Kasım 2026 owner kararıyla kalktı).
    laps.append(("threshold_trainer", time.monotonic()))
    try:
        tt = threshold_trainer.train()
        if tt.get("status") == "PROPOSED":
            log.info("threshold PROPOSED (owner inceler): %s", tt.get("evaluated"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("threshold_trainer", exc))

    # CP3: yön güvenlik kasası. Owner bir guard'ı canlıya aldıysa izlemeye alır;
    # yeterli yeni outcome birikince post-enable expectancy baseline'ın altına
    # düşerse guard'ı oto-kapatır (kill-override). Geçiş yoksa sessiz (no-op).
    laps.append(("guard_safety", time.monotonic()))
    try:
        guard_safety_status = guard_safety.run()
        if guard_safety_status.get("armed"):
            log.info("guard_safety ARMED: %s", guard_safety_status["armed"])
        if guard_safety_status.get("rolled_back"):
            log.info("guard_safety ROLLBACK: %s", guard_safety_status["rolled_back"])
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("guard_safety", exc))

    # F5-3 — aktivasyon watchdog'u: owner-flag OFF→ON geçişlerini izler,
    # post-enable expectancy düşerse DEGRADED önerir (YALNIZ-ÖNERİ — hiçbir
    # flag'i oto-kapatmaz; yön guard'larının oto-kapatlı kasası yukarıda).
    laps.append(("activation_watchdog", time.monotonic()))
    try:
        aw = activation_watchdog.run()
        activation_watchdog_status = aw
        if aw.get("armed"):
            log.info("activation_watchdog ARMED: %s", aw["armed"])
        if aw.get("degraded"):
            log.info("activation_watchdog DEGRADED (öneri): %s", aw["degraded"])
    except Exception as exc:  # defensive — worker patlamamalı
        activation_watchdog_status = {}
        errors.append(_err("activation_watchdog", exc))

    # K-0b — keşif: sektör rotasyon motoru (DISCOVERY_SCAN_ENABLED, default
    # OFF → tam no-op: ağa çıkmaz, dosya yazmaz, learning koşusu bayt-eşdeğer).
    # Açıkken saatte bir (interval_sec) 12 sektör ETF'sinin S&P'ye göreli gücünü
    # ölçer + karne damgası/çözümü; canlı karar zincirine dokunmaz (salt-gözlem).
    discovery_status = "DISABLED"
    laps.append(("sector_rotation", time.monotonic()))
    try:
        if discovery.scan_enabled():
            sr = sector_rotation.run_if_due()
            discovery_status = str(sr.get("status", "UNKNOWN"))
            if discovery_status == "OK":
                log.info(
                    "sector_rotation: rising=%s unavailable=%s stamped=%s resolved_new=%s",
                    sr.get("rising"), sr.get("unavailable_n"),
                    sr.get("stamped"), sr.get("resolved_new"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("sector_rotation", exc))

    # Haber güdümlü keşif (owner kararı 2026-10-05, ikinci tur; aynı kapı): tüm haber
    # akışından yerel YZ olay → sonuç → etkilenen varlık çıkarır, sembol Yahoo'da
    # doğrulanır. Tarayıcıdan ÖNCE koşar: doğrulanan adaylar aynı turda taranabilir.
    # SALT-GÖZLEM; yerel model yoksa (AWS) LOCAL_LLM_OFF, ortak LLM bütçesini harcamaz.
    news_discovery_status = "DISABLED"
    laps.append(("news_discovery", time.monotonic()))
    try:
        if discovery.scan_enabled():
            from packages.discovery import news_discovery
            nd = news_discovery.run()
            news_discovery_status = str(nd.get("status", "UNKNOWN"))
            log.info(
                "news_discovery: status=%s screened=%s events=%s proposed=%s valid=%s registry=%s "
                "rejected=%s candidates=%s errors=%s",
                news_discovery_status, nd.get("screened"), nd.get("events"), nd.get("proposed"),
                nd.get("valid"), nd.get("registry"), nd.get("rejected"), nd.get("candidates"), nd.get("errors"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        news_discovery_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("news_discovery", exc))

    # K-1 — keşif tarayıcısı (aynı flag): kota kadar adayı (sıcak sektör ETF'leri
    # + kripto kısa listesi) gölge analiz eder, yalnız artifact yazar. İşlem
    # AÇMAZ; RiskGate'e girmez. Import lazy — flag kapalıyken decision-engine
    # bağımlılıkları hiç yüklenmez (bayt-eşdeğer koşu).
    discovery_scan_status = "DISABLED"
    laps.append(("discovery_scan", time.monotonic()))
    try:
        if discovery.scan_enabled():
            from packages.discovery import scanner as discovery_scanner
            sc = discovery_scanner.run_if_due()
            discovery_scan_status = str(sc.get("status", "UNKNOWN"))
            if discovery_scan_status == "OK":
                log.info(
                    "discovery_scan: scanned=%s signals=%s candidates=%s shadow=%s",
                    sc.get("scanned"), sc.get("signals_n"),
                    sc.get("candidates_total"), sc.get("shadow"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_scan_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("discovery_scan", exc))

    # Haber öngörüsü (owner kararı 2026-10-05, aynı kapı): RSS + sınırlı web
    # araması → varlık başına yön/güç + öngörü karnesi. SALT-GÖZLEM: karar/
    # boyut/RiskGate/evren değişmez; fikir panosunu besler.
    news_forecast_status = "DISABLED"
    laps.append(("news_forecast", time.monotonic()))
    try:
        if discovery.scan_enabled():
            from packages.discovery import news_forecast
            nf = news_forecast.run()
            news_forecast_status = str(nf.get("status", "UNKNOWN"))
            log.info(
                "news_forecast: headlines=%s +rss=%s +web=%s forecasts=%s directional=%s "
                "karne(created=%s resolved=%s open=%s) web_errors=%s",
                nf.get("headlines"), nf.get("added_rss"), nf.get("added_web"), nf.get("forecasts"),
                nf.get("directional"), nf.get("created"), nf.get("resolved"), nf.get("open"),
                nf.get("web_errors"),
            )
    except Exception as exc:  # defensive — worker patlamamalı
        news_forecast_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("news_forecast", exc))

    # Kritik durum yedeği (hedef mimari 1. aşama): günde bir kez sıkıştırılmış
    # kopya + geçici klasöre geri yükleme denemesi. Yalnız okur; karar etkisi yok.
    laps.append(("runtime_backup", time.monotonic()))
    try:
        from packages.ops import backup as runtime_backup

        bk = runtime_backup.run_if_due()
        if bk.get("ran"):
            log.info("runtime_backup: %s %s", bk.get("status"), bk.get("archive"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("runtime_backup", exc))

    # Operasyon alarmları (hedef mimari 1. aşama): tick, kaynak, kota ve yedek
    # sorunlarını zile yazar; sessiz hata kalmasın. Salt gözlem, karar etkisi yok.
    laps.append(("ops_alerts", time.monotonic()))
    try:
        from packages.ops import alerts as ops_alerts

        al = ops_alerts.evaluate()
        if al.get("sent"):
            log.info("ops_alerts: active=%s sent=%s", al.get("active"), al.get("sent"))
    except Exception as exc:  # defensive — worker patlamamalı
        errors.append(_err("ops_alerts", exc))

    # Haber → karar geçmiş karşılaştırması. Runtime shadow yazımı kapalıdır;
    # eski dosyalar silinmez, yalnızca audit için korunur.

    # Fikir Panosu (owner kararı 2026-10-05, aynı kapı): keşif + haber + teknik →
    # şeffaf fikir skoru + YZ değerlendirmesi (yerel model; turda en çok 2 çağrı,
    # yoksa kurallı yedek). Terfiden ÖNCE koşar: YZ hükmü pakete kanıt olur.
    ideas_status = "DISABLED"
    laps.append(("ideas", time.monotonic()))
    try:
        if discovery.scan_enabled():
            from packages.discovery import ideas
            ib = ideas.run()
            ideas_status = str(ib.get("status", "UNKNOWN"))
            log.info("ideas: n=%s llm_calls=%s top=%s reviews=%s errors=%s",
                     ib.get("ideas"), ib.get("llm_calls"), ib.get("top"), ib.get("reviews"),
                     ib.get("llm_errors"))
    except Exception as exc:  # defensive — worker patlamamalı
        ideas_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("ideas", exc))

    # K-4 — keşif adayı TERFİ kriteri (aynı DISCOVERY_SCAN_ENABLED kapısı):
    # tarayıcı+defter tazelendikten SONRA aday gölge karnesini üç eşiğe (≥20
    # çözüm + ≥2 TF + Wilson alt sınırı > 0.5) vurur; geçen aday için governor
    # defterine STRATEGY_ENABLE paketi (add_custom_asset, dedupe'lu). Varlık
    # OTOMATİK EKLENMEZ — onay bile canlı evreni değiştirmez (KIRMIZI ÇİZGİ).
    discovery_promotion_status = "DISABLED"
    laps.append(("discovery_promotion", time.monotonic()))
    try:
        if discovery.scan_enabled():
            from packages.discovery import promotion as discovery_promotion
            dp = discovery_promotion.run()
            discovery_promotion_status = str(dp.get("status", "UNKNOWN"))
            if discovery_promotion_status == "READY":
                log.info(
                    "discovery_promotion READY — owner paketi sunuldu "
                    "(ready=%s proposal_ids=%s)",
                    dp.get("ready_symbols"), dp.get("proposal_ids"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        discovery_promotion_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("discovery_promotion", exc))

    # Rejim risk freni önerisi: AUTO kohort ortalama net R < 0 (min örnek) → fren.
    # Öneri dosyasına yazılır; engine donmuş canlı tabloyu okur (owner onayıyla değişir).
    regime_brake_status = "ERROR"
    laps.append(("regime_risk_brake", time.monotonic()))
    try:
        from packages.learning import regime_risk_brake as _rrb
        rb = _rrb.compute()
        regime_brake_status = "OK"
        if rb.get("braked_regimes"):
            log.info("regime_risk_brake: braked=%s", rb.get("braked_regimes"))
    except Exception as exc:  # defensive — worker patlamamalı
        regime_brake_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("regime_risk_brake", exc))

    # Y-6 — haber olay-çalışması (SALT-GÖZLEM). Off-tick: o anki verified haberleri
    # damgala (dedupe) + olgunlaşan olaylar için N-bar ileri-getiri karnesi
    # (ohlcv.history REUSE). Kanıt bar-arşivi gibi haftayla büyür; karara dokunmaz.
    news_study_status = "SKIP_NOT_DUE"
    if _artifact_due(NEWS_EVENT_STUDY_PATH, NEWS_EVENT_STUDY_INTERVAL_SEC):
        try:
            from packages.learning import news_event_study as _nes
            recorded = _nes.record_events()
            nt = _nes.compute()
            # Causal graph observation is deliberately off-tick. It is much
            # heavier than the ordinary news table, so it runs weekly rather
            # than once per learning tick. It never feeds orders or weights.
            causal_recorded = 0
            calibration_runtime = {"status": "SKIPPED_NOT_DUE"}
            if _artifact_due(CAUSAL_CALIBRATION_PATH, CAUSAL_OBSERVE_INTERVAL_SEC):
                try:
                    from packages.causal.engine import build_event_asset_attribution
                    from packages.causal.engine import build_shadow as _build_shadow
                    from packages.data.ingestion.pipeline import get_cached_snapshot
                    from packages.data.registry import assets as _asset_registry
                    from packages.world_state import archive as _world_archive
                    from packages.world_state.engine import build as _build_world
                    _cached_snapshot = get_cached_snapshot()
                    _world = _build_world(_cached_snapshot)
                    _shadow = _build_shadow(
                        _world,
                        _asset_registry.trade_symbols(),
                        technicals=(getattr(_cached_snapshot, "technicals_by_tf", None) or getattr(_cached_snapshot, "technicals", None)),
                        prices={quote.symbol: quote for quote in getattr(_cached_snapshot, "prices", ())},
                        volatility=getattr(_cached_snapshot, "volatility", None),
                    )
                    _world_archive.record(
                        _world,
                        snapshot_id=getattr(_cached_snapshot, "snapshot_id", None),
                        asset_impacts=_shadow.impacts,
                        causal_consensus=_shadow.causal_consensus,
                        edges=_shadow.edges,
                        forecasts=_shadow.forecasts,
                        reconstruction_inputs={
                            "snapshot_id": getattr(_cached_snapshot, "snapshot_id", None),
                            "source": "snapshot_store",
                        },
                    )
                    by_event = []
                    symbols = _asset_registry.trade_symbols()
                    for event in _world.geopolitical_events:
                        item = event.to_dict()
                        item.update(build_event_asset_attribution(item, symbols))
                        by_event.append(item)
                    for event in _world.macro_surprises:
                        item = event.to_dict()
                        channels = {
                            key: value for key, value in {
                                "inflation_pressure": event.inflation_contribution,
                                "growth_pressure": event.growth_contribution,
                                "rates_pressure": event.rates_contribution,
                                "oil_pressure": event.oil_contribution,
                            }.items() if value
                        }
                        item["channels"] = channels
                        item["source_confidence"] = event.numeric_confidence
                        item.update(build_event_asset_attribution(item, symbols))
                        by_event.append(item)
                    causal_recorded = _nes.record_causal_events(by_event)
                    _nes.causal_event_study()
                    # Matured archived factor responses are the sole input to
                    # the causal edge calibration artifact. Calibration apply
                    # remains false in production.
                    from packages.learning import causal_calibration as _cc
                    calibration_runtime = _cc.run_if_due()
                except Exception as causal_exc:
                    errors.append(f"causal_event_ledger:{type(causal_exc).__name__}")
                    calibration_runtime = {"status": "ERROR", "error": type(causal_exc).__name__}
            news_study_status = "OK"
            log.info("news_event_study: +%s events, causal=%s, matured=%s verdict=%s calibration=%s",
                     recorded, causal_recorded, nt.get("matured"), nt.get("global_verdict"), calibration_runtime.get("status"))
        except Exception as exc:  # defensive — worker patlamamalı
            news_study_status = f"ERROR:{type(exc).__name__}"
            errors.append(_err("news_event_study", exc))
    else:
        log.info(
            "news_event_study: skipped (artifact age < %ss; shadow-only)",
            NEWS_EVENT_STUDY_INTERVAL_SEC,
        )

    # Çıkış stop-verim backtest'i (SALT-ANALİZ). AĞIR (binlerce entry × ızgara) →
    # interval-kapılı (haftalık; durum = artifact yaşı). Sabit+trailing stop için
    # en verimli aralığı gerçek OHLCV'den ölçer; canlı çıkışa dokunmaz.
    exit_backtest_status = "ERROR"
    laps.append(("exit_backtest", time.monotonic()))
    try:
        from packages.learning import exit_backtest as _eb
        eb = _eb.run_if_due()
        exit_backtest_status = str(eb.get("status", "UNKNOWN"))
        if exit_backtest_status == "OK":
            log.info("exit_backtest: %s entries taranıp güncellendi", eb.get("entries"))
    except Exception as exc:  # defensive — worker patlamamalı
        exit_backtest_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("exit_backtest", exc))

    # Kapı karşı-olgu defteri (salt ölçüm, flag yok): karar kaydındaki her aday
    # açılsaydı karar anındaki stop/hedef planıyla ne yapardı — kapıların bedeli.
    gate_counterfactual_status = "ERROR"
    laps.append(("gate_counterfactual", time.monotonic()))
    try:
        from packages.learning import gate_counterfactual as _gcf
        gcf = _gcf.run()
        gate_counterfactual_status = str(gcf.get("status", "UNKNOWN"))
        log.info("gate_counterfactual: yeni=%s çözülen=%s bekleyen=%s",
                 gcf.get("new"), gcf.get("resolved"), gcf.get("pending"))
    except Exception as exc:  # defensive — worker patlamamalı
        gate_counterfactual_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("gate_counterfactual", exc))

    # Konsey karnesi (SALT-ANALİZ, flag YOK). Katmanlar-arası kombinasyon
    # analizi: modül yayılımları + ikili çiftler + rejim/güven kırılımları +
    # veriden-türetilen sanki-filtreler. Owner 2026-07-12 elle analizinin
    # kalıcı hâli; canlı karara dokunmaz. Veri hijyeni içerde (legacy hariç).
    council_status = "ERROR"
    laps.append(("council_scorecard", time.monotonic()))
    try:
        from packages.learning import council_scorecard as _cs
        cs_rep = _cs.run_if_due()
        council_status = str(cs_rep.get("status", "UNKNOWN"))
        if council_status == "OK":
            log.info("council_scorecard: n=%s", cs_rep.get("n"))
    except Exception as exc:  # defensive — worker patlamamalı
        council_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("council_scorecard", exc))

    # Aday bölge önericisi (SALT-ANALİZ, flag YOK).
    # Owner'ın kesişim yöntemini makro evrende (rotasyon çekirdeği + ETF + keşif
    # kısa listesi) mekanik geometriyle serer (pivot→log-çizgi→log-fib→kesişim→
    # confluence) → aday bölge listesi. Makine bölge SEÇMEZ, ADAY önerir; owner
    # süzer, kabul edileni zone_plans.yaml'a taşır. Canlı karara dokunmaz.
    zone_proposer_status = "ERROR"
    laps.append(("zone_proposer", time.monotonic()))
    try:
        from packages.learning import zone_proposer as _zpr
        zpr = _zpr.run_if_due()
        zone_proposer_status = str(zpr.get("status", "UNKNOWN"))
        if zone_proposer_status == "OK":
            log.info("zone_proposer: assets=%s with_zones=%s",
                     zpr.get("assets"), zpr.get("with_zones"))
    except Exception as exc:  # defensive — worker patlamamalı
        zone_proposer_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("zone_proposer", exc))

    # D5 — sinyal karnesi (SUBSIGNAL_SCORECARD_ENABLED, default OFF → tam no-op).
    # INTERVAL-kapılı (haftalık; durum = artifact yaşı): 8 sinyal × 4 TF ileri-
    # getiri karnesi (v2 sert cetvel) yeniden ölçülür — bar arşivi büyüdükçe
    # pencere kendiliğinden uzar. SALT-GÖZLEM: canlı skora/karara/paper'a yazmaz.
    # Import lazy — flag kapalıyken sinyal/vwap bağımlılıkları hiç yüklenmez.
    subsignal_scorecard_status = "DISABLED"
    laps.append(("subsignal_scorecard", time.monotonic()))
    try:
        from packages.learning import subsignal_scorecard
        if subsignal_scorecard.enabled():
            sc_rep = subsignal_scorecard.run_if_due()
            subsignal_scorecard_status = str(sc_rep.get("status", "UNKNOWN"))
            if subsignal_scorecard_status == "OK":
                log.info(
                    "subsignal_scorecard: timeframes=%s", sc_rep.get("timeframes")
                )
    except Exception as exc:  # defensive — worker patlamamalı
        subsignal_scorecard_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("subsignal_scorecard", exc))

    # D6 — tf_scoring_v2 GÖLGE (TF_SCORING_V2_SHADOW, default OFF → tam no-op).
    # Karne kanıtıyla (kanıt-cap ağırlık) katmanlı v2 yön skorunu CANLI barlar
    # üstünde üretir → "v2 şu an ne derdi" izole artifact. SALT-GÖZLEM: canlı
    # skora/karara/paper'a yazmaz (D7 yarışın girdisi). Lazy import — flag
    # kapalıyken skorlama bağımlılıkları yüklenmez (bayt-eşdeğer koşu).
    tf_scoring_v2_shadow_status = "DISABLED"
    laps.append(("tf_scoring_v2_shadow", time.monotonic()))
    try:
        from packages.learning import tf_scoring_shadow
        if tf_scoring_shadow.enabled():
            v2s = tf_scoring_shadow.run()
            tf_scoring_v2_shadow_status = str(v2s.get("status", "UNKNOWN"))
            if tf_scoring_v2_shadow_status == "OK":
                log.info(
                    "tf_scoring_v2_shadow: symbols_scored=%s", v2s.get("symbols_scored")
                )
    except Exception as exc:  # defensive — worker patlamamalı
        tf_scoring_v2_shadow_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("tf_scoring_v2_shadow", exc))

    # R5 — tf_scoring_v2 YARIŞ DEFTERİ (gölgeyle AYNI kapı: TF_SCORING_V2_SHADOW).
    # Gölge yönünü fiyat damgasıyla deftere yazar, ufuk dolan barları gerçekleşen
    # ileri-getiriyle çözer, yeni beyni eskiye/tabana karşı puanlar. Kriter tutarsa
    # governor'a OWNER ONAY paketi sunar — terfi OTOMATİK DEĞİL (KIRMIZI ÇİZGİ).
    # SALT-GÖZLEM: canlı skora/karara/paper'a yazmaz.
    tf_scoring_race_status = "DISABLED"
    laps.append(("tf_scoring_race", time.monotonic()))
    try:
        from packages.learning import tf_scoring_race
        if tf_scoring_shadow.enabled():
            r5 = tf_scoring_race.run()
            tf_scoring_race_status = str(r5.get("status", "UNKNOWN"))
            if tf_scoring_race_status == "OK":
                log.info(
                    "tf_scoring_race: appended=%s ledger_rows=%s resolved=%s race=%s",
                    r5.get("appended"), r5.get("ledger_rows"),
                    r5.get("resolved"), r5.get("race_status"),
                )
    except Exception as exc:  # defensive — worker patlamamalı
        tf_scoring_race_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("tf_scoring_race", exc))

    # 90 günlük paper ileri sınaması (salt-okuma kanıt; ağırlık/kapı/paper'a dokunmaz).
    forward_test_status = "ERROR"
    laps.append(("forward_test_90d", time.monotonic()))
    try:
        from packages.learning import forward_test
        forward_result = forward_test.run()
        forward_test_status = str(forward_result.get("status", "UNKNOWN"))
    except Exception as exc:  # defensive — worker patlamamalı
        forward_test_status = f"ERROR:{type(exc).__name__}"
        errors.append(_err("forward_test_90d", exc))

    if errors:
        status = "COMPLETED_WITH_ERRORS"
    elif outcomes_seen == 0:
        status = "NO_DATA"
        skipped_reason = "no_closed_outcomes"  # net NO_DATA nedeni
    else:
        status = "COMPLETED"  # skipped_reason trainer'dan (örn. below_min_total)

    # CP1 — perf bütçesi denetimi (off-tick; sistem ağırlaşmasın diye erken uyarı).
    try:
        learned_drift = _learned_drift()
    except Exception as exc:  # defensive — worker patlamamalı
        learned_drift = {}
        errors.append(_err("learned_drift", exc))
    laps.append(("_end", time.monotonic()))
    step_ms = {name: int((laps[i + 1][1] - at) * 1000) for i, (name, at) in enumerate(laps[:-1])}
    duration_ms = int((time.monotonic() - t0) * 1000)
    over_budget = duration_ms > LEARNING_BUDGET_MS
    if over_budget:
        log.warning(
            "learning run over budget: %dms > %dms (bütçe)", duration_ms, LEARNING_BUDGET_MS
        )

    run = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "skipped_reason": skipped_reason,
        "outcomes_seen": outcomes_seen,
        "proposals_generated": proposals_generated,
        "rebalance_decision": rebalance_decision,  # G3
        "guard_safety_status": guard_safety_status,  # CP3
        "activation_watchdog_status": activation_watchdog_status,  # F5-3
        "macro_backfill_status": macro_backfill_status,  # 2026-07-13 arşiv bekçisi

        "calibration_status": calibration_status,
        "tf_calibration_status": tf_calibration_status,
        "tf_weights_trusted": tf_weights_trusted,
        "tf_weight_proposal_status": tf_weight_proposal_status,
        "tf_target_status": tf_target_status,
        "tf_target_decisions": tf_target_decisions,
        "exit_forensics_status": exit_forensics_status,  # Çıkış Otopsisi (2026-07-03)
        "discovery_status": discovery_status,  # K-0b sektör rotasyonu (DISABLED=flag OFF)
        "discovery_scan_status": discovery_scan_status,  # K-1 tarayıcı
        "news_discovery_status": news_discovery_status,  # haber güdümlü keşif (2026-10-05)
        "news_forecast_status": news_forecast_status,  # haber öngörüsü (2026-10-05)
        "ideas_status": ideas_status,  # fikir panosu + YZ değerlendirmesi (2026-10-05)
        "discovery_promotion_status": discovery_promotion_status,  # K-4 terfi kriteri (DISABLED=flag OFF)
        "regime_brake_status": regime_brake_status,  # Y-1 rejim risk freni tablosu (gözlem; uygulama flag'le)
        "news_study_status": news_study_status,  # Y-6 haber olay-çalışması karnesi (SALT-GÖZLEM)
        "exit_backtest_status": exit_backtest_status,  # Çıkış stop-verim backtest (interval-kapılı; SKIP_FRESH=taze)
        "zone_proposer_status": zone_proposer_status,  # Aday bölge önericisi (makine ADAY önerir, owner süzer; SALT-ANALİZ)
        "council_status": council_status,  # Konsey karnesi (katmanlar-arası kombinasyon; SALT-ANALİZ)
        "gate_counterfactual_status": gate_counterfactual_status,  # kapı karşı-olgu defteri (salt ölçüm)
        "subsignal_scorecard_status": subsignal_scorecard_status,  # D5 sinyal karnesi (DISABLED=flag OFF)
        "tf_scoring_v2_shadow_status": tf_scoring_v2_shadow_status,  # D6 v2 gölge skoru (DISABLED=flag OFF)
        "tf_scoring_race_status": tf_scoring_race_status,  # R5 yarış defteri (DISABLED=flag OFF)
        "forward_test_90d_status": forward_test_status,  # 90 günlük paper ileri test
        "duration_ms": duration_ms,        # CP1 — perf görünürlüğü
        "over_budget": over_budget,        # CP1 — bütçe aşımı bayrağı
        "step_ms": step_ms,                # adım süreleri (ms; 26 Kasım 2026)
        "learned_drift": learned_drift,    # donmuş tablo ↔ öneri farkı (26 Kasım 2026)
        "errors": errors,
    }
    run_store.save(run)
    # O1 — heartbeat (system/health stale tespiti). Boş veri NO_DATA = "alive".
    heartbeat.record(
        WORKER_NAME,
        status=_HB_STATUS.get(status, "OK"),
        run_id=run_id,
        started_at=started_at,
        completed_at=run["completed_at"],
        last_error="; ".join(errors) if errors else None,
        learning_outcomes_seen=outcomes_seen,
        proposals_generated=proposals_generated,
        duration_ms=duration_ms,
    )
    return run


if __name__ == "__main__":
    from packages.ops.logsetup import configure_logging

    configure_logging()
    run_once()
