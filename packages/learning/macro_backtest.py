"""5y çok-rejim MAKRO backtest — kural #3 kapısı (Basamak-4, 2026-07-13).

İki aktivasyon kararının kanıt üreticisi (SALT-ANALİZ; canlı karara dokunmaz):
1. **fundamental_v3 (M8)**: v2 (Likidite+Rotasyon) vs v3 (yalnız Likidite) —
   hangisi ileri getiriyi daha iyi ayırıyor? (rejim başına separation)
2. **capital_flow ağırlıkları**: flow.DEFAULT_WEIGHTS'teki elle işaretlerin
   yerine 5y kanıt — sinyal başına IC (ileri risk-getirisiyle korelasyon) →
   ağırlık ÖNERİSİ (uygulamaz; owner kararı).

Dürüstlük kısıtları (raporda da yazar):
- Rejim etiketi PROXY: Likidite + Rotasyon(flow) + Kripto-momentum üçlüsünden
  (canlı 4-katmanın 5y kurulabilen kısmı; VIX arşivi ~2y → Risk İştahı katmanı
  YOK). Etiketler canlı rejimle birebir değil, rejim-AYRIMI için yeterli.
- Look-ahead YOK: gün t skorları yalnız ≤t kapanışından; getiri t→t+H.
- Takvim hizası: eksen SP500 işlem günleri; her seri son bilinen kapanışla
  forward-fill (denetimin "timestamp hizalanmıyor" bulgusunun cevabı).

Kullanım:  python -m packages.learning.macro_backtest [--horizon 10]
Artifact:  data/runtime/macro_backtest.json (MACRO_BACKTEST_PATH env override)
PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
import statistics as _st
from datetime import UTC, datetime
from pathlib import Path

from packages.data.providers.rotation import flow
from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

WARMUP = flow._MIN_HISTORY  # 127 gün — flow sinyalinin ihtiyacı
DEFAULT_HORIZON = 10        # ileri getiri penceresi (işlem günü)
_AXIS_KEY = "SPY"           # takvim ekseni: S&P 500 işlem günleri

# Rejim proxy eşikleri — canlı classifier ile aynı (65/50/35).
_REGIME_THRESHOLDS = ((65.0, "OFFENSIVE"), (50.0, "NEUTRAL"), (35.0, "DEFENSIVE"))

# İleri "risk-getirisi" sepeti: risk-on ekseninin hedefi (BTC + SPY ortalaması).
_RISK_TARGETS = ("BTC", "SPY")
# fundamental v2/v3 ayrımı bu hedeflerde ölçülür (işlem varlıkları).
_FUND_TARGETS = ("BTC", "GLD", "SPY")


# ── Veri hazırlığı ───────────────────────────────────────────────────────────

def align_daily(
    closes_by_key: dict[str, list[tuple[str, float]]],
    volumes_by_key: dict[str, list[tuple[str, float]]] | None = None,
) -> tuple[list[str], dict[str, list[float]], dict[str, list[float] | None]]:
    """(tarih, değer) listelerini SP500 işlem-günü eksenine hizalar (ffill).

    Ekseni olmayan gün atlanır; bir serinin o güne kadar HİÇ verisi yoksa seri
    o eksende None-ffill yerine baştan kırpılır (uydurma değer yok — çağıran
    WARMUP zaten kısa serileri süzer)."""
    axis_src = closes_by_key.get(_AXIS_KEY) or []
    dates = [d for d, _ in axis_src]
    aligned_c: dict[str, list[float]] = {}
    aligned_v: dict[str, list[float] | None] = {}
    vols = volumes_by_key or {}
    for key, series in closes_by_key.items():
        by_date = dict(series)
        v_by_date = dict(vols.get(key) or [])
        out_c: list[float] = []
        out_v: list[float] = []
        last: float | None = None
        last_v: float = 0.0
        sit = sorted(by_date)
        si = 0
        for d in dates:
            while si < len(sit) and sit[si] <= d:
                last = by_date[sit[si]]
                last_v = v_by_date.get(sit[si], 0.0)
                si += 1
            out_c.append(last if last is not None else float("nan"))
            out_v.append(last_v)
        aligned_c[key] = out_c
        aligned_v[key] = out_v if any(out_v) else None
    return dates, aligned_c, aligned_v


def _liquidity_score(dxy: float, us10y: float) -> float:
    """Canlı classifier'ın Likidite formülü (eğri bacağı hariç — US02Y arşivi yok)."""
    return max(0.0, min(100.0, 100.0 - (dxy - 100.0) * 2.0 - (us10y - 4.0) * 5.0))


