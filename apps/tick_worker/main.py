"""Tick worker — 30sn döngü.

Çalıştırma:
    python -m apps.tick_worker.main
veya:
    python apps/tick_worker/main.py

API ile aynı state.json dosyasını paylaşır; HTTP'ye ihtiyacı yok.
"""
from __future__ import annotations

import asyncio
import atexit
import ctypes
import logging
import os
import signal
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# httpx üzerinden API'yi çağırmak yerine paketleri doğrudan çağırıyoruz —
# böylece worker API'ye bağımlı değil.
from packages.data import snapshot_store
from packages.data.ingestion.pipeline import build_snapshot
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.decision import (
    agent_pipeline,
    conflict_gate,
    conflict_resolver_activation,
    gates,
    shadow,
    shadow_activation,
)
from packages.decision.engine import decide_matrix, matrix_view
from packages.learning import (
    calibration_audit,
    missed_opportunity,
    tf_calibration,
    tf_weight_trainer,
)
from packages.ops import heartbeat
from packages.paper import manual_queue
from packages.paper import state as paper_state
from packages.paper.lifecycle import attempt_open, flatten_all
from packages.paper.lifecycle import tick as price_tick
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

WORKER_NAME = "tick_worker"
LOCK_PATH = Path(os.environ.get("TICK_WORKER_LOCK_PATH", "data/runtime/tick_worker.lock"))
_LOCK_FD: int | None = None


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


# S1-4 — OPSİYONEL sağlayıcılar: bazı ağlardan kalıcı erişilemeyen yan
# kaynaklar (Deribit bölgesel engelli). Bunların arızası tek başına worker'ı
# DEGRADED yapmaz (alarm yorgunluğu gerçek arızayı maskeler); sebep yine
# degraded_reasons'ta listelenir, provider_status'ta görünür kalır.
OPTIONAL_PROVIDERS = frozenset({"options_deribit"})


def _degraded_providers(snap) -> tuple[list[str], list[str]]:
    """(kritik, opsiyonel) arızalı sağlayıcı adları."""
    critical: list[str] = []
    optional: list[str] = []
    for name, info in (getattr(snap, "provider_status", None) or {}).items():
        raw = info.get("status") if isinstance(info, dict) else info
        if str(raw or "").lower() in {"degraded", "down"}:
            (optional if name in OPTIONAL_PROVIDERS else critical).append(name)
    return sorted(critical), sorted(optional)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _release_single_instance() -> None:
    global _LOCK_FD
    if _LOCK_FD is not None:
        try:
            os.close(_LOCK_FD)
        except OSError:
            pass
        _LOCK_FD = None
    try:
        raw = LOCK_PATH.read_text(encoding="utf-8").strip()
        if raw.split("|", 1)[0] == str(os.getpid()):
            LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _acquire_single_instance() -> None:
    """Prevent parallel tick workers from writing divergent paper state."""
    if os.environ.get("TICK_WORKER_DISABLE_LOCK", "").strip().lower() in {"1", "true", "yes"}:
        return
    global _LOCK_FD
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            _LOCK_FD = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(_LOCK_FD, f"{os.getpid()}|{_utc_iso()}".encode())
            atexit.register(_release_single_instance)
            return
        except FileExistsError:
            try:
                raw = LOCK_PATH.read_text(encoding="utf-8").strip()
                pid = int(raw.split("|", 1)[0] or "0")
            except (OSError, ValueError):
                pid = 0
            if _pid_alive(pid):
                raise RuntimeError(f"tick_worker already running pid={pid}") from None
            try:
                LOCK_PATH.unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"stale tick_worker lock cannot be removed: {LOCK_PATH}") from exc


