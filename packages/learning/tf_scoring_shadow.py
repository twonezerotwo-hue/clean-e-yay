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
    """Her sembol için v2 gölge yön skoru. R2 çift-varyant kayıt:

    - `direction` (BİRİNCİL) = `regime_directed`: hava UP → 1d konuşur,
      DOWN → 4h konuşur; yön yalnız EDGE-kanıtlı sinyallerden (adaylar seyreltir
      — walk-forward kanıtı). Konuşan TF kanıtsızsa dürüstçe None.
    - `direction_blend_legacy` (KONTROL) = eski yumuşak harman (adaylar dahil)
      → D7 yarışı iki tasarımı gerçek veriyle kıyaslar.

    Salt-hesap; hiçbir yan etki yok."""
    from packages.data.providers.ohlcv import get_bars, history
    from packages.data.providers.rotation import engine as rotation_engine
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
    from packages.scoring import tf_scoring_v2 as v2
    from packages.scoring import tf_scoring_v3 as v3
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
    syms = symbols or sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD"})
    per_symbol: dict[str, dict] = {}
    # v3 makro-onayı: zaten çekilen 1d kapanışlarını rotasyon anahtarıyla
    # biriktir (ek ağ çağrısı YOK) → döngü sonunda TEK rotasyon skoru.
    closes_1d: dict[str, list[float]] = {}
    _sym_to_key = {val: key for key, val in ROTATION_SYMBOLS.items()}
    for sym in syms:
        try:
            tf_scores: dict[str, float] = {}          # EDGE-only (birincil yol)
            tf_scores_legacy: dict[str, float] = {}   # adaylar dahil (kontrol)
            tf_scores_v4: dict[str, float] = {}       # v4 owner-formülü (aday)
            convictions: dict[str, float] = {}
            drivers: dict[str, dict] = {}
            bar_marks: dict[str, dict] = {}           # R5 defteri için fiyat damgası
            regime_info: dict | None = None
            for tf in v2.DIRECTION_TFS:
                bars = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
                if len(bars) < _MIN_BARS:
                    continue
                # R5 (yarış defteri): konuşan TF'in son KAPANMIŞ barının ts+close'u —
                # gölge yönü hangi fiyatta üretildi. Additive; yön hesabını etkilemez.
                last = bars[-1]
                bar_marks[tf] = {"ts": last.ts.isoformat(), "close": round(last.close, 6)}
                leans = v2.collect_leans(tf, bars)
                # Birincil: yalnız kanıtlılar konuşur
                w_edge = v2.signal_weights(scorecard, tf, include_candidates=False)
                s_edge = v2.direction_score(tf, leans, w_edge)
                if s_edge is not None:
                    tf_scores[tf] = round(s_edge, 4)
                    drivers[tf] = {
                        name: {"lean": round(leans[name], 3), "weight": round(w, 4)}
                        for name, w in w_edge.items()
                        if w > 0.0 and name in leans
                    }
                # Kontrol: eski kural (adaylar dahil, kanıt-ağırlıklı harman)
                w_all = v2.signal_weights(scorecard, tf)
                s_all = v2.direction_score(tf, leans, w_all)
                if s_all is not None:
                    tf_scores_legacy[tf] = round(s_all, 4)
                    convictions[tf] = round(v2.conviction(w_all), 4)
                # v4 owner-formülü: leans REUSE + bölge (artifact) + kapılı-uyum
                s_v4 = v4.tf_direction(tf, v4.compute_leans(
                    tf, bars, zones_by_symbol.get(sym, []), leans))
                if s_v4 is not None:
                    tf_scores_v4[tf] = round(s_v4, 4)
                # Hava: 1d kapanışlarından (backtest tasarımıyla aynı)
                if tf == "1d":
                    closes = [b.close for b in bars]
                    rg = regime_gate.assess(closes)
                    if rg is not None:
                        regime_info = {"regime": rg.regime, "er": rg.er}
                    key = _sym_to_key.get(sym)
                    if key is not None:
                        closes_1d[key] = closes  # v3 makro girdisi (reuse)
            regime = (regime_info or {}).get("regime")
            primary = v2.regime_directed(tf_scores, regime)
            legacy = v2.blended_direction(tf_scores_legacy, convictions)
            d4 = v4.direction(tf_scores_v4, regime)
            per_symbol[sym] = {
                "direction": None if primary is None else round(primary, 4),
                "bias": _bias_label(primary),
                "regime": regime_info,
                "direction_blend_legacy": None if legacy is None else round(legacy, 4),
                "direction_v4": None if d4 is None else round(d4, 4),
                "tf_scores_v4": tf_scores_v4,
                "tf_scores": tf_scores,
                "tf_scores_legacy": tf_scores_legacy,
                "drivers": drivers,
                "bar_marks": bar_marks,  # R5 defteri: konuşan TF fiyat/ts damgası
                "status": "OK" if primary is not None else "no_evidence",
            }
        except Exception as exc:  # defensive — bir sembol diğerlerini düşürmesin
            per_symbol[sym] = {"status": f"ERROR:{type(exc).__name__}"}

    # ---- v3 (2026-07-12): v2 çekirdeği + makro-onay + bayat-karne kapısı ----
    # Makro hava TEK skorla (rotasyon risk-on) hesaplanır ve her sembole aynı
    # onay/kısma uygulanır; girdi = yukarıda zaten çekilen 1d kapanışlar.
    rotation_score: float | None = None
    try:
        rot = rotation_engine.compute(closes_1d)
        if rot.available:
            rotation_score = rot.score
    except Exception:
        rotation_score = None  # makro hesaplanamadı → v3 makro-katmanı nötr
    for row in per_symbol.values():
        if "tf_scores" not in row:
            continue
        try:
            d3 = v3.score(
                row["tf_scores"], (row.get("regime") or {}).get("regime"),
                rotation_score=rotation_score, scorecard=scorecard,
            )
            row["direction_v3"] = None if d3 is None else round(d3, 4)
        except Exception:
            row["direction_v3"] = None

    scored = sum(1 for v in per_symbol.values() if v.get("status") == "OK")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "tf_scoring_v2_shadow_r2",
        "scorecard_engine": scorecard.get("engine"),
        "scorecard_generated_at": scorecard.get("generated_at"),
        "symbols_scored": scored,
        "rotation_score": rotation_score,  # v3 makro girdisi (şeffaflık)
        "per_symbol": per_symbol,
        "note": (
            "İZOLE gölge (R2): BİRİNCİL yön = rejim-anahtarlı (UP→1d, DOWN→4h; "
            "yalnız EDGE-kanıtlılar konuşur). KONTROL = eski yumuşak harman. "
            "v3 = çekirdek + makro-onay + bayat-karne kapısı (2026-07-12). "
            "Canlı skora/karara/paper'a DOKUNMAZ (D7 yarış girdisi)."
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
