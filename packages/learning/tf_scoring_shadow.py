"""tf_scoring üretici — CANLI touche'un yön kaynağı (v4 birincil + backup yedek).

Owner kararı (2026-07-12): canlı teknik oy = tf_scoring_v4 (owner birleşik
formülü); v4 çekimserse touche_backup (v2 rejim-anahtarlı motor) konuşur; ikisi
de yoksa consensus zemin teknik motora düşer. Bu modül her cycle iki yönü de
hesaplayıp artifact'a yazar; canlı `consensus.engine._touche_shadow` oradan okur.

Her sembol için, rejim-anahtarlı konuşan TF'te (UP→1d, DOWN→4h):
- `direction_v4`     = owner birleşik formülü (elliott+trend+bölge+kapılı-
  uyumsuzluk; backtest-doğrulanmış ağırlıklar). −1..+1. BİRİNCİL.
- `direction_backup` = touche_backup: yalnız EDGE-kanıtlı sinyaller, karne
  ağırlıklarıyla (2026-07-06→12 arası canlı motordu; kanıtı en derin yedek).

Sözleşme:
- Flag `TF_SCORING_V2_SHADOW` (env, tarihsel ad — iki ortamda senkron,
  yeniden adlandırılmaz). OFF → üretim durur; canlı touche artifact bayatlayınca
  (3 saat) zemin motora düşer — sessiz kırılma yok, kademeli düşüş.
- Import lazy: flag kapalıyken skorlama bağımlılıkları yüklenmez.
- Bar arşivi (BAR_HISTORY_ENABLED) varsa birleşik pencere kullanılır.
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

# Rejim → konuşma hakkı olan DIRECTION TF'i (v2.regime_directed ile aynı eşleme).
_SPEAKER = {"UP": "1d", "DOWN": "4h"}


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def artifact_path() -> Path:
    return Path(os.environ.get("TF_SCORING_V2_SHADOW_PATH", _ART))


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
    """Her sembol için v4 (BİRİNCİL) + backup (YEDEK) yön skoru.

    Salt-hesap; hiçbir yan etki yok. Rejim-anahtarlı konuşan TF'te ikisini de
    üretir → canlı touche kademesi + doğrulama karnesi (race) buradan beslenir."""
    from packages.data.providers.ohlcv import get_bars, history
    from packages.scoring import tf_scoring_v2 as v2
    from packages.scoring import tf_scoring_v4 as v4
    from packages.signals import regime_gate

    scorecard = _load_scorecard()
    # v4 bölge merceği: zone_proposer artifact'ı REUSE (yeniden hesap yok —
    # "katmanlar birbirinden haberdar"). Artifact yoksa bölge/uyumsuzluk lean=0.
    zones_by_symbol: dict[str, list] = {}
    try:
        from packages.learning import zone_proposer
        for a in (zone_proposer._load() or {}).get("assets") or []:
            zones_by_symbol[str(a.get("symbol"))] = list(a.get("zones") or [])
    except Exception:
        zones_by_symbol = {}

    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
    syms = symbols or sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD"})
    per_symbol: dict[str, dict] = {}
    for sym in syms:
        try:
            tf_scores_v4: dict[str, float] = {}       # v4 owner-formülü, TF başına
            tf_scores_backup: dict[str, float] = {}   # backup: EDGE-only karne yolu
            bar_marks: dict[str, dict] = {}           # karne defteri: fiyat/ts damgası
            regime_info: dict | None = None
            for tf in v2.DIRECTION_TFS:
                bars = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
                if len(bars) < _MIN_BARS:
                    continue
                # Karne defteri: konuşan TF'in son KAPANMIŞ barının ts+close'u.
                last = bars[-1]
                bar_marks[tf] = {"ts": last.ts.isoformat(), "close": round(last.close, 6)}
                base_leans = v2.collect_leans(tf, bars)
                # v4: leans REUSE + bölge (artifact) + kapılı-uyumsuzluk
                s_v4 = v4.tf_direction(tf, v4.compute_leans(
                    tf, bars, zones_by_symbol.get(sym, []), base_leans))
                if s_v4 is not None:
                    tf_scores_v4[tf] = round(s_v4, 4)
                # backup: yalnız EDGE-kanıtlılar, karne ağırlıklarıyla
                s_bak = v2.direction_score(tf, base_leans, v2.signal_weights(scorecard, tf))
                if s_bak is not None:
                    tf_scores_backup[tf] = round(s_bak, 4)
                # Hava: 1d kapanışlarından (backtest tasarımıyla aynı)
                if tf == "1d":
                    rg = regime_gate.assess([b.close for b in bars])
                    if rg is not None:
                        regime_info = {"regime": rg.regime, "er": rg.er}

            regime = (regime_info or {}).get("regime")
            speaker = _SPEAKER.get(regime or "")
            d4 = v4.direction(tf_scores_v4, regime)
            dbak = v2.regime_directed(tf_scores_backup, regime)
            has_dir = d4 is not None or dbak is not None
            per_symbol[sym] = {
                "status": "OK" if (speaker and has_dir) else "no_evidence",
                "direction_v4": None if d4 is None else round(d4, 4),
                "direction_backup": None if dbak is None else round(dbak, 4),
                "bias": _bias_label(d4 if d4 is not None else dbak),
                "regime": regime_info,
                "speaker_tf": speaker,
                "tf_scores_v4": tf_scores_v4,
                "bar_marks": bar_marks,
            }
        except Exception as exc:  # defensive — bir sembol diğerlerini düşürmesin
            per_symbol[sym] = {"status": f"ERROR:{type(exc).__name__}"}

    scored = sum(1 for v in per_symbol.values() if v.get("status") == "OK")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "tf_scoring_v4_live",
        "scorecard_engine": scorecard.get("engine"),
        "scorecard_generated_at": scorecard.get("generated_at"),
        "symbols_scored": scored,
        "per_symbol": per_symbol,
        "note": (
            "CANLI touche kaynağı: rejim-anahtarlı konuşan TF'te (UP→1d, DOWN→4h) "
            "v4 owner formülü BİRİNCİL, touche_backup (EDGE-kanıtlı karne yolu) "
            "YEDEK. consensus._touche_shadow okur; bayatsa zemin motora düşer."
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
    """Worker-adımı: flag AÇIKSA v4+backup yönlerini üret + artifact yaz; KAPALI
    → no-op (canlı touche 3 saat içinde zemine düşer — kademeli, sessiz kırılma
    yok). Ucuz (sembol başına anlık hesap; per-bar döngü yok)."""
    if not enabled():
        return {"status": "DISABLED"}
    rep = analyze()
    _write(rep)
    return {"status": "OK", "symbols_scored": rep["symbols_scored"]}


__all__ = ["FLAG", "analyze", "artifact_path", "enabled", "run"]
