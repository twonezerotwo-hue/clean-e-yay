"""DecisionEngine — consensus + risk + learning'i birleştirir.

G6 — Confidence calibration:
- Ham confidence (`|score-50|/50`) Platt scaling ile kalibre edilir.
- "insufficient" damgası TradeDecision'a yansır.

G3 — Mistake memory gate:
- Consensus eşiği aşıldıktan sonra mistake memory `evaluate(fingerprint)`
  çağrılır. AVOID→hold, WARNING→size küçült. BOOST yalnızca pozitif damga;
  size_factor ≤1.0'a clamp'lenir → **asla boyut ARTIRMAZ** (no-AI-boost).
- NEUTRAL/insufficient → no_adjustment (size_factor=1.0).

G4 — Correlation-aware sizing:
- Mistake gate'ten sonra `cluster_exposure(open_positions, aday)` çağrılır.
  Aynı yönlü |rho| ≥ 0.7 cluster toplamı `max_cluster_pct`'yi aştıysa →
  hold; yarısını aştıysa size×0.5. **Sadece küçültür, asla artırmaz.**
  Veri yetersizse neutral fallback (adjustment yok).

**Hard kural:** mistake memory, calibration ve correlation sizing
**RiskGate'i bypass ETMEZ**. KILL_SWITCH→blocked;
RISK_REDUCE/NO_POSITION_INCREASE→hold.
DQS < 55 zaten risk engine'inde KILL_SWITCH üretir → BLOCKED state'te trade
yok (calibration BOOST veya mistake BOOST yüksek olsa bile).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.providers import technical as tech_provider
from packages.data.registry import guard_overrides
from packages.data.registry.loader import load_thresholds
from packages.data.types import TIMEFRAMES
from packages.decision import correlation_veto, learning_advisor, sizing_layers
from packages.learning import empirical_pwin, meta_gate, mistake_memory, regime_risk_brake
from packages.learning.calibration_store import (
    apply_inflation_guardrail,
    predict_calibrated_tf,
    raw_confidence_from_score,
)
from packages.learning.fingerprint import make as make_fingerprint
from packages.learning.mistake_memory import MistakeVerdict
from packages.regime.classifier import RegimeOutput, classify
from packages.risk import (
    catalyst_risk,
    correlation,
    derivatives_risk,
    event_risk,
    options_risk,
    volatility_risk,
)
from packages.risk.engine import RiskDecision, RiskInput
from packages.risk.engine import evaluate as evaluate_risk

Action = Literal["open_long", "open_short", "hold", "blocked"]


@dataclass
class TradeDecision:
    symbol: str
    action: Action
    confidence: float           # calibrated p(win) ∈ [0,1]
    size_multiplier: float      # 0–1.5
    consensus: ConsensusResult
    risk: RiskDecision
    reason: str
    raw_confidence: float = 0.0
    confidence_source: str = "identity"
    fingerprint: str | None = None
    mistake_verdict: dict = field(default_factory=dict)
    cluster_report: dict = field(default_factory=dict)
    # Açık-kitap self-conflict guard (shadow-first). Aday aynı sembolde zaten açık
    # ZIT yöne giriyorsa burada işaretlenir; book_audit.self_conflict_guard.enabled
    # iken bloklanır, kapalıyken yalnız gözlem (active=False). Boş = çakışma yok.
    self_conflict_report: dict = field(default_factory=dict)
    # Concentration guard (shadow-first). Aday aynı sembolde zaten açık AYNI yöne yeni
    # leg ekliyorsa (tek sinyalin TF'lere kopyası) burada işaretlenir; book_audit.
    # concentration_guard.enabled iken yığın sınırı aşılırsa bloklanır, kapalıyken
    # yalnız gözlem (active=False). Boş = aynı-yön açık leg yok.
    concentration_report: dict = field(default_factory=dict)
    # v2.7 D2 — kripto türev riski (yalnızca kısıtlayıcı; crypto sembolleri).
    derivatives_report: dict = field(default_factory=dict)
    # v2.7 D4 — realized volatility riski (yalnızca kısıtlayıcı; per (symbol, tf)).
    volatility_report: dict = field(default_factory=dict)
    # v2.7 D5 — haber catalyst riski (yalnızca kısıtlayıcı; verified + taze).
    catalyst_report: dict = field(default_factory=dict)
    # v2.7 D3 — options IV/skew/term riski (yalnızca kısıtlayıcı; BTC/ETH).
    options_report: dict = field(default_factory=dict)
    timeframe: str = "1d"  # T2 — (symbol, timeframe) karar uzayı aktif
    # T2 additive — candidate (consensus niyeti) vs final (gate'ler sonrası)
    # ayrımı görünür olsun; blocked_by hangi kapının kararı kestiğini söyler.
    candidate_action: Action = "hold"
    blocked_by: list[str] = field(default_factory=list)
    actionable: bool = False
    # F5 — beklenen değer (R-katı): p(win)×RR − (1−p)×1 − maliyet. Her zaman hesaplanır
    # (gözlem); ev_gate.enabled iken < min_ev olan trade bloklanır. None = hesaplanmadı.
    expected_value: float | None = None
    # F4-2 — ampirik p(win) gözlemi: (tf|rejim → tf) gerçekleşmiş isabet oranı.
    # `empirical_pwin.enabled` KAPALIYKEN yalnız gözlem (EV/Kelly cal_conf ile);
    # açıkken EV/Kelly bu p ile hesaplanır. None = yeterli ampirik kanıt yok.
    p_win_empirical: float | None = None
    expected_value_empirical: float | None = None
    # Y-1 — rejim risk freni (shadow-first). Rejim kanıtı çift-negatifse fren
    # bilgisi burada taşınır; `regime_risk_brake.enabled` iken boyut kısılır,
    # kapalıyken yalnız gözlem (applied=False). Boş = frenlenecek kanıt yok.
    regime_brake_report: dict = field(default_factory=dict)
    # Y-5 — meta-label kapısı (SALT-GÖLGE): açılış adayına GİR/GİRME hükmü.
    # Karara/boyuta ASLA uygulanmaz (uygulama flag'i yok; aktivasyon scorecard
    # seçicilik kanıtı + owner kararıyla AYRI dilim). Boş = aday değil/hata.
    meta_gate_report: dict = field(default_factory=dict)
    # Karar-kanıt tüketicisi (2026-07-09): tüm learning'lerin TEK birleşik fikri
    # (CONFIRM/CAUTION/AVOID + gerekçe). VARSAYILAN GÖLGE — boyutu değiştirmez;
    # canlı etki yalnız LEARNING_ADVISOR_APPLY=1 (owner). Boş = aday değil/hata.
    learning_advice: dict = field(default_factory=dict)
    # Boyut katmanları (P1, 2026-07-10): inanç-boyu + oynaklık-paritesi. VARSAYILAN
    # GÖLGE (her katman config-flag default false → applied_factor 1.0, boyut bayt-
    # aynı); açık katman YALNIZ KISAR (no-boost). Boş = aday değil/hesaplanamadı.
    sizing_layers_report: dict = field(default_factory=dict)
    # D — dinamik korelasyon vetosu (P1, 2026-07-10): aday sinyalin en güçlü akrabası
    # ilişkiyi çürütüyorsa engel. VARSAYILAN GÖLGE (correlation_veto.enabled=false →
    # rapor dolu, karar değişmez); açıkken YALNIZ ENGELLER. Boş = güçlü akraba yok.
    correlation_veto_report: dict = field(default_factory=dict)
    # P3 parça-2 — quantum boyut-kısma (2026-07-10): quantum katkısı yüksekken (INVERSE
    # kanıtı) o işlemde boyut kısılır. VARSAYILAN GÖLGE (quantum_dampen.enabled=false →
    # rapor dolu, boyut bayt-aynı); açıkken YALNIZ KISAR. Boş = quantum katkısı yok.
    quantum_dampen_report: dict = field(default_factory=dict)


def _timeframe_policy(timeframe: str) -> dict:
    """thresholds.timeframe_risk — yalnızca risk azaltıcı okunur.

    risk_multiplier 1.0'a clamp'lenir (hiçbir TF boyut ARTIRAMAZ);
    paper_execution=False (1w) doğrudan paper açılışını kapatır.
    """
    cfg = load_thresholds().get("timeframe_risk") or {}
    pol = cfg.get(timeframe) or {}
    return {
        "role": str(pol.get("role", "")),
        "risk_multiplier": min(1.0, float(pol.get("risk_multiplier", 1.0))),
        "paper_execution": bool(pol.get("paper_execution", True)),
        "time_stop_hours": int(pol.get("time_stop_hours", 0)),
    }


def time_stop_hours(timeframe: str) -> int:
    """Paper katmanı için TF time-stop süresi (saat; 0 → time-stop yok)."""
    return _timeframe_policy(timeframe)["time_stop_hours"]


def _candidate_from_score(score: float, th: dict) -> tuple[Action, float]:
    """Consensus skorundan ham niyet (candidate) + taban boyut."""
    if score >= th["strong_bullish_min"]:
        return "open_long", 1.5
    if score >= th["bullish_min"]:
        return "open_long", 1.0
    if score <= th["strong_bearish_max"]:
        return "open_short", 1.5
    if score <= th["bearish_max"]:
        return "open_short", 1.0
    return "hold", 0.0


def _regime_multiplier(label: str) -> float:
    return {"OFFENSIVE": 1.0, "NEUTRAL": 0.8, "DEFENSIVE": 0.5, "CRISIS": 0.35}.get(label, 0.5)


def _verdict_to_dict(v: MistakeVerdict) -> dict:
    return {
        "action": v.action,
        "reason": v.reason,
        "size_factor": v.size_factor,
        "evidence": list(v.evidence),
        "fingerprint": v.fingerprint,
        "record": asdict(v.record) if v.record else None,
    }


def _ev_gate_cfg() -> dict:
    """F5 EV kapısı config (monkeypatch-edilebilir seam — test izolasyonu)."""
    return load_thresholds().get("ev_gate") or {}


def _kelly_cfg() -> dict:
    """F5 Kelly sizing config (monkeypatch-edilebilir seam — test izolasyonu)."""
    return load_thresholds().get("kelly_sizing") or {}


def _self_conflict_cfg() -> dict:
    """Açık-kitap self-conflict guard config (monkeypatch-seam). Aynı sembolde
    zaten açık ZIT yöne yeni aday girişini engeller. enabled default False
    (shadow-first); kapalıyken yalnız gözlem işaretlenir, davranış değişmez.

    CP3 — yön güvenlik kasası: guard_safety bu guard'ı canlıda kötü bulup
    kill-override yazdıysa enabled zorla False'a çekilir (config'e dokunmadan).
    Override yokken çıktı birebir bugünkü (bkz. guard_overrides)."""
    cfg = (load_thresholds().get("book_audit") or {}).get("self_conflict_guard") or {}
    if cfg.get("enabled") and guard_overrides.is_disabled("self_conflict"):
        return {**cfg, "enabled": False}
    return cfg


def _concentration_cfg() -> dict:
    """Aynı-sembol aynı-yön yığın (concentration) guard config (monkeypatch-seam).
    Aday aynı sembolde zaten açık AYNI yöne yeni leg ekliyorsa (DODO 1h+4h gibi tek
    sinyalin TF'lere kopyalanması → riski 2x) yığını sınırlar. enabled default False
    (shadow-first); kapalıyken yalnız gözlem işaretlenir, davranış değişmez.

    CP3 — yön güvenlik kasası: guard_safety bu guard'ı canlıda kötü bulup kill-override
    yazdıysa enabled zorla False'a çekilir (config'e dokunmadan). Override yokken çıktı
    birebir bugünkü (bkz. guard_overrides)."""
    cfg = (load_thresholds().get("book_audit") or {}).get("concentration_guard") or {}
    if cfg.get("enabled") and guard_overrides.is_disabled("concentration"):
        return {**cfg, "enabled": False}
    return cfg


def _sizing_layers_cfg() -> dict:
    """Boyut katmanları (inanç-boyu + oynaklık-paritesi) config (monkeypatch-seam).
    İki alt-katman ayrı `enabled` (default False → shadow, boyut bayt-aynı). Yalnız
    KISAR (no-boost). Yoksa boş dict → evaluate güvenli 1.0 döner."""
    return load_thresholds().get("sizing_layers") or {}


def _correlation_veto_cfg() -> dict:
    """D — dinamik korelasyon vetosu config (monkeypatch-seam). enabled default False
    (shadow-first: rapor her kararda hesaplanır, davranış değişmez). Yalnız ENGELLER."""
    return load_thresholds().get("correlation_veto") or {}


def _quantum_dampen_cfg() -> dict:
    """P3 parça-2 — quantum boyut-kısma config (monkeypatch-seam). enabled default
    False (shadow: rapor her kararda, boyut bayt-aynı). Yalnız KISAR (no-boost)."""
    return load_thresholds().get("quantum_dampen") or {}


def _recent_edge(lookback: int) -> float | None:
    """P3 fren — son `lookback` kapanan işlemin ort R'si (sistemin güncel performansı).
    <10 örnek → None (yetersiz kanıt, fren yok — uydurma yok). Saf/defansif."""
    try:
        from packages.learning import outcomes as om
        outs = om.outcomes_from_state()
    except Exception:
        return None
    rs = [float(o.r_multiple) for o in outs[-lookback:] if o.r_multiple is not None]
    if len(rs) < 10:
        return None
    return sum(rs) / len(rs)


def _veto_universe() -> list[str]:
    """Korelasyon vetosunun akraba havuzu = sistemin rotasyon sembol evreni."""
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
    return sorted(set(ROTATION_SYMBOLS.values()))


def _concentration_report(
    symbol: str, cand_side: str, open_positions, equity_usd: float, cfg: dict
) -> dict:
    """Aday aynı-sembol aynı-yön açık leg'leri değerlendir (shadow — her zaman hesaplanır).

    Boş dict = aynı-yön açık leg yok (yığın riski yok). Aksi halde yığın raporu:
    leg sayısı ≥ max_same_dir_legs VEYA exposure/equity ≥ max_symbol_pct → breach.
    `active` yalnız enabled iken True; blok kararı çağırana bırakılır."""
    legs = [
        p for p in (open_positions or [])
        if p.symbol == symbol and p.side == cand_side
    ]
    if not legs:
        return {}
    max_legs = int(cfg.get("max_same_dir_legs", 1))
    max_pct = float(cfg.get("max_symbol_pct", 0.05))
    exposure_usd = sum(float(p.size_usd) for p in legs)
    exposure_pct = round(exposure_usd / equity_usd, 4) if equity_usd > 0 else 0.0
    breach_count = len(legs) >= max_legs
    breach_pct = max_pct > 0 and exposure_pct >= max_pct
    return {
        "active": bool(cfg.get("enabled", False)),
        "symbol": symbol,
        "candidate_side": cand_side,
        "open_same_dir_count": len(legs),
        "open_same_dir_usd": round(exposure_usd, 2),
        "exposure_pct": exposure_pct,
        "max_same_dir_legs": max_legs,
        "max_symbol_pct": max_pct,
        "breach": bool(breach_count or breach_pct),
        "breach_reason": "leg_count" if breach_count else ("exposure_pct" if breach_pct else None),
        "timeframes": sorted({p.timeframe for p in legs if getattr(p, "timeframe", None)}),
    }


def _tf_rr(timeframe: str) -> float:
    """timeframe_targets'tan o TF'in hedef ödül/risk (RR) oranı (yoksa 2.0)."""
    cfg = load_thresholds().get("timeframe_targets") or {}
    tf = cfg.get(timeframe) or {}
    try:
        return float(tf.get("rr", 2.0))
    except (TypeError, ValueError):
        return 2.0


def _expected_value(p_win: float, rr: float, cost_r: float) -> float:
    """Beklenen değer (R-katı): kazanırsan +RR, kaybedersen −1; maliyet düşülür."""
    return p_win * rr - (1.0 - p_win) * 1.0 - cost_r


def _expected_value_payoff(
    p_win: float, avg_win_r: float, avg_loss_r: float, cost_r: float
) -> float:
    """F5-3 — ödül-ağırlıklı beklenen değer (R-katı).

    Sabit hedef-RR (kazanç=+RR, kayıp=−1) varsayımı yerine GERÇEKLEŞEN ortalama
    kazanç-R ve kayıp-R kullanır: EV = p×avg_win_r − (1−p)×avg_loss_r − cost_r.
    Trailing/time-stop kazancı hedeften erken kesince (avg_win_r < hedef RR) veya
    kayıplar 1R'yi aşınca (avg_loss_r > 1) bu, sabit-RR EV'sinin gizlediği negatif
    edge'i açığa çıkarır. Yalnızca KISITLAYICI kapı girdisi — RiskGate'i bypass etmez."""
    return p_win * avg_win_r - (1.0 - p_win) * avg_loss_r - cost_r


def _kelly_fraction(p_win: float, rr: float) -> float:
    """Tam Kelly oranı f* = (p×RR − (1−p)) / RR (edge/odds); negatif → 0."""
    if rr <= 0:
        return 0.0
    return max(0.0, (p_win * rr - (1.0 - p_win)) / rr)


def decide_for_symbol(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    risk: RiskDecision,
    mistakes: list | None = None,
    open_positions: list | None = None,
    equity_usd: float = 0.0,
    corr_entries: list | None = None,
    timeframe: str = "1d",
    recent_edge: float | None = None,
) -> TradeDecision:
    th = load_thresholds()["consensus"]
    cons = build_consensus(symbol, snap, regime, timeframe)
    pol = _timeframe_policy(timeframe)

    raw_conf = raw_confidence_from_score(cons.score)
    # F4-1 — TF-duyarlı Platt: flag (calibration.tf_platt) KAPALIYKEN global
    # fit birebir; açıkken o TF'in fit'i (yoksa global fallback, "fitted_tf").
    cal_conf, conf_source = predict_calibrated_tf(raw_conf, timeframe)
    # Owner-flag (default KAPALI): zayıf ham sinyalin aşırı kalibrasyon şişmesini
    # kıs. Kapalıyken passthrough — mevcut davranış birebir korunur.
    cal_conf, conf_source = apply_inflation_guardrail(raw_conf, cal_conf, conf_source)

    # Candidate = consensus'un ham niyeti (gate'lerden önce) — dashboard
    # candidate vs final ayrımını bununla gösterir.
    candidate, base_size = _candidate_from_score(cons.score, th)

    # Fingerprint hesabı (mistake memory için her zaman üret — debugging).
    # T2: gerçek timeframe segmenti taşır → 15m hatası 1d'yi cezalandırmaz.
    fp = make_fingerprint(
        symbol=symbol,
        regime=regime.label,
        direction=cons.direction,
        score=cons.score,
        confluence=cons.confluence_aligned,
        dominant_module=cons.dominant_module or "?",
        timeframe=timeframe,
    )

    # ----- Risk hard gate'leri ÖNCE (timeframe dahil hiçbir katman bypass etmez) -----
    if risk.action == "KILL_SWITCH":
        return TradeDecision(
            symbol=symbol,
            action="blocked",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=[f"risk_gate:{risk.action}"],
        )
    if risk.action in {"NO_POSITION_INCREASE", "RISK_REDUCE"}:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=[f"risk_gate:{risk.action}"],
        )

    # ----- DATA_POLICY: stale OHLCV sert blok (owner-flag; varsayılan KAPALI) -----
    # "Eski veriyle trade açma" kuralı. Flag kapalıyken bu blok HİÇ çalışmaz →
    # mevcut davranış (consensus dampening, bkz. _degraded_direction_score) birebir
    # korunur. Açıkken: karar timeframe'inin son barı TF stale eşiğini aşmışsa
    # AÇILIŞ bloklanır. RiskGate'ten sonra, veri-geçerliliği önceliğiyle çalışır;
    # asla RiskGate'i bypass etmez (bu noktaya yalnızca risk açıkken gelinir).
    _dp = load_thresholds().get("data_policy") or {}
    if _dp.get("block_stale_ohlcv_for_trade", False):
        _t = (
            snap.technicals_by_tf.get(symbol, {}).get(timeframe)
            if snap.technicals_by_tf
            else None
        )
        _age = tech_provider.staleness_age_sec(_t) if _t is not None else None
        if _age is not None:
            # FAZ-2 (2026-07-16) kapalı-piyasa/stale AYRIMI: piyasası kapalı
            # sembolde taze bar OLAMAZ (hafta sonu/tatil) — bu veri hatası değil.
            # Blok SÜRER (bayat fiyatla açılış yine yapılmaz) ama etiket
            # dürüstleşir: izleme/karne bunu stale-veri alarmı saymaz
            # (pazartesi 16-blok bulgusunun kökü). Guard pipeline'dakiyle aynı;
            # kripto (continuous) her zaman açık, eşlenmemiş sembol muaf değil.
            _closed = False
            try:
                from datetime import UTC as _UTC
                from datetime import datetime as _dt

                from packages import market_sessions as _ms

                _ctx = _ms.asset_context(symbol, _dt.now(_UTC))
                _closed = bool(_ctx.relevant_markets) and not _ctx.any_relevant_market_open
            except Exception:
                _closed = False
            if _closed:
                _reason = (
                    f"DATA_POLICY: piyasa kapalı ({timeframe}, {int(_age)}s) — "
                    "yeni bar yok (veri hatası değil); bayat fiyatla açılış yine yapılmaz"
                )
                _tag = f"market_closed:{timeframe}:{int(_age)}s"
            else:
                _reason = f"DATA_POLICY: stale OHLCV ({timeframe}, {int(_age)}s) — eski veriyle açılmaz"
                _tag = f"stale_ohlcv:{timeframe}:{int(_age)}s"
            return TradeDecision(
                symbol=symbol,
                action="blocked",
                confidence=0.0,
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=_reason,
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=[_tag],
            )

    # ----- Consensus eşikleri -----
    action: Action = candidate
    size = base_size
    if action == "hold":
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason="Consensus eşiği aşılmadı",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
        )

    # ----- Minimum güven tabanı: skor eşiği geçse de kalibre p(win) düşükse açma -----
    # (Nötr/düşük-güvenli sinyallerle pozisyon açılmasını engeller. RiskGate'i
    #  bypass etmez; yalnızca ek kısıt. Owner config'ten ayarlanır.)
    min_open_conf = float(th.get("min_open_confidence", 0.0))
    if cal_conf < min_open_conf:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Düşük güven: p(win) %{cal_conf * 100:.0f} < taban %{min_open_conf * 100:.0f}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["confidence_floor"],
        )

    # ----- F5: EV (beklenen değer) kapısı — olasılık + ödül/risk BİRLİKTE pozitif
    #  değilse açma. EV her zaman hesaplanır (gözlem); ev_gate.enabled iken kısıtlar.
    #  RiskGate'i bypass etmez; yalnızca ek ekonomik filtre. (Owner config'ten.) -----
    # F4-2 — ampirik p(win): (tf|rejim) gerçekleşmiş isabet oranı her zaman
    # GÖZLENİR; `empirical_pwin.enabled` açık VE hücre yeterli örnekliyse EV +
    # Kelly bu p ile hesaplanır (skor-türevi güven yerine ölçülmüş isabet).
    # Kapalıyken / kanıt yokken cal_conf (bayt-aynı — sahte p uydurulmaz).
    rr = _tf_rr(timeframe)
    ev_cfg = _ev_gate_cfg()
    cost_r = float(ev_cfg.get("cost_r", 0.1))
    emp = empirical_pwin.lookup(timeframe, regime.label)
    p_for_ev = emp.p_win if (emp is not None and empirical_pwin.enabled()) else cal_conf
    # F5-3 — ödül-ağırlıklı EV. Flag OFF (default) → sabit-RR formülü birebir
    # (bayt-aynı). ON + yeterli örnekli hücrede GERÇEKLEŞEN kazanç-R/kayıp-R
    # varsa: EV = p_emp×avg_win_r − (1−p_emp)×avg_loss_r − cost_r (kazanma
    # olasılığı DA ampirik — şişik kalibre güven değil). R verisi yoksa dürüstçe
    # sabit-RR'ye düşer (sahte payoff uydurulmaz).
    # F5-3 guard — payoff yolu için MİN R-örneği: avg_win_r/avg_loss_r'nin
    # istatistiksel anlamı olsun (avuç dolusu gerçekleşen R koca bir timeframe'i
    # kapatmasın). Her yönde win_r_n/loss_r_n ≥ min_r_samples değilse dürüstçe
    # sabit-RR'ye düşer. min_r_samples 0 → guard kapalı (yalnız None kontrolü).
    min_r = int(ev_cfg.get("min_r_samples", 8))
    payoff_ready = (
        bool(ev_cfg.get("payoff_weighted", False))
        and emp is not None
        and emp.avg_win_r is not None
        and emp.avg_loss_r is not None
        and emp.win_r_n >= min_r
        and emp.loss_r_n >= min_r
    )
    if payoff_ready:
        expected_value = _expected_value_payoff(
            emp.p_win, emp.avg_win_r, emp.avg_loss_r, cost_r
        )
        ev_reason = (
            f"Negatif EV: {expected_value:.2f}R (p={emp.p_win:.2f}, "
            f"+{emp.avg_win_r:.2f}R/−{emp.avg_loss_r:.2f}R gerçekleşen)"
        )
    else:
        expected_value = _expected_value(p_for_ev, rr, cost_r)
        ev_reason = f"Negatif EV: {expected_value:.2f}R (p={p_for_ev:.2f}, RR={rr})"
    p_win_empirical = None if emp is None else round(emp.p_win, 4)
    expected_value_empirical = (
        None if emp is None else round(_expected_value(emp.p_win, rr, cost_r), 4)
    )
    if ev_cfg.get("enabled", False) and expected_value < float(ev_cfg.get("min_ev", 0.0)):
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=ev_reason,
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["ev_gate"],
            expected_value=round(expected_value, 4),
            p_win_empirical=p_win_empirical,
            expected_value_empirical=expected_value_empirical,
        )

    # Confluence yoksa boyut yarıya iner
    if not cons.confluence_aligned:
        size *= 0.5
    size *= _regime_multiplier(regime.label)

    # ----- G3: Mistake memory gate (RiskGate'i ASLA bypass etmez) -----
    verdict = mistake_memory.evaluate(fp, mistakes)
    if verdict.action == "AVOID":
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"mistake_memory: {verdict.reason}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["mistake_memory:AVOID"],
        )

    # No-AI-boost invariant: learning/mistake-memory may only REDUCE size. Clamp the
    # factor to ≤ 1.0 so a BOOST verdict can never increase the deterministic base.
    size *= min(1.0, verdict.size_factor)
    size = max(0.0, min(1.5, size))

    # ----- Açık-kitap self-conflict guard (shadow-first) -----
    # Aday aynı sembolde zaten açık ZIT yöne giriyorsa (BRENT short varken long)
    # bu kendine-karşı pozisyondur — biri kesin yanlış, ikisi birbirini hedge eder.
    # correlation.cluster_exposure bunu "hedge" sayıp İZİN VERİYOR; bu guard kapatır.
    # Shadow-her-zaman-hesaplanır; yalnız enabled iken bloklar (mimari kural: yön/
    # yapı katmanı öğrenme otomasyonunca izlenmediği için flag-default-OFF + ölç).
    cand_side = "long" if action == "open_long" else "short"
    opposite_side = "short" if cand_side == "long" else "long"
    conflict_legs = [
        p for p in (open_positions or [])
        if p.symbol == symbol and p.side == opposite_side
    ]
    if conflict_legs:
        sc_enabled = bool(_self_conflict_cfg().get("enabled", False))
        self_conflict_report = {
            "active": sc_enabled,
            "symbol": symbol,
            "candidate_side": cand_side,
            "open_opposite_side": opposite_side,
            "open_opposite_count": len(conflict_legs),
            "open_opposite_usd": round(sum(float(p.size_usd) for p in conflict_legs), 2),
        }
        if sc_enabled:
            return TradeDecision(
                symbol=symbol,
                action="hold",
                confidence=round(cal_conf, 3),
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=(
                    f"self_conflict: {symbol} üzerinde zaten {len(conflict_legs)} "
                    f"{opposite_side.upper()} açık — zıt yön ({cand_side.upper()}) engellendi"
                ),
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                mistake_verdict=_verdict_to_dict(verdict),
                self_conflict_report=self_conflict_report,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=["self_conflict_guard"],
            )
    else:
        self_conflict_report = {}

    # ----- Concentration guard (shadow-first) — aynı-sembol aynı-yön yığını -----
    # Aday aynı sembolde zaten açık AYNI yöne yeni leg ekliyorsa (DODO 1h+4h gibi tek
    # sinyalin TF'lere kopyalanması) bu tek market olayına 2x maruz kalmaktır. G4
    # correlation cluster equity'nin %30'unda tetikler (tek sembol için çok gevşek —
    # DODO 2 leg = equity'nin %9'u, G4 hiç görmedi); bu guard tek-sembol yığınına sıkı
    # sınır koyar. Shadow-her-zaman-hesaplanır; yalnız enabled + breach iken bloklar.
    concentration_report = _concentration_report(
        symbol, cand_side, open_positions, equity_usd, _concentration_cfg()
    )
    if concentration_report.get("active") and concentration_report.get("breach"):
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=(
                f"concentration: {symbol} üzerinde zaten "
                f"{concentration_report['open_same_dir_count']} {cand_side.upper()} açık "
                f"({concentration_report['exposure_pct']:.0%} equity) — aynı-yön yığını engellendi"
            ),
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            self_conflict_report=self_conflict_report,
            concentration_report=concentration_report,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["concentration_guard"],
        )

    # ----- G4: Correlation cluster cap (sadece küçültür, RiskGate'i bypass etmez) -----
    cluster = correlation.cluster_exposure(
        open_positions or [],
        symbol,
        "long" if action == "open_long" else "short",
        equity_usd,
        entries=corr_entries,
    )
    cluster_dict = asdict(cluster)
    if cluster.size_factor <= 0.0:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=(
                f"correlation_cluster: aynı yönlü exposure {cluster.cluster_pct:.0%}"
                f" ≥ cap {cluster.max_cluster_pct:.0%}"
            ),
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["correlation_cluster_cap"],
        )
    size *= min(1.0, cluster.size_factor)
    size = max(0.0, min(1.5, size))

    # ----- v2.7 D2: kripto türev riski (RiskGate'ten SONRA; yalnızca kısıtlayıcı) -----
    # Yalnızca crypto sembolleri + verified/OK snapshot karar zincirine girer.
    # 15m/1h reaksiyon için derivatives daha önemli (timeframe ağırlığı); asla
    # size artırmaz, asla RiskGate/DQS/halt'ı bypass etmez (bu kod yalnızca
    # RiskGate açıkken çalışır — hard gate'ler yukarıda zaten dönmüş olur).
    derivatives_dict: dict = {}
    deriv_snap = (snap.derivatives or {}).get(symbol)
    deriv_weight = derivatives_risk.timeframe_weight(timeframe)
    if deriv_snap is not None and deriv_weight > 0.0:
        dv = derivatives_risk.apply_timeframe(
            derivatives_risk.assess(deriv_snap, action), deriv_weight
        )
        derivatives_dict = {
            "level": dv.level,
            "size_factor": dv.size_factor,
            "block": dv.block,
            "reason": dv.reason,
            "evidence": list(dv.evidence),
            "squeeze_level": deriv_snap.squeeze_level,
            "squeeze_proxy": deriv_snap.squeeze_proxy,
            "funding_bias": deriv_snap.funding_bias,
            "is_proxy": deriv_snap.is_proxy,
        }
        if dv.block:
            return TradeDecision(
                symbol=symbol,
                action="hold",
                confidence=round(cal_conf, 3),
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=f"derivatives_risk: {dv.reason}",
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                mistake_verdict=_verdict_to_dict(verdict),
                cluster_report=cluster_dict,
                derivatives_report=derivatives_dict,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=[f"derivatives_risk:{dv.level}"],
            )
        size *= dv.size_factor
        size = max(0.0, min(1.5, size))

    # ----- v2.7 D4: realized volatility riski (RiskGate'ten SONRA; yalnızca kısıtlayıcı) -----
    # Yalnızca verified/OK (symbol, tf) snapshot karar zincirine girer. 15m/1h'de
    # vol shock daha etkili (timeframe ağırlığı); 1d/1w'de rejim bağlamı (block
    # CAUTION'a yumuşar). Asla size artırmaz, asla RiskGate/DQS/halt'ı bypass
    # etmez (bu kod yalnızca RiskGate açıkken çalışır).
    volatility_dict: dict = {}
    vol_snap = (snap.volatility or {}).get(symbol, {}).get(timeframe)
    vol_weight = volatility_risk.timeframe_weight(timeframe)
    if vol_snap is not None and vol_weight > 0.0:
        vv = volatility_risk.apply_timeframe(
            volatility_risk.assess(vol_snap, action), vol_weight
        )
        volatility_dict = {
            "level": vv.level,
            "size_factor": vv.size_factor,
            "block": vv.block,
            "reason": vv.reason,
            "evidence": list(vv.evidence),
            "regime": vol_snap.regime,
            "vol_state": vol_snap.vol_state,
            "realized_vol": vol_snap.realized_vol,
            "vol_zscore": vol_snap.vol_zscore,
        }
        if vv.block:
            return TradeDecision(
                symbol=symbol,
                action="hold",
                confidence=round(cal_conf, 3),
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=f"volatility_risk: {vv.reason}",
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                mistake_verdict=_verdict_to_dict(verdict),
                cluster_report=cluster_dict,
                derivatives_report=derivatives_dict,
                volatility_report=volatility_dict,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=[f"volatility_risk:{vv.level}"],
            )
        size *= vv.size_factor
        size = max(0.0, min(1.5, size))

    # ----- v2.7 D5: haber catalyst riski (RiskGate'ten SONRA; yalnızca kısıtlayıcı) -----
    # Yalnızca verified + yarı-ömrü dolmamış impact'ler bu (symbol, tf) hücresini
    # kısar. Rumor (verified=False) ve süresi dolmuş catalyst karar zincirine
    # girmez (yalnızca bağlam). Yön bağımsız; asla size artırmaz, asla RiskGate/
    # DQS/halt'ı bypass etmez (bu kod yalnızca RiskGate açıkken çalışır).
    catalyst_dict: dict = {}
    cv = catalyst_risk.assess(snap.catalyst_impacts, symbol, timeframe)
    if cv.level != "NONE":
        catalyst_dict = {
            "level": cv.level,
            "size_factor": cv.size_factor,
            "block": cv.block,
            "reason": cv.reason,
            "evidence": list(cv.evidence),
            "event_type": cv.event_type,
        }
        if cv.block:
            return TradeDecision(
                symbol=symbol,
                action="hold",
                confidence=round(cal_conf, 3),
                size_multiplier=0.0,
                consensus=cons,
                risk=risk,
                reason=f"catalyst_risk: {cv.reason}",
                raw_confidence=round(raw_conf, 4),
                confidence_source=conf_source,
                fingerprint=fp,
                mistake_verdict=_verdict_to_dict(verdict),
                cluster_report=cluster_dict,
                derivatives_report=derivatives_dict,
                volatility_report=volatility_dict,
                catalyst_report=catalyst_dict,
                timeframe=timeframe,
                candidate_action=candidate,
                blocked_by=[f"catalyst_risk:{cv.level}"],
            )
        size *= cv.size_factor
        size = max(0.0, min(1.5, size))

    # ----- v2.7 D3: options IV/skew/term riski (RiskGate'ten SONRA; yalnızca kısıtlayıcı) -----
    # Yalnızca BTC/ETH + verified/OK snapshot karar zincirine girer. Options daha
    # çok 4h/1d/1w bağlamıdır (timeframe ağırlığı yüksek); 15m/1h düşük ağırlık.
    # Asla size artırmaz (CHEAP_VOL bile yalnızca bağlam), asla RiskGate/DQS/halt'ı
    # bypass etmez (bu kod yalnızca RiskGate açıkken çalışır).
    options_dict: dict = {}
    opt_snap = (snap.options or {}).get(symbol)
    opt_weight = options_risk.timeframe_weight(timeframe)
    if opt_snap is not None and opt_weight > 0.0:
        ov = options_risk.apply_timeframe(
            options_risk.assess(opt_snap, action), opt_weight
        )
        if ov.level != "NONE":
            options_dict = {
                "level": ov.level,
                "size_factor": ov.size_factor,
                "block": ov.block,
                "reason": ov.reason,
                "evidence": list(ov.evidence),
                "regime": opt_snap.regime,
                "atm_iv": opt_snap.atm_iv,
                "skew_25d": opt_snap.skew_25d,
                "iv_rv_spread": opt_snap.iv_rv_spread,
                "term_slope": opt_snap.term_slope,
                "is_proxy": opt_snap.is_proxy,
            }
            if ov.block:
                return TradeDecision(
                    symbol=symbol,
                    action="hold",
                    confidence=round(cal_conf, 3),
                    size_multiplier=0.0,
                    consensus=cons,
                    risk=risk,
                    reason=f"options_risk: {ov.reason}",
                    raw_confidence=round(raw_conf, 4),
                    confidence_source=conf_source,
                    fingerprint=fp,
                    mistake_verdict=_verdict_to_dict(verdict),
                    cluster_report=cluster_dict,
                    derivatives_report=derivatives_dict,
                    volatility_report=volatility_dict,
                    catalyst_report=catalyst_dict,
                    options_report=options_dict,
                    timeframe=timeframe,
                    candidate_action=candidate,
                    blocked_by=[f"options_risk:{ov.level}"],
                )
            size *= ov.size_factor
            size = max(0.0, min(1.5, size))

    # ----- T2: timeframe politikası EN SON (RiskGate'ten sonra; sadece azaltır) -----
    blocked_by: list[str] = []
    if not pol["paper_execution"]:
        # 1w strategic view — doğrudan paper trade açmaz; yön bilgisi
        # matrix'te bias olarak görünür.
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"timeframe {timeframe} ({pol['role']}): paper execution kapalı — sadece bias",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
            derivatives_report=derivatives_dict,
            volatility_report=volatility_dict,
            catalyst_report=catalyst_dict,
            options_report=options_dict,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=["timeframe_policy:no_paper_execution"],
        )
    # Çarpan sadece küçültür (≤1.0 clamp'li) — blocked_by'a girmez,
    # reason + size_multiplier üzerinden görünür.
    size *= pol["risk_multiplier"]

    # ----- F5: Kelly sizing — boyutu ölçülen edge'e oransal CAP'le (yalnız küçültür).
    #  fractional-Kelly $ = fraction × f* × equity; size_mult cap'i = bu / max_pos.
    #  no-AI-boost: yalnız min() ile kısar, asla büyütmez. (Owner config; default KAPALI) -----
    kelly_cfg = _kelly_cfg()
    if kelly_cfg.get("enabled", False) and equity_usd > 0:
        max_pos = float((load_thresholds().get("paper_trading") or {}).get("max_position_usd", 0.0))
        if max_pos > 0:
            # F4-2 — flag açıkken Kelly de ampirik p ile (EV ile aynı kaynak);
            # kapalıyken p_for_ev == cal_conf (bayt-aynı).
            f_star = _kelly_fraction(p_for_ev, rr)
            fraction = float(kelly_cfg.get("fraction", 0.25))
            kelly_mult_cap = fraction * f_star * equity_usd / max_pos
            if kelly_mult_cap < size:
                size = max(0.0, kelly_mult_cap)
                blocked_by.append("kelly_cap")

    # ----- D: dinamik korelasyon vetosu (shadow-first, YALNIZ ENGELLER) — aday
    # sinyalin EN GÜÇLÜ akrabası (o anki |rho| en yüksek) KENDİ sinyaliyle ilişkiyi
    # çürütüyorsa işlem AÇILMAZ. 5y backtest: elenen işlemler −0.511 (çöp), 5/5 yıl.
    # Akraba otomatik (owner kararı); ağ yok (1d cache). enabled default false →
    # rapor gözlem, karar değişmez. Boyuttan ÖNCE ("girer miyim" → "ne kadar"). -----
    correlation_veto_report: dict = {}
    try:
        correlation_veto_report = correlation_veto.assess(
            symbol, cand_side, _veto_universe(), _correlation_veto_cfg(),
        )
    except Exception:  # gölge/veto fikri kararı asla düşürmez
        correlation_veto_report = {}
    if correlation_veto_report.get("active") and correlation_veto_report.get("vetoed"):
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"correlation_veto: {correlation_veto_report.get('reason', '')}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
            self_conflict_report=self_conflict_report,
            concentration_report=concentration_report,
            derivatives_report=derivatives_dict,
            volatility_report=volatility_dict,
            catalyst_report=catalyst_dict,
            options_report=options_dict,
            timeframe=timeframe,
            candidate_action=candidate,
            blocked_by=[*blocked_by, "correlation_veto"],
            correlation_veto_report=correlation_veto_report,
        )

    # ----- P1: boyut katmanları — inanç-boyu + oynaklık-paritesi (shadow-first,
    # YALNIZ KISAR). Sinyal gücüne oransal + oynaklığa ters orantılı boyut; her
    # katman config-flag default false → applied_factor 1.0 (boyut bayt-aynı,
    # rapor her kararda hesaplanır). 5y çok-rejim backtest: inanç edge ~2 kat,
    # vol-parite maxDD yarıya. RiskGate'i bypass etmez (zincirin en sonunda). -----
    sl_cfg = _sizing_layers_cfg()
    threshold_dist = (
        float(th["bullish_min"]) - 50.0 if action == "open_long"
        else 50.0 - float(th["bearish_max"])
    )
    realized_vol = getattr(vol_snap, "realized_vol", None) if vol_snap else None
    sizing_layers_report = sizing_layers.evaluate(
        score=cons.score, realized_vol=realized_vol, threshold_dist=threshold_dist,
        conviction_cfg=sl_cfg.get("conviction") or {},
        vol_parity_cfg=sl_cfg.get("vol_parity") or {},
        recent_edge=recent_edge, brake_cfg=sl_cfg.get("brake") or {},
    )
    sl_factor = float(sizing_layers_report["applied_factor"])
    if sl_factor < 1.0 and size > 0.0:
        size = max(0.0, round(size * sl_factor, 3))
        blocked_by.append("sizing_layers")

    # ----- P3 parça-2: quantum boyut-kısma (shadow-first, YALNIZ KISAR). Quantum
    # katkısı eşiği aşarsa (INVERSE kanıtı: yüksek sesle konuşunca kaybediyor) o
    # işlemde boyut × factor. Yön DEĞİŞMEZ (kaynak ağırlığa/trainer'a dokunmaz).
    # enabled default false → rapor gözlem, boyut bayt-aynı. -----
    quantum_dampen_report: dict = {}
    qd_cfg = _quantum_dampen_cfg()
    q_contrib = next((m.contribution for m in cons.modules if m.name == "quantum"), None)
    if q_contrib is not None:
        qd_on = bool(qd_cfg.get("enabled", False))
        qd_threshold = float(qd_cfg.get("contrib_threshold", 8.0))
        dampened = q_contrib >= qd_threshold
        quantum_dampen_report = {
            "active": qd_on, "quantum_contribution": round(float(q_contrib), 3),
            "threshold": qd_threshold, "dampened": bool(dampened),
        }
        if qd_on and dampened and size > 0.0:
            size = max(0.0, round(size * float(qd_cfg.get("factor", 0.5)), 3))
            blocked_by.append("quantum_dampen")

    # ----- Y-1: rejim risk freni — kanıtı çift-negatif (canlı AUTO kohort +
    # backtest challenger) rejimde boyut kıs (YALNIZ küçültür). SHADOW her
    # kararda: rapor flag'ten bağımsız taşınır (aktivasyon kanıtı flag'siz
    # birikir); uygulama yalnız `regime_risk_brake.enabled` açıkken. -----
    brake_mult, brake_evidence = regime_risk_brake.active_mult(regime.label)
    regime_brake_report: dict = {}
    if brake_evidence is not None:
        brake_applied = regime_risk_brake.enabled()
        regime_brake_report = {**brake_evidence, "applied": brake_applied}
        if brake_applied and brake_mult < 1.0:
            size = max(0.0, round(size * brake_mult, 3))
            blocked_by.append("regime_risk_brake")

    # ----- Y-5: meta-label kapısı — SALT-GÖLGE (mlfinlab meta-labeling): açılış
    # adayına "GİR/GİRME" hükmü damgalanır + fingerprint'le gölge deftere yazılır
    # (scorecard kapanışla birleştirir). Karar/boyut DEĞİŞMEZ; uygulama flag'i
    # YOK — aktivasyon seçicilik kanıtı + owner kararıyla ayrı dilim. -----
    meta_gate_report: dict = {}
    if candidate in ("open_long", "open_short"):
        try:
            meta_gate_report = meta_gate.assess(
                dominant_module=cons.dominant_module, timeframe=timeframe,
                regime_label=regime.label, expected_value=expected_value,
                p_win_empirical=p_win_empirical, mistake_action=verdict.action,
                regime_braked=brake_evidence is not None,
            )
            meta_gate.record_shadow(fp, meta_gate_report)
        except Exception:  # gölge hükmü kararı asla düşürmez
            meta_gate_report = {}

    # Karar-kanıt tüketicisi: tüm learning'leri TEK fikre indir. VARSAYILAN GÖLGE
    # (boyut değişmez); LEARNING_ADVISOR_APPLY=1 iken advice yalnız KISAR (no-boost).
    # Asla raise etmez — kararı düşürmez.
    learning_advice: dict = {}
    if candidate in ("open_long", "open_short"):
        try:
            adv = learning_advisor.advise(
                symbol=symbol, timeframe=timeframe, regime=regime.label,
                dominant_module=cons.dominant_module, mistake_action=verdict.action,
                meta_report=meta_gate_report, calibrated_confidence=cal_conf,
                expected_value=expected_value, min_confidence=min_open_conf,
            )
            if learning_advisor.apply_enabled() and adv.size_hint < 1.0 and size > 0.0:
                size = max(0.0, round(size * adv.size_hint, 3))
                adv.applied = True
                if adv.stance != "CONFIRM":
                    blocked_by.append(f"learning_advisor:{adv.stance.lower()}")
            learning_advice = learning_advisor.to_dict(adv)
        except Exception:  # gölge/uygulama fikri kararı asla düşürmez
            learning_advice = {}

    return TradeDecision(
        symbol=symbol,
        action=action,
        confidence=round(min(0.99, cal_conf), 3),
        size_multiplier=round(size, 3),
        consensus=cons,
        risk=risk,
        reason=(
            f"{cons.direction} signal · dominant={cons.dominant_module}"
            + (f" · mistake:{verdict.action.lower()}" if verdict.action != "NEUTRAL" else "")
            + (f" · correlation:{cluster.status.lower()}" if cluster.status != "OK" else "")
            + (
                f" · deriv:{derivatives_dict['level'].lower()}"
                if derivatives_dict and derivatives_dict.get("level") not in (None, "NONE")
                else ""
            )
            + (
                f" · vol:{volatility_dict['level'].lower()}"
                if volatility_dict and volatility_dict.get("level") not in (None, "NONE")
                else ""
            )
            + (
                f" · catalyst:{catalyst_dict['level'].lower()}"
                if catalyst_dict and catalyst_dict.get("level") not in (None, "NONE")
                else ""
            )
            + (
                f" · opt:{options_dict['level'].lower()}"
                if options_dict and options_dict.get("level") not in (None, "NONE")
                else ""
            )
            + (f" · tf:{timeframe}×{pol['risk_multiplier']}" if pol["risk_multiplier"] < 1.0 else "")
        ),
        raw_confidence=round(raw_conf, 4),
        confidence_source=conf_source,
        fingerprint=fp,
        mistake_verdict=_verdict_to_dict(verdict),
        cluster_report=cluster_dict,
        self_conflict_report=self_conflict_report,
        concentration_report=concentration_report,
        derivatives_report=derivatives_dict,
        volatility_report=volatility_dict,
        catalyst_report=catalyst_dict,
        options_report=options_dict,
        timeframe=timeframe,
        candidate_action=candidate,
        blocked_by=blocked_by,
        actionable=size > 0.0,
        expected_value=round(expected_value, 4),
        p_win_empirical=p_win_empirical,
        expected_value_empirical=expected_value_empirical,
        regime_brake_report=regime_brake_report,
        meta_gate_report=meta_gate_report,
        learning_advice=learning_advice,
        sizing_layers_report=sizing_layers_report,
        correlation_veto_report=correlation_veto_report,
        quantum_dampen_report=quantum_dampen_report,
    )


def decide_all(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
    open_positions: list | None = None,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    regime = classify(snap)
    # P0 — olay riski yalnızca kısıtlayıcı ek candidate; DQS/halt'ı ezemez.
    risk = evaluate_risk(
        paper_state_input,
        event_candidates=event_risk.risk_candidates(snap.catalysts),
    )
    # Tek pass mistake özeti — tüm semboller için aynı snapshot.
    mems = mistake_memory.summary()
    # P3 fren — sistemin güncel edge'i (tüm kararlar için tek pass; state okuma tekrarı yok).
    _brake_lb = int(((load_thresholds().get("sizing_layers") or {}).get("brake") or {}).get("lookback", 30))
    recent_edge = _recent_edge(_brake_lb)
    positions = open_positions or []
    # Korelasyon matrisi tek pass (aday + açık pozisyon sembolleri).
    corr_entries = correlation.matrix(
        sorted({*symbols, *(p.symbol for p in positions)})
    )
    decisions = [
        decide_for_symbol(
            s,
            snap,
            regime,
            risk,
            mistakes=mems,
            open_positions=positions,
            equity_usd=paper_state_input.equity_usd,
            corr_entries=corr_entries,
            recent_edge=recent_edge,
        )
        for s in symbols
    ]
    return regime, risk, decisions


def _intra_batch_guard_enabled() -> bool:
    """Intra-batch same-symbol cluster guard açık mı (default KAPALI). Açıkken
    decide_matrix pass içinde açılan kardeş pozisyonları sonraki hücrelere besler →
    aynı-sembol çok-TF yığını correlation cap'e tabi olur. Politika kararı (owner)."""
    try:
        return bool(
            (load_thresholds().get("paper_trading") or {}).get("intra_batch_cluster_guard", False)
        )
    except (OSError, KeyError, ValueError, TypeError):
        return False


