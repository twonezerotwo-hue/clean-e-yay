"""tf_scoring_v2 GÖLGE üretici (D6, İZOLE salt-gözlem).

`packages.scoring.tf_scoring_v2` saf skorlamasını CANLI barlar üzerinde koşturup
"v2 şu an ne derdi" görünümünü izole artifact'a yazar. Canlı skora/karara/paper'a
SIFIR dokunuş — yalnız gözlem (D7 gölge yarışın girdisi).

Sözleşme:
- Flag `TF_SCORING_V2_SHADOW` (env, DEFAULT OFF). OFF → tam no-op (worker koşusu
  bayt-eşdeğer). Import lazy: flag kapalıyken skorlama bağımlılıkları yüklenmez.
- Ağırlıklar `subsignal_scorecard` artifact'ından (kanıt-cap); karne yoksa boş
  görünüm (dürüst: kanıt yoksa v2 yön üretmez).
- Bar arşivi (BAR_HISTORY_ENABLED) varsa birleşik pencere kullanılır (karneyle
  aynı kaynak → tutarlı).
- ASLA raise etmez; her sembol izole (biri patlarsa diğerleri sürer).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

FLAG = "TF_SCORING_V2_SHADOW"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})
_ART = "data/runtime/tf_scoring_v2_shadow.json"
_MIN_BARS = 210  # ema200 + pay (karneyle aynı ısınma)


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def artifact_path() -> Path:
    return Path(_ART)


def _load_scorecard() -> dict:
    from packages.learning import subsignal_scorecard
    try:
        path = subsignal_scorecard.artifact_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


def analyze(symbols: list[str] | None = None) -> dict:
    """Her sembol için v2 gölge yön skoru (DIRECTION TF'leri + harman). Salt-hesap;
    hiçbir yan etki yok. Karne kanıtı yoksa sembol 'no_evidence' işaretlenir."""
    from packages.data.providers.ohlcv import get_bars, history
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
    from packages.scoring import tf_scoring_v2 as v2

    scorecard = _load_scorecard()
    syms = symbols or sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD"})
    per_symbol: dict[str, dict] = {}
    for sym in syms:
        try:
            tf_scores: dict[str, float] = {}
            convictions: dict[str, float] = {}
            drivers: dict[str, dict] = {}
            for tf in v2.DIRECTION_TFS:
                bars = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
                if len(bars) < _MIN_BARS:
                    continue
                weights = v2.signal_weights(scorecard, tf)
                leans = v2.collect_leans(tf, bars)
                score = v2.direction_score(tf, leans, weights)
                conv = v2.conviction(weights)
                if score is not None:
                    tf_scores[tf] = round(score, 4)
                    convictions[tf] = round(conv, 4)
                    # Hangi sinyaller sürdü (kanıtlı ağırlıklı, şeffaflık).
                    drivers[tf] = {
                        name: {"lean": round(leans[name], 3), "weight": round(w, 4)}
                        for name, w in weights.items()
                        if w > 0.0 and name in leans
                    }
            blended = v2.blended_direction(tf_scores, convictions)
            per_symbol[sym] = {
                "direction": None if blended is None else round(blended, 4),
                "bias": _bias_label(blended),
                "tf_scores": tf_scores,
                "convictions": convictions,
                "drivers": drivers,
                "status": "OK" if blended is not None else "no_evidence",
            }
        except Exception as exc:  # defensive — bir sembol diğerlerini düşürmesin
            per_symbol[sym] = {"status": f"ERROR:{type(exc).__name__}"}
    scored = sum(1 for v in per_symbol.values() if v.get("status") == "OK")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "tf_scoring_v2_shadow",
        "scorecard_engine": scorecard.get("engine"),
        "scorecard_generated_at": scorecard.get("generated_at"),
        "symbols_scored": scored,
        "per_symbol": per_symbol,
        "note": (
            "İZOLE gölge: tf_scoring_v2 katmanlı yön (1d/4h DIRECTION, kanıt-cap "
            "ağırlık karneden). Canlı skora/karara/paper'a DOKUNMAZ (D7 yarış girdisi)."
        ),
    }


def _bias_label(direction: float | None) -> str:
    if direction is None:
        return "NONE"
    if direction >= 0.15:
        return "BULLISH"
    if direction <= -0.15:
        return "BEARISH"
    return "NEUTRAL"


def _write(payload: dict) -> None:
    path = artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run() -> dict:
    """Worker-adımı: flag AÇIKSA v2 gölge skorlarını üret + artifact yaz; KAPALI
    → no-op. Ucuz (sembol başına anlık hesap; per-bar döngü yok)."""
    if not enabled():
        return {"status": "DISABLED"}
    rep = analyze()
    _write(rep)
    return {"status": "OK", "symbols_scored": rep["symbols_scored"]}


__all__ = ["FLAG", "analyze", "artifact_path", "enabled", "run"]