def _appetite_score(vix: float) -> float:
    """Canlı classifier'ın Risk İştahı formülü (VIX → 0-100; düşük VIX = iştah).

    2026-07-13: VIX 5y backfill edildi → rejim proxy artık 4-katman (CRISIS
    ayrımı görünür). Formül canlı `_appetite_layer` ile BİREBİR (tek kaynak)."""
    return max(0.0, min(100.0, 100.0 - (vix - 12.0) * 4.0))


def _zscore(series: list[float], window: int = 252, min_n: int = 60) -> float | None:
    """Son değerin, son `window` değere göre z-skoru (rolling merkezleme)."""
    tail = [v for v in series[-window:] if v == v]  # NaN süz
    if len(tail) < min_n:
        return None
    sd = _st.pstdev(tail)
    if sd <= 0:
        return None
    return (tail[-1] - _st.mean(tail)) / sd


# ── Fundamental formül ADAYLARI (Basamak-4 revizyonu, 2026-07-13) ────────────
# Mevcut Likidite formülünün ampirik kusuru: mutlak seviyeye çapalı ve eğimleri
# zayıf → 5 yılda 1118/1118 gün ≥55 (hiç bearish olamıyor). Adaylar merkezi
# yapısal olarak düzeltir; katsayı UYDURMA yok (eşit-ağırlık eksenler), seçim
# 5y tezgâh kanıtıyla owner'ın. Hepsi 0-100, 50=nötr; veri yetersiz → None.

def cand_z(dxy: list[float], us10y: list[float]) -> float | None:
    """ADAY A — seviye yerine 1y z-skor: DXY ve faiz kendi son-yıl dağılımına
    göre yüksekse likidite sıkı (skor<50). Merkez yapısal olarak 50."""
    zd, zr = _zscore(dxy), _zscore(us10y)
    if zd is None or zr is None:
        return None
    return max(0.0, min(100.0, 50.0 - 20.0 * zd - 20.0 * zr))


def cand_mom(dxy: list[float], us10y: list[float]) -> float | None:
    """ADAY B — değişim-bazlı: DXY ve faiz vol-norm momentumu (yükseliyorsa
    sıkılaşıyor → risk-off). Canlı üretici `flow.liquidity_momentum_score`'a
    DELEGE eder (tek kaynak — canlı v4 = backtest'te ölçülen B birebir)."""
    return flow.liquidity_momentum_score(dxy, us10y)


def cand_credit(
    dxy: list[float], us10y: list[float],
    hyg: list[float] | None, lqd: list[float] | None,
) -> float | None:
    """ADAY C — B + kredi ekseni: HYG/LQD oran momentumu (kredi risk-iştahı;
    denetimin 'boşta duran güçlü girdi' dediği eksen). Üç eksen eşit ağırlık."""
    md = flow.vol_norm_momentum(dxy)
    mr = flow.vol_norm_momentum(us10y)
    if md is None or mr is None:
        return None
    axes = [-md, -mr]
    if hyg and lqd:
        mc = flow.credit_signal(hyg, lqd)
        if mc is not None:
            axes.append(mc)
    return max(0.0, min(100.0, 50.0 + 12.5 * sum(axes) / len(axes)))


CANDIDATE_KEYS = ("cand_z", "cand_mom", "cand_credit")


def fundamental_candidates(prefix: dict[str, list[float]]) -> dict[str, float | None]:
    dxy, us10y = prefix.get("DXY") or [], prefix.get("US10Y") or []
    return {
        "cand_z": cand_z(dxy, us10y),
        "cand_mom": cand_mom(dxy, us10y),
        "cand_credit": cand_credit(dxy, us10y, prefix.get("HYG"), prefix.get("LQD")),
    }