@dataclass(frozen=True)
class _PendingPosition:
    """decide_matrix pass'i İÇİNDE açılması önerilen (henüz gerçek olmayan) pozisyon.

    Kardeş (symbol, tf) hücrelerinin correlation cluster cap'ine girsin diye üretilir
    — intra-batch aynı-sembol yığılmasını (örn. XAGUSD 15m/1h/4h short) cap görebilsin.
    cluster_exposure yalnız .symbol/.side/.size_usd/.id okur."""

    id: str
    symbol: str
    side: str
    size_usd: float


def decide_matrix(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
    open_positions: list | None = None,
    timeframes: list[str] | None = None,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    """T2 — (symbol, timeframe) karar matrisi.

    Her hücre decide_for_symbol'dan geçer (RiskGate önce, timeframe sonra).
    Üst-TF bias kuralı: 1w consensus yönü alt TF open kararının TERSİYSE
    boyut ×0.5 (asla artırma yok; 1w zaten kendi başına trade açamaz).
    """
    regime = classify(snap)
    # P0 — olay riski yalnızca kısıtlayıcı ek candidate; DQS/halt'ı ezemez.
    risk = evaluate_risk(
        paper_state_input,
        event_candidates=event_risk.risk_candidates(snap.catalysts),
    )
    mems = mistake_memory.summary()
    positions = open_positions or []
    corr_entries = correlation.matrix(
        sorted({*symbols, *(p.symbol for p in positions)})
    )
    tfs = [tf for tf in (timeframes or list(TIMEFRAMES)) if tf in TIMEFRAMES]
    # Intra-batch yığılma koruması: pass içinde açılması önerilen kardeş hücreleri
    # büyüyen listeye ekle → sonraki hücreler onları open_positions'ta görüp aynı
    # correlation cap'e tabi olur. Flag kapalıyken eski (pass-başı-snapshot) davranış.
    guard_on = _intra_batch_guard_enabled()
    max_pos = float((load_thresholds().get("paper_trading") or {}).get("max_position_usd", 0.0))
    pass_positions = list(positions)
    decisions: list[TradeDecision] = []
    for s in symbols:
        per_tf: dict[str, TradeDecision] = {}
        for tf in tfs:
            d = decide_for_symbol(
                s,
                snap,
                regime,
                risk,
                mistakes=mems,
                open_positions=pass_positions,
                equity_usd=paper_state_input.equity_usd,
                corr_entries=corr_entries,
                timeframe=tf,
            )
            per_tf[tf] = d
            if (
                guard_on
                and max_pos > 0
                and d.action in ("open_long", "open_short")
                and d.size_multiplier > 0
            ):
                pass_positions.append(
                    _PendingPosition(
                        id=f"pending:{s}:{tf}",
                        symbol=s,
                        side="long" if d.action == "open_long" else "short",
                        size_usd=round(d.size_multiplier * max_pos, 2),
                    )
                )
        weekly = per_tf.get("1w")
        if weekly is not None:
            bias = weekly.consensus.direction
            for tf, d in per_tf.items():
                if tf == "1w" or d.action not in {"open_long", "open_short"}:
                    continue
                conflict = (d.action == "open_long" and bias == "bearish") or (
                    d.action == "open_short" and bias == "bullish"
                )
                if conflict:
                    d.size_multiplier = round(d.size_multiplier * 0.5, 3)
                    d.blocked_by.append("1w_bias_conflict:scale_down")
                    d.reason += f" · 1w bias {bias} → size×0.5"
        decisions.extend(per_tf[tf] for tf in tfs)
    return regime, risk, decisions


# Matrix hücresinin actionable/suspended rozetini frontend HESAPLAMAZ —
# backend ViewModel üretir (DASHBOARD_RULES).
def matrix_view(
    regime: RegimeOutput,
    risk: RiskDecision,
    decisions: list[TradeDecision],
    snap: MarketSnapshot,
    symbols: list[str],
    timeframes: list[str] | None = None,
) -> dict:
    from datetime import UTC, datetime

    tfs = [tf for tf in (timeframes or list(TIMEFRAMES)) if tf in TIMEFRAMES]
    suspended = (
        risk.action in {"KILL_SWITCH", "RISK_REDUCE", "NO_POSITION_INCREASE"}
        or snap.quality.status == "BLOCKED"
    )
    # P0 — olay riski ayrı görünür blok (RiskGate'i bypass etmez; hangi olayın
    # hücreleri kıstığını dashboard'da göstermek için). Restrictive olduğunda
    # zaten yukarıdaki `risk` içine NO_POSITION_INCREASE candidate olarak girmiş.
    ev = event_risk.assess(snap.catalysts)
    # v2.7 D2 — kripto türev özeti (yalnızca kısıtlayıcı; etkilenen hücreler
    # cell.blocked_by="derivatives_risk:*" ile zaten görünür). Bu blok panel
    # banner'ı için per-symbol squeeze/funding durumunu taşır.
    derivatives_summary = [
        {
            "symbol": d.symbol,
            "squeeze_level": d.squeeze_level,
            "squeeze_proxy": d.squeeze_proxy,
            "funding_bias": d.funding_bias,
            "funding_rate": d.funding_rate,
            "is_proxy": d.is_proxy,
            "status": d.status,
            "verified": d.verified,
        }
        for d in (snap.derivatives or {}).values()
        if d.status == "OK"
    ]
    # v2.7 D4 — realized volatility özeti (banner). Yalnızca status=OK + dikkat
    # çeken hücreler (ELEVATED/EXTREME rejim veya shock/expansion/squeeze).
    # Etkilenen hücreler ayrıca cell.blocked_by="volatility_risk:*" taşır.
    volatility_summary = [
        {
            "symbol": v.symbol,
            "timeframe": v.timeframe,
            "regime": v.regime,
            "vol_state": v.vol_state,
            "realized_vol": v.realized_vol,
            "vol_zscore": v.vol_zscore,
            "status": v.status,
            "verified": v.verified,
        }
        for by_tf in (snap.volatility or {}).values()
        for v in by_tf.values()
        if v.status == "OK" and (v.regime in ("ELEVATED", "EXTREME") or v.vol_state != "normal")
    ]
    # v2.7 D5 — catalyst özeti (banner). Yalnızca verified + yarı-ömrü dolmamış +
    # kısıtlayıcı (CONTEXT_ONLY hariç). Etkilenen hücreler ayrıca
    # cell.blocked_by="catalyst_risk:*" taşır.
    now_ref = datetime.now(UTC)
    catalyst_summary = [
        {
            "catalyst_id": c.catalyst_id,
            "headline_id": c.headline_id,
            "event_type": c.event_type,
            "actionability": c.actionability,
            "affected_assets": list(c.affected_assets),
            "affected_timeframes": list(c.affected_timeframes),
            "expected_half_life_minutes": c.expected_half_life_minutes,
            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
            "surprise_level": c.surprise_level,
            "confidence": c.confidence,
            "verified": c.verified,
        }
        for c in (snap.catalyst_impacts or [])
        if c.verified
        and c.actionability != "CONTEXT_ONLY"
        and (c.valid_until is None or now_ref <= c.valid_until)
    ]
    # v2.7 D3 — options özeti (banner). Yalnızca status=OK + dikkat çeken rejim
    # (NORMAL hariç). Etkilenen hücreler ayrıca cell.blocked_by="options_risk:*"
    # taşır. Skew GERÇEK greeks değil → is_proxy.
    options_summary = [
        {
            "symbol": o.symbol,
            "regime": o.regime,
            "atm_iv": o.atm_iv,
            "realized_vol": o.realized_vol,
            "iv_rv_spread": o.iv_rv_spread,
            "skew_25d": o.skew_25d,
            "put_call_oi_ratio": o.put_call_oi_ratio,
            "term_slope": o.term_slope,
            "front_expiry": o.front_expiry,
            "next_expiry": o.next_expiry,
            "long_expiry": o.long_expiry,
            "is_proxy": o.is_proxy,
            "source": o.source,
            "freshness": o.freshness,
            "status": o.status,
            "verified": o.verified,
        }
        for o in (snap.options or {}).values()
        if o.status == "OK" and o.regime != "NORMAL"
    ]
    cells = []
    for d in decisions:
        actionable = bool(d.actionable) and not suspended
        if suspended:
            status = "SUSPENDED"
        elif actionable:
            status = "ACTIONABLE"
        else:
            status = "NOT_ACTIONABLE"
        cells.append(
            {
                "symbol": d.symbol,
                "timeframe": d.timeframe,
                "action": d.action,
                "candidate_action": d.candidate_action,
                "score": d.consensus.score,
                "direction": d.consensus.direction,
                "confidence": d.confidence,
                "size_multiplier": d.size_multiplier,
                "reason": d.reason,
                "blocked_by": list(d.blocked_by),
                "warnings": list(getattr(d.consensus, "warnings", []) or []),
                "actionable": actionable,
                "status": status,
                "paper_action": d.action if actionable else "none",
                # F5 gözlem — beklenen değer (R-katı); ev_gate KAPALI olsa da dolu.
                # Dashboard/owner pozitif-EV dağılımını görüp ev_gate enable kararını verir.
                "expected_value": d.expected_value,
                # F4-2 gözlem — ampirik (tf|rejim) p(win) + onunla hesaplanan EV.
                # Owner cal_conf-EV ile ampirik-EV ayrışmasını izleyip
                # empirical_pwin.enabled aktivasyon kararını verir.
                "p_win_empirical": d.p_win_empirical,
                "expected_value_empirical": d.expected_value_empirical,
                # Y-1 gözlem — rejim risk freni (shadow-first): kanıt çift-negatifse
                # fren bilgisi + applied bayrağı. Owner aktivasyon kararını buradan
                # izler (flag OFF iken applied=False ile birikir). Boş = kanıt yok.
                "regime_brake": dict(d.regime_brake_report),
                # Y-5 gözlem — meta-label kapısının gölge hükmü (TAKE/SKIP + skor).
                # Karara uygulanmaz; seçicilik kanıtı /learning/meta-gate scorecard.
                "meta_gate": dict(d.meta_gate_report),
                # Karar-kanıt tüketicisi (2026-07-09): tüm learning'lerin TEK
                # birleşik fikri. VARSAYILAN GÖLGE (applied=False); owner
                # LEARNING_ADVISOR_APPLY ile canlıya alır. Boş = aday değil.
                "learning_advice": dict(d.learning_advice),
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "symbols": list(symbols),
        "timeframes": tfs,
        "regime": regime.label,
        "risk_gate": {
            "action": risk.action,
            "reason": risk.reason,
            "evidence": list(risk.evidence),
        },
        "dqs_status": snap.quality.status,
        "suspended": suspended,
        "event_risk": {
            "level": ev.level,
            "action": ev.action,
            "reason": ev.reason,
            "evidence": list(ev.evidence),
            "restrictive": ev.restrictive,
            "triggers": [
                {
                    "id": t.id,
                    "title": t.title,
                    "importance": t.importance,
                    "hours_until": t.hours_until,
                    "days_until": t.days_until,
                    "level": t.level,
                }
                for t in ev.triggers
            ],
        },
        "derivatives": derivatives_summary,
        "volatility": volatility_summary,
        "catalysts": catalyst_summary,
        "options": options_summary,
        "cells": cells,
    }
