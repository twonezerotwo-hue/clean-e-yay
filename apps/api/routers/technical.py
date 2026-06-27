"""GET /api/v1/technical/insight/{asset_code} — multi-timeframe Fibonacci evidence.

Thin read-only HTTP layer over the technical provider. No paper-state mutation, no
trade actions, no broker. Fibonacci is technical EVIDENCE only — it never opens a
trade and never bypasses RiskGate.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.providers import ohlcv
from packages.data.providers import technical as tech_provider
from packages.data.providers.technical import fibonacci
from packages.data.registry import assets as asset_registry
from packages.decision import agent_pipeline
from packages.elliott import engine as elliott_engine
from packages.learning import tf_weight_trainer
from packages.liquidity import sweep as liquidity_sweep_engine
from packages.paper import state as paper_state
from packages.risk import engine as risk_engine
from packages.scoring import exhaustion as exhaustion_engine
from packages.scoring import location as location_engine
from packages.scoring import trigger as trigger_engine
from packages.volume import engine as volume_engine
from packages.vwap import engine as vwap_engine
from packages.zones import engine as zone_engine

router = APIRouter(tags=["technical"])


@router.get("/technical/insight/{asset_code}")
def get_technical_insight(asset_code: str) -> dict:
    return tech_provider.get_technical_insight(asset_code).model_dump()


@router.get("/technical/elliott/{asset_code}")
def get_elliott_scenario(asset_code: str, timeframe: str = "1d") -> dict:
    """Elliott Wave senaryosu (EVIDENCE only) — read-only.

    Fibonacci insight ile aynı sözleşme: trade açmaz, RiskGate'i bypass
    etmez, hiçbir canlı karar zincirine bağlı değildir (additive read
    surface). NO_VALID_COUNT meşru bir sonuçtur, hata değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    return elliott_engine.analyze(bars, timeframe=timeframe).model_dump()


@router.get("/technical/zones/{asset_code}")
def get_zone_analysis(asset_code: str, timeframe: str = "1d") -> dict:
    """Support/resistance zone analizi (EVIDENCE only) — read-only.

    Fibonacci insight ile aynı sözleşme: trade açmaz, RiskGate'i bypass
    etmez, hiçbir canlı karar zincirine bağlı değildir (additive read
    surface). Supply/demand zone tespiti bu sürümün kapsamı dışındadır.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    current = bars[-1].close if bars else None
    return zone_engine.analyze(bars, timeframe=timeframe, current_price=current).model_dump()


@router.get("/technical/volume/{asset_code}")
def get_volume_analysis(asset_code: str, timeframe: str = "1d") -> dict:
    """Hacim doğrulama analizi (EVIDENCE only) — read-only.

    Fibonacci insight ile aynı sözleşme: trade açmaz, RiskGate'i bypass
    etmez, hiçbir canlı karar zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    return volume_engine.analyze(bars, timeframe=timeframe).model_dump()


@router.get("/technical/vwap/{asset_code}")
def get_vwap_analysis(asset_code: str, timeframe: str = "1d") -> dict:
    """VWAP / Anchored VWAP analizi (EVIDENCE only) — read-only.

    Fibonacci insight ile aynı sözleşme: trade açmaz, RiskGate'i bypass
    etmez, hiçbir canlı karar zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    current = bars[-1].close if bars else None
    return vwap_engine.analyze(bars, timeframe=timeframe, current_price=current).model_dump()


@router.get("/technical/liquidity-sweep/{asset_code}")
def get_liquidity_sweep_analysis(asset_code: str, timeframe: str = "1d") -> dict:
    """Liquidity sweep / stop-hunt tespiti (EVIDENCE only) — read-only.

    Fibonacci insight ile aynı sözleşme: trade açmaz, RiskGate'i bypass
    etmez, hiçbir canlı karar zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    return liquidity_sweep_engine.analyze(bars, timeframe=timeframe).model_dump()


@router.get("/technical/exhaustion/{asset_code}")
def get_exhaustion_score(asset_code: str, timeframe: str = "1d") -> dict:
    """Exhaustion Score (EVIDENCE only, yön skoru DEĞİLDİR) — read-only.

    Volume Validation + Liquidity Sweep kanıtlarını besler. Hiçbir karar
    zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    volume = volume_engine.analyze(bars, timeframe=timeframe)
    sweep = liquidity_sweep_engine.analyze(bars, timeframe=timeframe)
    return exhaustion_engine.analyze(bars, timeframe=timeframe, volume=volume, sweep=sweep).model_dump()


@router.get("/technical/location-score/{asset_code}")
def get_location_score(asset_code: str, timeframe: str = "1d") -> dict:
    """Location Score (EVIDENCE only) — read-only.

    Zone Engine + Fibonacci + VWAP + Liquidity Sweep kanıtlarını birleştirir.
    Hiçbir karar zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    current = bars[-1].close if bars else None
    zone = zone_engine.analyze(bars, timeframe=timeframe, current_price=current)
    fib = fibonacci.analyze(bars, timeframe="1D" if timeframe == "1d" else "4H", current_price=current) if bars else None
    vwap = vwap_engine.analyze(bars, timeframe=timeframe, current_price=current) if bars else None
    sweep = liquidity_sweep_engine.analyze(bars, timeframe=timeframe) if bars else None
    return location_engine.analyze(zone, fib=fib, vwap=vwap, sweep=sweep).model_dump()


@router.get("/technical/trigger/{asset_code}")
def get_trigger_analysis(asset_code: str, timeframe: str = "1d") -> dict:
    """Trigger Engine (EVIDENCE only) — read-only.

    Mum formasyonu + Volume + VWAP + Liquidity Sweep kanıtlarını birleştirir.
    Hiçbir karar zincirine bağlı değildir.
    """
    bars = ohlcv.get_bars(asset_code, timeframe) or []
    volume = volume_engine.analyze(bars, timeframe=timeframe)
    current = bars[-1].close if bars else None
    vwap = vwap_engine.analyze(bars, timeframe=timeframe, current_price=current)
    sweep = liquidity_sweep_engine.analyze(bars, timeframe=timeframe)
    return trigger_engine.analyze(bars, timeframe=timeframe, volume=volume, vwap=vwap, sweep=sweep).model_dump()


@router.get("/technical/agent-matrix")
def get_agent_matrix() -> dict:
    """Read-only multi-TF agent pipeline (steps 1–6) as a per-symbol matrix.

    Thin HTTP layer — composition lives in `packages.decision.agent_pipeline`. The
    global RiskGate action is computed first and applied inside the pipeline; the
    per-trade cost + R:R gate is final. No paper-state mutation, no trade actions,
    no broker.
    """
    snap = get_cached_snapshot()
    ps = paper_state.load()
    risk = risk_engine.evaluate(
        risk_engine.RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )
    )
    # Trust-gated live tf_weights: None when calibration hasn't validated yet
    # (strategy-agnostic equal weighting). Defensive — never breaks the read path.
    try:
        tf_weights = tf_weight_trainer.resolve_live_tf_weights()
    except Exception:
        tf_weights = None
    views = agent_pipeline.build_agent_matrix(
        asset_registry.trade_symbols(), risk_action=risk.action, tf_weights=tf_weights,
    )
    return agent_pipeline.matrix_viewmodel(views, risk_action=risk.action)