def score_distribution(rows: list[dict], key: str) -> dict:
    """Skor dağılımı — merkez düzeldi mi kanıtı: gün yüzdesi ≥55 / ≤45 / ara."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"n": 0}
    n = len(vals)
    return {
        "n": n, "mean": round(_st.mean(vals), 1),
        "pct_hi55": round(100.0 * sum(1 for v in vals if v >= 55) / n, 1),
        "pct_lo45": round(100.0 * sum(1 for v in vals if v <= 45) / n, 1),
    }


def _regime_label(avg: float) -> str:
    for thr, name in _REGIME_THRESHOLDS:
        if avg >= thr:
            return name
    return "CRISIS"


# ── Çekirdek yürüyüş (pure; look-ahead yok) ──────────────────────────────────

def walk(
    closes: dict[str, list[float]],
    volumes: dict[str, list[float] | None],
    dates: list[str],
    horizon: int = DEFAULT_HORIZON,
) -> list[dict]:
    """Gün gün: sinyaller + skorlar + rejim-proxy + ileri getiriler.

    Her satır bir gündür; skorlar yalnız ≤t verisinden (dilimleme prefix'le),
    `fwd_*` alanları t→t+H getirisi (son H gün satır üretmez)."""
    n = len(dates)
    rows: list[dict] = []
    for i in range(WARMUP, n - horizon):
        prefix_c = {k: v[: i + 1] for k, v in closes.items()}
        prefix_v = {k: (v[: i + 1] if v else None) for k, v in volumes.items()}
        signals = flow.build_signals(prefix_c, prefix_v)
        fscore = flow.flow_score(signals)
        dxy_s, us10_s = closes.get("DXY"), closes.get("US10Y")
        liq = (
            _liquidity_score(dxy_s[i], us10_s[i])
            if dxy_s and us10_s and dxy_s[i] == dxy_s[i] and us10_s[i] == us10_s[i]
            else None
        )
        if fscore is None or liq is None:
            continue
        # Kripto momentum proxy: BTC akış sinyali → 0-100 (canlı katmanın vekili).
        btc_sig = signals.get("BTC")
        crypto = None if btc_sig is None else max(0.0, min(100.0, 50.0 + 50.0 / 3.0 * btc_sig))
        # Risk İştahı katmanı (2026-07-13, VIX 5y backfill): canlı rejimin 4.
        # bacağı — CRISIS ayrımının asıl kaynağı. VIX yoksa (eski arşiv) atlanır.
        vix_s = closes.get("VIX")
        appetite = (
            _appetite_score(vix_s[i])
            if vix_s and i < len(vix_s) and vix_s[i] == vix_s[i]
            else None
        )
        # Rejim proxy artık canlı 4-katmanı yansıtır: Likidite + Rotasyon(flow) +
        # Kripto + Risk İştahı (hangi bacak varsa). VIX'li dönemde CRISIS görünür.
        layer_vals = [v for v in (liq, fscore, crypto, appetite) if v is not None]
        regime = _regime_label(sum(layer_vals) / len(layer_vals))
        fund_v2 = (liq + fscore) / 2.0
        fund_v3 = liq
        fwd: dict[str, float] = {}
        for key in set(_RISK_TARGETS) | set(_FUND_TARGETS):
            s = closes.get(key)
            if s and s[i] == s[i] and s[i] > 0 and s[i + horizon] == s[i + horizon]:
                fwd[key] = (s[i + horizon] - s[i]) / s[i] * 100.0
        if not all(k in fwd for k in _RISK_TARGETS):
            continue
        cands = fundamental_candidates(prefix_c)
        rows.append({
            "date": dates[i],
            "signals": signals,
            "flow_score": round(fscore, 2),
            "fund_v2": round(fund_v2, 2),
            "fund_v3": round(fund_v3, 2),
            **{k: (None if v is None else round(v, 2)) for k, v in cands.items()},
            "regime": regime,
            "fwd": {k: round(v, 3) for k, v in fwd.items()},
            "fwd_risk": round(sum(fwd[k] for k in _RISK_TARGETS) / len(_RISK_TARGETS), 3),
        })
    return rows


# ── Metrikler ────────────────────────────────────────────────────────────────

def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 20 or len(xs) != len(ys):
        return None
    try:
        sx, sy = _st.pstdev(xs), _st.pstdev(ys)
        if sx <= 0 or sy <= 0:
            return None
        mx, my = _st.mean(xs), _st.mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True)) / len(xs)
        return cov / (sx * sy)
    except (ValueError, ZeroDivisionError):
        return None


def separation(rows: list[dict], score_key: str, target: str,
               hi: float = 55.0, lo: float = 45.0) -> dict:
    """Skor≥hi günlerin ort. ileri getirisi − skor≤lo günlerinki (challenger
    karnesi separation'ının aynısı). n'ler şeffaf; <10 örnek → INSUFFICIENT."""
    hi_v = [r["fwd"][target] for r in rows if r[score_key] >= hi and target in r["fwd"]]
    lo_v = [r["fwd"][target] for r in rows if r[score_key] <= lo and target in r["fwd"]]
    if len(hi_v) < 10 or len(lo_v) < 10:
        return {"sep": None, "n_hi": len(hi_v), "n_lo": len(lo_v), "verdict": "INSUFFICIENT"}
    sep = _st.mean(hi_v) - _st.mean(lo_v)
    return {
        "sep": round(sep, 3), "n_hi": len(hi_v), "n_lo": len(lo_v),
        "hi_mean": round(_st.mean(hi_v), 3), "lo_mean": round(_st.mean(lo_v), 3),
        "verdict": "POSITIVE" if sep > 0 else "NEGATIVE",
    }


def separation_tercile(rows: list[dict], score_key: str, target: str) -> dict:
    """Dağılım-göreli separation: skorun ÜST üçte-biri vs ALT üçte-biri günlerin
    ileri getirisi. Sabit 55/45 bandından farkı: merkezi kaymış skorlar (örn.
    5 yıl boyunca hep >55 kalan Likidite) yine de kıyaslanabilir — 'skor
    YÜKSEKKEN mi iyi?' sorusunun banttan bağımsız cevabı."""
    vals = [(r[score_key], r["fwd"][target]) for r in rows
            if r.get(score_key) is not None and target in r["fwd"]]
    if len(vals) < 30:
        return {"sep": None, "n_hi": 0, "n_lo": 0, "verdict": "INSUFFICIENT"}
    vals.sort(key=lambda t: t[0])
    k = len(vals) // 3
    lo_v = [f for _, f in vals[:k]]
    hi_v = [f for _, f in vals[-k:]]
    sep = _st.mean(hi_v) - _st.mean(lo_v)
    return {
        "sep": round(sep, 3), "n_hi": len(hi_v), "n_lo": len(lo_v),
        "hi_mean": round(_st.mean(hi_v), 3), "lo_mean": round(_st.mean(lo_v), 3),
        "verdict": "POSITIVE" if sep > 0 else "NEGATIVE",
    }


def walk_forward(rows: list[dict], min_train_years: int = 2) -> dict:
    """Kanıt-ağırlıkların DÜRÜST testi: her test yılının ağırlıkları YALNIZ
    önceki yılların IC'sinden öğrenilir (in-sample zafer tuzağı yok, kural #3).
    Çıktı: yıl başına tercile-separation + elle-ağırlıkla yan yana."""
    years = sorted({r["date"][:4] for r in rows})
    out: dict[str, dict] = {}
    for y in years[min_train_years:]:
        train = [r for r in rows if r["date"][:4] < y]
        test = [r for r in rows if r["date"][:4] == y]
        if len(train) < 100 or len(test) < 30:
            out[y] = {"verdict": "INSUFFICIENT", "n_train": len(train), "n_test": len(test)}
            continue
        w = suggest_weights(signal_ic(train))
        scored = []
        for r in test:
            s = flow.flow_score(r["signals"], weights=w)
            if s is not None:
                scored.append({**r, "wf_score": s})
        out[y] = {
            "weights": w,
            "learned": separation_tercile(scored, "wf_score", "BTC"),
            "hand": separation_tercile(test, "flow_score", "BTC"),
            "n_train": len(train), "n_test": len(test),
        }
    return out


def signal_ic(rows: list[dict]) -> dict[str, dict]:
    """Sinyal başına IC: sinyal değeri ↔ ileri risk-getirisi korelasyonu
    (tümü + rejim başına). Ağırlık önerisinin ham kanıtı."""
    out: dict[str, dict] = {}
    for key in flow.SIGNAL_KEYS:
        sub = [(r["signals"][key], r["fwd_risk"], r["regime"]) for r in rows if key in r["signals"]]
        if not sub:
            out[key] = {"ic": None, "n": 0}
            continue
        entry: dict = {"ic": _corr([s for s, _, _ in sub], [f for _, f, _ in sub]), "n": len(sub)}
        for reg in ("OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"):
            rsub = [(s, f) for s, f, g in sub if g == reg]
            ic = _corr([s for s, _ in rsub], [f for _, f in rsub])
            entry[f"ic_{reg}"] = None if ic is None else round(ic, 4)
        entry["ic"] = None if entry["ic"] is None else round(entry["ic"], 4)
        out[key] = entry
    return out


def suggest_weights(ics: dict[str, dict], floor: float = 0.03) -> dict[str, float]:
    """IC → ağırlık ÖNERİSİ: işaret IC'den, büyüklük |IC|'nin en büyüğüne göre
    1.5'e ölçekli; |IC|<floor → 0 (gürültüye ağırlık verilmez). UYGULAMAZ."""
    vals = {k: (v.get("ic") or 0.0) for k, v in ics.items()}
    mx = max((abs(x) for x in vals.values()), default=0.0)
    if mx <= 0:
        return {k: 0.0 for k in vals}
    return {
        k: 0.0 if abs(x) < floor else round(1.5 * x / mx, 2)
        for k, x in vals.items()
    }


def per_year(rows: list[dict], score_key: str, target: str) -> dict[str, dict]:
    """Yıl başına separation — kural #3'ün '2 aylık zafer' tuzağına karşı."""
    out: dict[str, dict] = {}
    years = sorted({r["date"][:4] for r in rows})
    for y in years:
        out[y] = separation([r for r in rows if r["date"].startswith(y)], score_key, target)
    return out


def per_regime(rows: list[dict], score_key: str, target: str) -> dict[str, dict]:
    return {
        reg: separation([r for r in rows if r["regime"] == reg], score_key, target)
        for reg in ("OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS")
    }


# ── Rapor + artifact ─────────────────────────────────────────────────────────

def artifact_path() -> Path:
    return Path(os.environ.get("MACRO_BACKTEST_PATH", "data/runtime/macro_backtest.json"))


def analyze(rows: list[dict], horizon: int) -> dict:
    ics = signal_ic(rows)
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "params": {"horizon_days": horizon, "warmup": WARMUP, "rows": len(rows),
                   "date_from": rows[0]["date"] if rows else None,
                   "date_to": rows[-1]["date"] if rows else None},
        "notes": [
            "REJIM=PROXY (Likidite+Rotasyon+Kripto; VIX arsivi kisa, Risk Istahi yok)",
            "SALT-ANALIZ: canli karara/agirliga hicbir yazim yok",
        ],
        "signal_ic": ics,
        "suggested_flow_weights": suggest_weights(ics),
        "current_default_weights": dict(flow.DEFAULT_WEIGHTS),
        "flow_score": {
            "overall": separation(rows, "flow_score", "BTC"),
            "overall_tercile": separation_tercile(rows, "flow_score", "BTC"),
            "per_regime_btc": per_regime(rows, "flow_score", "BTC"),
            "per_year_btc": per_year(rows, "flow_score", "BTC"),
        },
        "walk_forward": walk_forward(rows),
        "fundamental_v2_vs_v3": {
            t: {
                "v2": {"overall": separation(rows, "fund_v2", t),
                       "tercile": separation_tercile(rows, "fund_v2", t),
                       "tercile_per_year": {
                           y: separation_tercile([r for r in rows if r["date"].startswith(y)], "fund_v2", t)
                           for y in sorted({r["date"][:4] for r in rows})
                       }},
                "v3": {"overall": separation(rows, "fund_v3", t),
                       "tercile": separation_tercile(rows, "fund_v3", t),
                       "tercile_per_year": {
                           y: separation_tercile([r for r in rows if r["date"].startswith(y)], "fund_v3", t)
                           for y in sorted({r["date"][:4] for r in rows})
                       }},
            }
            for t in _FUND_TARGETS
        },
        "fundamental_candidates": {
            key: {
                "distribution": score_distribution(rows, key),
                "targets": {
                    t: {
                        "tercile": separation_tercile(rows, key, t),
                        "per_year": {
                            y: (separation_tercile(
                                [r for r in rows if r["date"].startswith(y)], key, t,
                            ) or {}).get("sep")
                            for y in sorted({r["date"][:4] for r in rows})
                        },
                    }
                    for t in _FUND_TARGETS
                },
            }
            for key in CANDIDATE_KEYS
        },
        "fund_current_distribution": {
            "fund_v2": score_distribution(rows, "fund_v2"),
            "fund_v3": score_distribution(rows, "fund_v3"),
        },
        "regime_distribution": {
            reg: sum(1 for r in rows if r["regime"] == reg)
            for reg in ("OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS")
        },
    }
    return result


def load_archive_series() -> tuple[dict, dict]:
    """Bar arşivinden rotasyon evreni + US10Y günlük serileri (tarih, değer)."""
    from packages.data.providers.ohlcv import history
    keys = dict(ROTATION_SYMBOLS)
    keys["US10Y"] = "US10Y"
    keys["VIX"] = "VIX"  # Risk İştahı katmanı (rejim proxy 4. bacağı)
    closes: dict[str, list[tuple[str, float]]] = {}
    volumes: dict[str, list[tuple[str, float]]] = {}
    for key, symbol in keys.items():
        bars = history.load(symbol, "1d")
        closes[key] = [(b.ts.date().isoformat(), float(b.close)) for b in bars]
        volumes[key] = [(b.ts.date().isoformat(), float(b.volume or 0.0)) for b in bars]
    return closes, volumes


def run(horizon: int = DEFAULT_HORIZON) -> dict:
    closes_raw, volumes_raw = load_archive_series()
    dates, closes, volumes = align_daily(closes_raw, volumes_raw)
    rows = walk(closes, volumes, dates, horizon)
    result = analyze(rows, horizon)
    p = artifact_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _fmt_sep(s: dict) -> str:
    if s.get("sep") is None:
        return f"YETERSIZ (hi={s['n_hi']}/lo={s['n_lo']})"
    return f"{s['sep']:+.2f}pp (hi n={s['n_hi']} ort {s['hi_mean']:+.2f}% / lo n={s['n_lo']} ort {s['lo_mean']:+.2f}%) {s['verdict']}"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    args = ap.parse_args()
    # NOT: print'ler ASCII — Windows konsolu (cp1254) ok/uzun-tire karakterinde
    # patliyor (owner kurali #10'un konsol karsiligi).
    r = run(args.horizon)
    p = r["params"]
    print(f"MAKRO BACKTEST - {p['date_from']} -> {p['date_to']} ({p['rows']} gun, H={p['horizon_days']}g)")
    print(f"Rejim dagilimi (PROXY): {r['regime_distribution']}")
    print("\n-- capital_flow sinyal IC'leri (ileri risk-getirisi korelasyonu) --")
    for k, v in r["signal_ic"].items():
        print(f"  {k:7} ic={v.get('ic')}  n={v.get('n')}  "
              f"OFF={v.get('ic_OFFENSIVE')} NEU={v.get('ic_NEUTRAL')} DEF={v.get('ic_DEFENSIVE')} CRI={v.get('ic_CRISIS')}")
    print(f"\n  ONERILEN agirliklar (in-sample): {r['suggested_flow_weights']}")
    print(f"  MEVCUT (elle):                   {r['current_default_weights']}")
    print("\n-- flow_score -> BTC ileri getiri separation --")
    print(f"  genel (55/45): {_fmt_sep(r['flow_score']['overall'])}")
    print(f"  genel (tercile): {_fmt_sep(r['flow_score']['overall_tercile'])}")
    for reg, s in r["flow_score"]["per_regime_btc"].items():
        print(f"  {reg:10}: {_fmt_sep(s)}")
    print("\n-- WALK-FORWARD (yil oncesinden ogren, o yilda test; kural #3 durust hali) --")
    for y, wf in r["walk_forward"].items():
        if wf.get("verdict") == "INSUFFICIENT":
            print(f"  {y}: YETERSIZ (train={wf['n_train']} test={wf['n_test']})")
            continue
        print(f"  {y}: ogrenilmis {_fmt_sep(wf['learned'])}")
        print(f"  {'':6}elle       {_fmt_sep(wf['hand'])}")
    print("\n-- fundamental v2 (Likidite+Rotasyon) vs v3 (yalniz Likidite), tercile --")
    for t, blk in r["fundamental_v2_vs_v3"].items():
        print(f"  hedef {t}: v2 {_fmt_sep(blk['v2']['tercile'])}")
        print(f"  {'':8}  v3 {_fmt_sep(blk['v3']['tercile'])}")
    print("\n-- FORMUL ADAYLARI (A=z-skor, B=momentum, C=B+kredi ekseni) --")
    print(f"  mevcut dagilim: v2={r['fund_current_distribution']['fund_v2']} v3={r['fund_current_distribution']['fund_v3']}")
    for key, blk in r["fundamental_candidates"].items():
        print(f"  {key}: dagilim={blk['distribution']}")
        for t, tb in blk["targets"].items():
            yrs = " ".join(f"{y}:{s if s is not None else 'na'}" for y, s in tb["per_year"].items())
            print(f"    {t:4} genel {_fmt_sep(tb['tercile'])}  | yil-yil: {yrs}")
    print(f"\nArtifact: {artifact_path()}")
    print("NOT: rejim PROXY'dir; sonuclar M8/flow aktivasyon KANITI icindir, otomatik aksiyon yok.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