def _snapshot_record(snap, view: dict, risk, ps) -> dict:
    """R1 — disk snapshot store payload'u (gerçek state; sahte backtest yok)."""
    return {
        "schema_version": snapshot_store.SCHEMA_VERSION,
        "snapshot_id": snap.snapshot_id,
        "generated_at": snap.generated_at.isoformat(),
        "mode": data_provenance(snap),
        "dqs": {"score": snap.quality.score, "status": snap.quality.status},
        "provider_status": snap.provider_status or {},
        "data_snapshot": {
            "prices": [
                {
                    "symbol": q.symbol,
                    "price": q.price,
                    "verified": q.verified,
                    "status": getattr(q, "status", None),
                }
                for q in snap.prices
            ],
            "warnings": list(snap.warnings)[:8],
        },
        "decision_matrix": view,
        "risk_state": {
            "action": risk.action,
            "reason": risk.reason,
            "evidence": list(risk.evidence),
        },
        "paper_state_summary": {
            "equity_usd": round(ps.equity_usd, 2),
            "peak_equity_usd": round(ps.peak_equity_usd, 2),
            "daily_pnl_usd": round(ps.daily_pnl_usd, 2),
            "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
            # F2-1 — MTM salt-gözlem: açık pozisyonların mark-to-market toplamı.
            # RiskGate hâlâ realized equity görür; bu alanlar bant gözlemi içindir.
            "unrealized_pnl_usd": round(ps.unrealized_pnl_usd, 2),
            "mtm_equity_usd": round(ps.mtm_equity_usd, 2),
            "open_position_count": len(ps.open_positions),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "timeframe": getattr(p, "timeframe", "1d"),
                    "size_usd": round(p.size_usd, 2),
                }
                for p in ps.open_positions
            ],
        },
    }

log = logging.getLogger("tick_worker")

INTERVAL = int(os.environ.get("TICK_INTERVAL_SEC", "30"))
_STOP = asyncio.Event()


def _install_signals() -> None:
    # When embedded in another process (e.g. FastAPI lifespan), the host owns
    # signals. Set TICK_SKIP_SIGNAL_HANDLERS=1 to opt out cleanly.
    if os.environ.get("TICK_SKIP_SIGNAL_HANDLERS", "").strip() in {"1", "true", "yes"}:
        return
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _STOP.set)
        except NotImplementedError:
            pass


async def run_once() -> None:
    # O1 — her cycle heartbeat: başta RUNNING, sonda OK/DEGRADED; istisnada FAILED.
    # Worker ASLA gerçek emir üretmez; heartbeat yalnızca gözlemler.
    run_id = uuid.uuid4().hex[:12]
    started_at = _utc_iso()
    t0 = time.monotonic()
    heartbeat.record(WORKER_NAME, status="RUNNING", run_id=run_id, started_at=started_at)
    decisions_generated = 0
    paper_actions = 0
    snapshots_written = 0
    # Her tick'te taze okunur — kullanıcı runtime'da custom trade asset
    # eklerse bir sonraki cycle'da otomatik dahil olur (process restart gerekmez).
    MATRIX_SYMBOLS = asset_registry.trade_symbols()
    try:
        snap = build_snapshot()
        ps = paper_state.load()
        prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
        verified_flags = {q.symbol: q.verified for q in snap.prices}
        closed = price_tick(ps, prices)
        for cls in closed:
            log.info("close: %s %s pnl=%.2f reason=%s", cls.symbol, cls.side, cls.pnl_usd, cls.close_reason)

        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
            # S2-1 — MTM gate girdisi (flag risk_gates.mtm_equity_enabled
            # KAPALIYKEN engine bunu okumaz → davranış birebir eski).
            mtm_equity_usd=ps.mtm_equity_usd,
        )

        # G5 — halt durumunu oku/persist et; KILL_SWITCH halt → flatten,
        # yeni trade açma (risk engine halt'i KILL_SWITCH/RISK_REDUCE'a çevirir).
        halts = halt_store.sync(risk_in)
        if any(h.level == "KILL_SWITCH" for h in halts):
            for cls in flatten_all(ps, prices):
                log.info(
                    "halt flatten: %s %s pnl=%.2f reason=%s",
                    cls.symbol, cls.side, cls.pnl_usd, cls.close_reason,
                )
            risk_in = RiskInput(
                dqs_score=snap.quality.score,
                equity_usd=ps.equity_usd,
                peak_equity_usd=ps.peak_equity_usd,
                daily_pnl_usd=ps.daily_pnl_usd,
                open_position_count=len(ps.open_positions),
                mtm_equity_usd=ps.mtm_equity_usd,
            )
        if halts:
            log.warning("active halts: %s", [h.type for h in halts])

        # T2 — (symbol, timeframe) karar uzayı; fingerprint TF segmenti taşır,
        # 1w decide_matrix içinde paper_execution=false ile hold'a düşer.
        _regime, _risk, decisions = decide_matrix(
            MATRIX_SYMBOLS, snap, risk_in, open_positions=ps.open_positions
        )
        decisions_generated = len(decisions)
        now = datetime.now(UTC)

        # Faz 8 — Conflict Gate: eski sistemin önerisini yeni Conflict Resolver'ın
        # verdict'iyle, trade_profile bazlı kademeli sıkılıkla süzer. enabled=false
        # (varsayılan) ise hiçbir şey hesaplanmaz, davranış değişmez (fail-open).
        gate_cfg = conflict_gate.load_config()
        conflict_by_symbol: dict[str, dict] = {}
        if gate_cfg.enabled:
            try:
                gate_views = agent_pipeline.build_agent_matrix(MATRIX_SYMBOLS, risk_action=_risk.action)
                for gv in gate_views:
                    gv_symbol = getattr(gv, "symbol", None)
                    if gv_symbol:
                        conflict_by_symbol[gv_symbol] = shadow.evaluate_symbol(
                            gv, fingerprint=None, risk_action=_risk.action, dqs_status=snap.quality.status
                        )
            except Exception:
                log.exception("conflict gate precompute failed (tick devam ediyor, fail-open)")
                conflict_by_symbol = {}

        for d in decisions:
            if d.action in {"blocked", "hold"}:
                continue
            side = "long" if d.action == "open_long" else "short"
            # Tek rotalama noktası: session_gate (RiskGate sonrası seans kısıtı) +
            # Faz 8 Conflict Gate — sıralama/öncelik bkz. packages/decision/gates.py.
            routed = gates.apply_gates(
                d, side=side, now=now, regime=_regime,
                gate_cfg=gate_cfg, conflict_by_symbol=conflict_by_symbol,
            )
            if routed.route == "block":
                continue
            if routed.route == "manual_ready":
                manual_queue.route_to_manual_ready(
                    ps, symbol=d.symbol, timeframe=d.timeframe, side=side,
                    size_multiplier=d.size_multiplier * routed.effective_multiplier,
                    requested_price=prices.get(d.symbol),
                    reason=routed.reason,
                    fingerprint=d.fingerprint,
                    snapshot_id=snap.snapshot_id,
                )
                continue
            # P1 — açılış tek yoldan (attempt_open): duplicate/scale-in politikası +
            # fiyat denetimi + audit ortak. Seans çarpanı kısıtlayıcı + attribution.
            # ATR'yi per-TF teknik snapshot'tan çek; lifecycle TF-targets enabled
            # iken bunu compute_tf_targets'a aktarır, değilse görmezden gelir.
            tf_atr: float | None = None
            tech_by_tf = (snap.technicals_by_tf or {}).get(d.symbol) or {}
            tech = tech_by_tf.get(d.timeframe)
            if tech is not None and tech.atr is not None and tech.atr > 0:
                tf_atr = float(tech.atr)
            pos, open_decision = attempt_open(
                ps,
                symbol=d.symbol,
                side=side,
                entry_price=prices.get(d.symbol),
                size_multiplier=d.size_multiplier * routed.effective_multiplier,
                timeframe=d.timeframe,
                open_reason=d.reason,
                snapshot_id=snap.snapshot_id,
                fingerprint=d.fingerprint,
                data_verified=verified_flags.get(d.symbol, False),
                predicted_confidence=d.confidence,
                raw_confidence=d.raw_confidence,
                confidence_source=d.confidence_source,
                atr=tf_atr,
                # F1-3 — modül katkı vektörü (score×weight): dominant_module tek-modül
                # attribution'unun ham verisi; kapanışta decision_log'a taşınır.
                module_contributions={
                    m.name: m.contribution for m in d.consensus.modules
                },
                # Tekrar-giriş kilidi YALNIZ otomatik sinyal açılışına (owner manuel
                # açılış / manual_ready onayı muaf). Flag KAPALIYKEN gözlem, açılış
                # bayt-aynı (shadow-first).
                apply_reentry_guard=True,
                **routed.session_attribution,
            )
            if pos is not None:
                paper_actions += 1
                log.info(
                    "open: %s %s %s @ %.4f size=%.0f valid_until=%s",
                    pos.symbol, pos.timeframe, pos.side, pos.entry_price, pos.size_usd,
                    pos.valid_until,
                )
                # Observe-only: kalibrasyon sıçramasını + faktörleri ledger'a yaz
                # (karar/sizing değişmez; best-effort, tick'i düşürmez).
                calibration_audit.record_open(
                    d, pos, regime=getattr(_regime, "label", None)
                )
            # Tekrar-giriş kilidi kanıtı (shadow VEYA canlı): guard kilit hesapladıysa
            # logla — owner kapalıyken frekansı görüp açar (shadow-first kanıt yolu).
            rg = (open_decision or {}).get("reentry_guard")
            if rg and rg.get("locked"):
                log.info(
                    "reentry_guard %s: %s %s %s (armed_by=%s, %s) — %s",
                    "BLOK" if rg.get("active") else "gölge",
                    d.symbol, d.timeframe, side, rg.get("armed_by"),
                    rg.get("reason"), "açılış engellendi" if rg.get("active") else "açılışa izin (flag kapalı)",
                )

        paper_state.save(ps)

        # Step 9 — controlled activation (OBSERVATION mode). Run the NEW agent
        # pipeline in shadow and persist a comparison vs. the live engine. Runs
        # AFTER paper is saved and never receives paper state — with
        # affect_decision:false it cannot move paper. Best-effort: never breaks tick.
        try:
            shadow_cfg = shadow.load_config()
            if shadow_cfg.enabled:
                # tf_weights trust verdict (read-only; worker owns paper state `ps`).
                # Surfaced in the record so applying PRIOR weights stays data-driven.
                try:
                    cal_report = tf_calibration.calibration_report(state=ps)
                    cal_summary = shadow.calibration_summary(cal_report)
                except Exception:
                    cal_report = {}
                    cal_summary = {}
                # Trust-gated live tf_weights application: only when calibration trusts.
                try:
                    live_tf_weights = tf_weight_trainer.resolve_live_tf_weights(cal_report)
                except Exception:
                    live_tf_weights = None
                shadow_record = shadow.observe(
                    MATRIX_SYMBOLS,
                    snapshot_id=snap.snapshot_id,
                    risk_action=_risk.action,
                    live_decisions=decisions,
                    cfg=shadow_cfg,
                    calibration=cal_summary,
                    tf_weights=live_tf_weights,
                    dqs_status=snap.quality.status,
                )
                shadow.record(shadow_record)
                # Faz 2 — Missed Opportunity: açılmayan valid setup'ları (shadow
                # CANDIDATE_OPEN ama canlı açmadı) TTL boyunca izle; paper'a ASLA
                # dokunmaz, ayrı best-effort → gözlem tick'i kesmez. enabled=false
                # iken inert (boş özet). Faz 4 conflict-gate kararına veri toplar.
                try:
                    mo = missed_opportunity.scan_and_track(shadow_record)
                    if mo.get("tracked_new") or mo.get("resolved"):
                        log.info(
                            "missed_opp: +%d izleme, %d çözüldü, %d aktif",
                            mo["tracked_new"], mo["resolved"], mo["active"],
                        )
                except Exception:
                    log.exception("missed_opp scan failed (tick devam ediyor)")
                if shadow.affects_paper(shadow_cfg):
                    # Phase B — controlled activation: route shadow entries to
                    # manual_ready ONLY (never auto-open; RiskGate re-runs at owner
                    # approval). Inert under the shipped affect_decision:false config.
                    queued = shadow_activation.activate(
                        ps,
                        MATRIX_SYMBOLS,
                        risk_action=_risk.action,
                        prices=prices,
                        snapshot_id=snap.snapshot_id,
                        cfg=shadow_cfg,
                        tf_weights=live_tf_weights,
                    )
                    if queued:
                        paper_state.save(ps)
                        log.info(
                            "shadow activation: %d entry → manual_ready", len(queued)
                        )
        except Exception:
            log.exception("shadow observe failed (tick devam ediyor)")

        # Faz 7 — Conflict Resolver'ın kontrollü aktivasyonu. `shadow.affect_decision`'dan
        # TAMAMEN BAĞIMSIZ ayrı bir kapı (conflict_resolver_activation.enabled).
        # Varsayılan kapalı: cfg.enabled=false olduğu sürece activate() her zaman
        # boş liste döner — manual_ready'e hiçbir şey eklenmez, davranış değişmez.
        try:
            cr_cfg = conflict_resolver_activation.load_config()
            if cr_cfg.enabled:
                cr_queued = conflict_resolver_activation.activate(
                    ps,
                    MATRIX_SYMBOLS,
                    risk_action=_risk.action,
                    dqs_status=snap.quality.status,
                    prices=prices,
                    snapshot_id=snap.snapshot_id,
                    cfg=cr_cfg,
                )
                if cr_queued:
                    paper_state.save(ps)
                    log.info(
                        "conflict resolver activation: %d entry → manual_ready", len(cr_queued)
                    )
        except Exception:
            log.exception("conflict resolver activation failed (tick devam ediyor)")

        # R1 — kararı disk snapshot store'a kaydet (replay temeli). Store yazımı
        # ASLA tick'i patlatmaz; başarısızsa loglanır ve döngü devam eder.
        try:
            view = matrix_view(_regime, _risk, decisions, snap, MATRIX_SYMBOLS)
            view["mode"] = data_provenance(snap)
            sid = snapshot_store.record(_snapshot_record(snap, view, _risk, ps))
            if sid:
                snapshots_written = 1
                log.info("snapshot stored: %s (count=%d)", sid, snapshot_store.count())
        except Exception:
            log.exception("snapshot store record failed (tick devam ediyor)")

        # DEGRADED: veri/sağlayıcı bozuk ya da aktif halt var (yine de cycle tamam).
        # S1-4: opsiyonel sağlayıcı arızası (options_deribit) tek başına DEGRADED
        # YAPMAZ; sebepler degraded_reasons'ta her durumda görünür.
        crit_providers, opt_providers = _degraded_providers(snap)
        reasons: list[str] = []
        if str(snap.quality.status) in {"BLOCKED", "DEGRADED"}:
            reasons.append(f"dqs:{snap.quality.status}")
        reasons.extend(f"halt:{h.type}" for h in halts)
        reasons.extend(f"provider:{n}" for n in crit_providers)
        reasons.extend(f"provider_optional:{n}" for n in opt_providers)
        degraded = (
            str(snap.quality.status) in {"BLOCKED", "DEGRADED"}
            or bool(halts)
            or bool(crit_providers)
        )
        heartbeat.record(
            WORKER_NAME,
            status="DEGRADED" if degraded else "OK",
            run_id=run_id,
            started_at=started_at,
            completed_at=_utc_iso(),
            snapshots_written=snapshots_written,
            decisions_generated=decisions_generated,
            paper_actions=paper_actions,
            duration_ms=int((time.monotonic() - t0) * 1000),
            # F2-1 — MTM salt-gözlem (RiskGate girdisi değil; bkz. _snapshot_record).
            unrealized_pnl_usd=round(ps.unrealized_pnl_usd, 2),
            mtm_equity_usd=round(ps.mtm_equity_usd, 2),
            degraded_reasons=reasons,
        )
        # SSE: cockpit'in canlı nabzı — UI bu event'i alınca brief/decision/
        # paper cache'lerini invalidate eder.
        try:
            from packages.events import bus as _bus

            _bus.publish(
                "tick.complete",
                {
                    "status": "degraded" if degraded else "ok",
                    "decisions": decisions_generated,
                    "paper_actions": paper_actions,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                },
            )
        except Exception:
            log.debug("event bus publish failed", exc_info=True)
    except Exception as exc:  # tick loop'u öldürmez — FAILED heartbeat yaz, devam et
        heartbeat.record(
            WORKER_NAME,
            status="FAILED",
            run_id=run_id,
            started_at=started_at,
            completed_at=_utc_iso(),
            last_error=repr(exc),
            snapshots_written=snapshots_written,
            decisions_generated=decisions_generated,
            paper_actions=paper_actions,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        log.exception("tick run_once failed: %s", exc)


async def run() -> None:
    _install_signals()
    log.info("tick_worker started, interval=%ds", INTERVAL)
    while not _STOP.is_set():
        try:
            await run_once()
        except Exception as exc:
            log.exception("tick failed: %s", exc)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=INTERVAL)
        except TimeoutError:
            pass
    log.info("tick_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _acquire_single_instance()
    try:
        asyncio.run(run())
    finally:
        _release_single_instance()
