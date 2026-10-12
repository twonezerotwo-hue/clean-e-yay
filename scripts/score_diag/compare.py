"""ESKİ vs YENİ karşılaştırma, parametre seçimi (TRAIN→VALIDATION) ve TEST'te tek seferlik doğrulama.

YENİ = ``entry_quality.assess`` (üretim kodu, aynı fonksiyon). Aday yön (ESKİ) değişmez:
YENİ yalnız {aday, WAIT} üretir ve boyutu ≤ 1.0 ile kısar — zıt yön ÜRETİLMEZ (``assert`` ile doğrulanır).

Seçim disiplini:
* Parametre ızgarası yalnız TRAIN'de taranır; en iyi adaylar VALIDATION'da elenir; TEST'e dokunulmaz.
* Hedef (J'): bloklanan sinyallerin sürüklenme-ayarlı z'sinin TÜM ESKİ sinyal ortalamasının ALTINDA
  olması (rastgele bloklama ≈ 0). Kısıt: sinyallerin en az %70'i korunur (işlem sayısı çökmesin).
* TEST yalnız ``final_report`` ile, dondurulmuş config dosyası varken, bir kez okunur.
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import asdict, replace
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

from packages.scoring import entry_quality
from scripts.score_diag import diagnose as dg
from scripts.score_diag import metrics

KEEP_MIN = 0.70
GRID = {
    "q_wait": [0.30, 0.40, 0.50, 0.60],
    "reversal_wait": [0.45, 0.60, 0.75, 1.01],       # 1.01 = dönüş riski kapısı kapalı
    "range_extreme": [0.15, 0.20, 0.30],
    "loc_floor": [0.2, 0.4, 0.6],
}


# --------------------------------------------------------------------- YENİ karar

def assess_rows(df: pd.DataFrame, cand: pd.Series, cfg: entry_quality.EntryQualityConfig) -> pd.DataFrame:
    """Aday satırlar için eq/rr/verdict/size (üretim ``assess``). Aday olmayanlar NaN/'none'."""
    n = len(df)
    eq = np.full(n, np.nan)
    rr = np.full(n, np.nan)
    verdict = np.array(["none"] * n, dtype=object)
    size = np.zeros(n)
    objs = df["ctx_obj"].to_numpy()
    cv = cand.to_numpy()
    for k in np.flatnonzero(cv != 0):
        side = "long" if cv[k] > 0 else "short"
        r = entry_quality.assess(side, objs[k], cfg)
        eq[k] = r["entry_quality"] if r["entry_quality"] is not None else np.nan
        rr[k] = r["reversal_risk"] if r["reversal_risk"] is not None else np.nan
        verdict[k] = r["verdict"]
        size[k] = r["size_factor"]
    return pd.DataFrame({"eq": eq, "rr": rr, "verdict": verdict, "size": size}, index=df.index)


def new_side(cand: pd.Series, rep: pd.DataFrame) -> pd.Series:
    out = cand.where(rep["verdict"].ne("wait"), 0)
    assert ((out == 0) | (out == cand)).all(), "YENİ sistem zıt yön üretemez"
    return out


# --------------------------------------------------------------------- ızgara

def _terms(df: pd.DataFrame, cand: pd.Series, base_cfg) -> dict[tuple, tuple[np.ndarray, np.ndarray]]:
    """(range_extreme, loc_floor) başına eq/rr dizileri (q_wait & reversal_wait'ten bağımsız)."""
    out = {}
    for re_, lf in itertools.product(GRID["range_extreme"], GRID["loc_floor"]):
        cfg = replace(base_cfg, range_extreme=re_, loc_floor=lf)
        rep = assess_rows(df, cand, cfg)
        out[(re_, lf)] = (rep["eq"].to_numpy(), rep["rr"].to_numpy())
    return out


def objective(df: pd.DataFrame, cand: pd.Series, keep: np.ndarray, h: int = 10) -> dict:
    """J' = −(bloklanan payı) × (bloklananların z ortalaması − tüm ESKİ sinyal z ortalaması),
    (seri,tf) grupları eşit ağırlıkla ortalanır. keep: aday satırlarda True=korunur."""
    sd = cand
    r = sd * (df[f"f{h}"] - df[f"drift{h}"])
    z = r / (df["atrp"] * math.sqrt(h))
    m = (sd != 0) & z.notna()
    d = pd.DataFrame({"g": df["series"] + "|" + df["tf"], "z": z.where(m), "keep": keep & m.to_numpy(), "m": m})
    d = d[d["m"]]
    js, ks = [], []
    for _, g in d.groupby("g"):
        if len(g) < 30:
            continue
        zbar = g["z"].mean()
        blocked = ~g["keep"]
        share = blocked.mean()
        zb = g.loc[blocked, "z"].mean() if blocked.any() else zbar
        js.append(-share * (zb - zbar))
        ks.append(1 - share)
    n_all, n_keep = int(d["m"].sum()), int(d["keep"].sum())
    return {"j": float(np.mean(js)) if js else float("nan"), "keep": n_keep / max(1, n_all),
            "groups": len(js), "groups_pos": int(sum(1 for x in js if x >= 0))}


def tune(df: pd.DataFrame, cand: pd.Series, base_cfg: entry_quality.EntryQualityConfig,
         top_k: int = 5) -> dict:
    """TRAIN'de ızgara; VALIDATION'da seçim. TEST'e dokunmaz."""
    tr, va = df[df["split"] == "train"], df[df["split"] == "val"]
    c_tr, c_va = cand.loc[tr.index], cand.loc[va.index]
    t_tr, t_va = _terms(tr, c_tr, base_cfg), _terms(va, c_va, base_cfg)
    rows = []
    for (re_, lf), (eq_tr, rr_tr) in t_tr.items():
        eq_va, rr_va = t_va[(re_, lf)]
        for qw, rw in itertools.product(GRID["q_wait"], GRID["reversal_wait"]):
            keep_tr = ~((rr_tr >= rw) | (eq_tr < qw))
            keep_va = ~((rr_va >= rw) | (eq_va < qw))
            keep_tr = np.where(np.isnan(eq_tr), True, keep_tr)
            keep_va = np.where(np.isnan(eq_va), True, keep_va)
            a, b = objective(tr, c_tr, keep_tr), objective(va, c_va, keep_va)
            rows.append({"q_wait": qw, "reversal_wait": rw, "range_extreme": re_, "loc_floor": lf,
                         "j_train": a["j"], "keep_train": a["keep"], "j_val": b["j"], "keep_val": b["keep"],
                         "groups_pos_val": b["groups_pos"], "groups_val": b["groups"]})
    res = pd.DataFrame(rows)
    ok = res[(res["keep_train"] >= KEEP_MIN) & (res["keep_val"] >= KEEP_MIN)]
    top = ok.sort_values("j_train", ascending=False).head(top_k)
    chosen = top[top["j_val"] > 0].sort_values("j_val", ascending=False).head(1)
    return {"grid": res, "top_train": top, "chosen": chosen}


def _keep_mask(df: pd.DataFrame, cand: pd.Series, cfg: entry_quality.EntryQualityConfig) -> np.ndarray:
    rep = assess_rows(df, cand, cfg)
    return (rep["verdict"] != "wait").to_numpy()


def new_ablation(df: pd.DataFrame, cand: pd.Series, cfg: entry_quality.EntryQualityConfig,
                 h: int = 10) -> str:
    """YENİ katmanın kendi bileşenleri için leave-one-out (marjinal katkı). J' tam modele göre Δ."""
    from copy import deepcopy
    full = objective(df, cand, _keep_mask(df, cand, cfg), h)
    rows = [["tam model", full["j"], 0.0, full["keep"]]]

    def _row(name: str, keep: np.ndarray) -> None:
        o = objective(df, cand, keep, h)
        rows.append([name, o["j"], o["j"] - full["j"], o["keep"]])

    for term in cfg.term_weights:
        w = dict(cfg.term_weights)
        w[term] = 0.0
        _row(f"{term} terimi olmadan", _keep_mask(df, cand, replace(cfg, term_weights=w)))
    _row("aralık konumu olmadan (loc=1)", _keep_mask(df, cand, replace(cfg, loc_floor=1.0)))
    kinds = sorted({e["kind"] for o in df["ctx_obj"] if o for e in o.get("events", [])})
    for kind in kinds:
        d2 = df.copy()
        d2["ctx_obj"] = [
            None if not o else {**o, "events": [e for e in o.get("events", []) if e["kind"] != kind]}
            for o in deepcopy(df["ctx_obj"].tolist())
        ]
        _row(f"{kind} olayı olmadan", _keep_mask(d2, cand, cfg))
    d3 = df.copy()
    d3["ctx_obj"] = [None if not o else {**o, "events": []} for o in df["ctx_obj"]]
    _row("hiç dönüş olayı olmadan (yalnız giriş kalitesi)", _keep_mask(d3, cand, cfg))
    d4 = df.copy()
    d4["ctx_obj"] = [None if not o else {**o, "pullback": None} for o in df["ctx_obj"]]
    _row("0-2 pullback bonusu olmadan", _keep_mask(d4, cand, cfg))
    return dg.md(["varyant", "J'", "ΔJ'", "korunan pay"], rows)


# --------------------------------------------------------------------- tablolar

def compare_signals(df: pd.DataFrame, cand: pd.Series, rep: pd.DataFrame, h: int = 10) -> dict:
    side_new = new_side(cand, rep)
    old = metrics.signal_stats(df, cand, h)
    old_adj = metrics.signal_stats(df, cand, h, adjust=True)
    new = metrics.signal_stats(df, side_new, h)
    new_adj = metrics.signal_stats(df, side_new, h, adjust=True)
    blocked = (cand != 0) & (side_new == 0)
    adj = (cand * (df[f"f{h}"] - df[f"drift{h}"]))
    good_old = (cand != 0) & (adj > 0)
    bl_prec = float((adj[blocked] < 0).mean()) if blocked.any() else float("nan")
    ret_good = float((side_new[good_old] != 0).mean()) if good_old.any() else float("nan")
    # trend yakalama: EMA dizilimi işlem yönünde olan 'iyi' sinyaller
    aligned = ((df["stack"] == "bullish") & (cand > 0)) | ((df["stack"] == "bearish") & (cand < 0))
    trend_good = good_old & aligned
    ret_trend = float((side_new[trend_good] != 0).mean()) if trend_good.any() else float("nan")
    avg_size = float(rep.loc[side_new != 0, "size"].mean()) if (side_new != 0).any() else float("nan")
    return {
        "old": old, "old_adj": old_adj, "new": new, "new_adj": new_adj,
        "n_long_old": int((cand > 0).sum()), "n_short_old": int((cand < 0).sum()),
        "n_long_new": int((side_new > 0).sum()), "n_short_new": int((side_new < 0).sum()),
        "n_wait_old": int((cand == 0).sum()), "n_wait_new": int((side_new == 0).sum()),
        "blocked": int(blocked.sum()), "blocked_precision": bl_prec, "retention_good": ret_good,
        "retention_trend_good": ret_trend, "avg_size_new": avg_size,
        "reduced": int(((rep["verdict"] == "reduce")).sum()),
    }


def overview_table(df: pd.DataFrame, cand: pd.Series, rep: pd.DataFrame, h: int = 10) -> str:
    c = compare_signals(df, cand, rep, h)
    rows = [
        ["LONG sayısı", c["n_long_old"], c["n_long_new"]],
        ["SHORT sayısı", c["n_short_old"], c["n_short_new"]],
        ["WAIT/hold sayısı", c["n_wait_old"], c["n_wait_new"]],
        [f"isabet (h{h})", c["old"].get("hit"), c["new"].get("hit")],
        [f"ort. getiri% (h{h})", c["old"].get("mean_pct"), c["new"].get("mean_pct")],
        [f"medyan getiri% (h{h})", c["old"].get("median_pct"), c["new"].get("median_pct")],
        ["ort. getiri% (sürüklenme-ayarlı)", c["old_adj"].get("mean_pct"), c["new_adj"].get("mean_pct")],
        ["ort. z (ayarlı)", c["old_adj"].get("mean_z"), c["new_adj"].get("mean_z")],
        ["profit factor (getiri)", c["old"].get("pf"), c["new"].get("pf")],
        ["MFE% (20 bar)", c["old"].get("mfe_pct"), c["new"].get("mfe_pct")],
        ["MAE% (20 bar)", c["old"].get("mae_pct"), c["new"].get("mae_pct")],
        ["ort. boyut çarpanı", 1.0, c["avg_size_new"]],
    ]
    extra = (f"\nBloklanan: {c['blocked']} (kesinlik: bloklananların kaybetme payı "
             f"{dg._c(c['blocked_precision'])}); ESKİ'nin 'iyi' sinyallerinin korunma payı "
             f"{dg._c(c['retention_good'])}; trend yönündeki 'iyi' sinyallerin korunma payı "
             f"{dg._c(c['retention_trend_good'])}; boyutu küçültülen: {c['reduced']}.")
    return dg.md(["ölçüt", "ESKİ", "YENİ"], rows) + extra


def breakdown(df: pd.DataFrame, cand: pd.Series, rep: pd.DataFrame, by: str, h: int = 10) -> str:
    rows = []
    for g, d in df.groupby(by):
        c = compare_signals(d, cand.loc[d.index], rep.loc[d.index], h)
        rows.append([g, c["n_long_old"] + c["n_short_old"], c["n_long_new"] + c["n_short_new"],
                     c["old_adj"].get("mean_z"), c["new_adj"].get("mean_z"), c["old"].get("hit"),
                     c["new"].get("hit"), c["blocked_precision"], c["retention_good"]])
    return dg.md([by, "n ESKİ", "n YENİ", "z ESKİ(ay.)", "z YENİ(ay.)", "isabet ESKİ", "isabet YENİ",
                  "bloklama kesinliği", "iyi sinyal korunma"], rows)


def confidence_calibration(df: pd.DataFrame, cand: pd.Series, rep: pd.DataFrame, h: int = 10) -> str:
    conf = (df["base"] - 50.0).abs() / 50.0
    kept = new_side(cand, rep) != 0
    adj = cand * (df[f"f{h}"] - df[f"drift{h}"])
    bins = [0.1, 0.2, 0.3, 0.4, 0.6, 1.01]
    rows = []
    for lo, hi in pairwise(bins):
        m = (cand != 0) & (conf >= lo) & (conf < hi) & adj.notna()
        if m.sum() < 30:
            continue
        rows.append([f"{lo:.1f}-{min(hi, 1.0):.1f}", int(m.sum()), float((adj[m] > 0).mean()),
                     int((m & kept).sum()), float((adj[m & kept] > 0).mean()) if (m & kept).any() else float("nan")])
    ics = {}
    for name, mm in (("ESKİ", cand != 0), ("YENİ (korunan)", kept)):
        ics[name] = metrics.spearman(conf[mm & adj.notna()], (adj[mm & adj.notna()] > 0).astype(float))
    return (dg.md(["güven kovası (|skor−50|/50)", "n ESKİ", "isabet ESKİ", "n YENİ", "isabet YENİ"], rows)
            + f"\nGüven↔isabet Spearman: ESKİ {dg._c(ics['ESKİ'])}, YENİ {dg._c(ics['YENİ (korunan)'])}")


# --------------------------------------------------------------------- dönüm noktası tepkisi (hindsight: yalnız tanılama)

def turning_points(df: pd.DataFrame, win: int = 10, min_move_atr: float = 4.0) -> pd.DataFrame:
    """Hindsight dip/tepe (YALNIZ ölçüm): ±win satır penceresinin ekstremi ve sonraki win satırda
    ≥ min_move_atr x ATR ters hareket. Üretim özelliği DEĞİL — gelecek barlarla tanımlıdır."""
    out = []
    for (s, tf), g in df.groupby(["series", "tf"], sort=False):
        g = g.reset_index()
        c = g["close"].to_numpy()
        a = (g["atr"].to_numpy())
        n = len(g)
        for k in range(win, n - win):
            seg = c[k - win:k + win + 1]
            if c[k] == seg.min() and (c[k + 1:k + win + 1].max() - c[k]) >= min_move_atr * a[k]:
                out.append((g.loc[k, "index"], s, tf, "bottom"))
            elif c[k] == seg.max() and (c[k] - c[k + 1:k + win + 1].min()) >= min_move_atr * a[k]:
                out.append((g.loc[k, "index"], s, tf, "top"))
    return pd.DataFrame(out, columns=["idx", "series", "tf", "kind"])


def reversal_reaction(df: pd.DataFrame, cand: pd.Series, side_new: pd.Series, tp: pd.DataFrame,
                      lookahead: int = 8) -> str:
    """Dipte açık SHORT / tepede açık LONG adayları için: (a) dönüm barındaki durum,
    (b) 'tepki süresi' = dönümden sonra adayın bitmesine (ESKİ: yön sınıfı değişince; YENİ: WAIT veya
    değişince) kaç SATIR geçti (medyan). Hindsight yalnız tanılama."""
    pos = {ix: p for p, ix in enumerate(df.index)}
    rows = []
    for kind, bad_side in (("bottom", -1), ("top", 1)):
        t = tp[tp["kind"] == kind]
        at_old = at_new = 0
        n = 0
        d_old, d_new = [], []
        for ix, s, tf in zip(t["idx"], t["series"], t["tf"], strict=True):
            if ix not in pos:
                continue
            p = pos[ix]
            n += 1
            at_old += int(cand.iloc[p] == bad_side)
            at_new += int(side_new.iloc[p] == bad_side)
            for arr, dst in ((cand, d_old), (side_new, d_new)):
                if arr.iloc[p] != bad_side:
                    dst.append(0)
                    continue
                k = 0
                while p + k < len(df) and k <= lookahead * 4 and arr.iloc[p + k] == bad_side \
                        and df.iloc[p + k]["series"] == s and df.iloc[p + k]["tf"] == tf:
                    k += 1
                dst.append(k)
        rows.append([kind, n, f"{at_old / max(1, n):.1%}", f"{at_new / max(1, n):.1%}",
                     float(np.median(d_old)) if d_old else float("nan"),
                     float(np.median(d_new)) if d_new else float("nan"),
                     float(np.mean(d_old)) if d_old else float("nan"),
                     float(np.mean(d_new)) if d_new else float("nan")])
    return dg.md(["dönüm", "n", "ters yönde açık (ESKİ)", "ters yönde açık (YENİ)",
                  "medyan satır ESKİ", "medyan satır YENİ", "ort. ESKİ", "ort. YENİ"], rows)


# --------------------------------------------------------------------- yürütme backtesti

def exec_frame(df: pd.DataFrame, side: pd.Series, size: pd.Series, splits: tuple[str, ...]) -> pd.DataFrame:
    keep = df["split"].isin(splits)
    f = pd.DataFrame({"series": df["series"], "tf": df["tf"], "asset_class": df["asset_class"],
                      "i": df["i"], "atr": df["atr"], "side": side, "size": size, "split": df["split"]})
    return f[keep]


def run_exec(df: pd.DataFrame, side: pd.Series, size: pd.Series, uni: dict, splits: tuple[str, ...],
             cost_mult: float = 1.0) -> pd.DataFrame:
    fr = exec_frame(df, side, size, splits)
    all_tr = []
    for (s, tf), g in fr.groupby(["series", "tf"], sort=False):
        series, bars = uni[(s, tf)]
        tr = metrics.simulate(bars, g[["i", "side", "size", "atr"]], tf, s, series.asset_class, cost_mult)
        all_tr.extend(tr)
    return pd.DataFrame(all_tr)


def exec_table(trades_old: pd.DataFrame, trades_new: pd.DataFrame, by: str | None = None) -> str:
    keys = ["n", "win_rate", "avg_r_net", "median_r_net", "profit_factor", "total_r", "max_dd_r",
            "sharpe_m", "sortino_m", "avg_bars", "avg_mfe_r", "avg_mae_r", "fee_drag_r", "long_n", "short_n"]
    names = ["işlem", "isabet", "ort. R(net)", "medyan R", "PF", "toplam R", "maks. DD(R)", "Sharpe(ay)",
             "Sortino(ay)", "ort. bar", "MFE R", "MAE R", "ücret R", "long", "short"]
    rows = []
    groups = [("tümü", None)]
    if by:
        vals = sorted(set(trades_old[by]) | set(trades_new[by])) if not trades_old.empty else []
        groups = [(v, v) for v in vals]
    for label, v in groups:
        for sysname, tr in (("ESKİ", trades_old), ("YENİ", trades_new)):
            sub = tr if v is None else tr[tr[by] == v]
            m = metrics.portfolio_metrics(sub)
            rows.append([label, sysname, *metrics.fmt(m, keys)])
    return dg.md(["grup", "sistem", *names], rows)


# --------------------------------------------------------------------- kabul ölçütleri

def acceptance(df: pd.DataFrame, cand: pd.Series, rep: pd.DataFrame, trades_old: pd.DataFrame,
               trades_new: pd.DataFrame, h: int = 10) -> list[dict]:
    """Önceden kayıtlı kabul ölçütleri (sonuca bakmadan yazıldı). Her biri {ad, geçti, değer}."""
    c = compare_signals(df, cand, rep, h)
    mo, mn = metrics.portfolio_metrics(trades_old), metrics.portfolio_metrics(trades_new)
    sn = new_side(cand, rep)
    # grup tutarlılığı
    pos = tot = 0
    for _, g in df.groupby(["series", "tf"]):
        cg = cand.loc[g.index]
        if (cg != 0).sum() < 30:
            continue
        keep = (sn.loc[g.index] != 0).to_numpy()
        j = objective(g, cg, keep, h)
        tot += 1
        pos += int(j["j"] >= 0)
    # konum payı
    s_old = dg.location_share_summary(df, cand)
    s_new = dg.location_share_summary(df, sn)
    items = [
        ("1 Beklenti (ort. R net/işlem) kötüleşmedi", mn.get("avg_r_net", float("nan")) >= mo.get("avg_r_net", float("nan")) - 1e-9,
         f"ESKİ {dg._c(mo.get('avg_r_net'))} → YENİ {dg._c(mn.get('avg_r_net'))}"),
        ("2 Maks. drawdown (R) %5'ten fazla kötüleşmedi", mn.get("max_dd_r", 0) <= mo.get("max_dd_r", 0) * 1.05 + 1e-9,
         f"ESKİ {dg._c(mo.get('max_dd_r'))} → YENİ {dg._c(mn.get('max_dd_r'))}"),
        ("3 Korunan sinyallerin z'si ≥ tüm ESKİ sinyaller", c["new_adj"].get("mean_z", -9) >= c["old_adj"].get("mean_z", 9),
         f"{dg._c(c['old_adj'].get('mean_z'))} → {dg._c(c['new_adj'].get('mean_z'))}"),
        ("4 Trend yönündeki 'iyi' sinyallerin ≥%85'i korundu", (c["retention_trend_good"] or 0) >= 0.85,
         dg._c(c["retention_trend_good"])),
        ("5 İşlem sayısı ESKİ'nin ≥%60'ı (yürütme)", mn.get("n", 0) >= 0.6 * mo.get("n", 1),
         f"{mn.get('n', 0)}/{mo.get('n', 0)}"),
        ("6 Zıt yön üretilmedi", bool(((sn == 0) | (sn == cand)).all()), "yapısal"),
        ("7 Uçta açılan short/long payı azaldı", (s_new["short_in_bottom20"] <= s_old["short_in_bottom20"] + 1e-9)
         and (s_new["long_in_top20"] <= s_old["long_in_top20"] + 1e-9),
         f"short alt20 {dg._c(s_old['short_in_bottom20'])}→{dg._c(s_new['short_in_bottom20'])}; "
         f"long üst20 {dg._c(s_old['long_in_top20'])}→{dg._c(s_new['long_in_top20'])}"),
        ("8 Bloklama kesinliği > %50 (bloklananlar kaybeden)", (c["blocked_precision"] or 0) > 0.5,
         dg._c(c["blocked_precision"])),
        ("9 Grupların ≥%60'ında Δ ≥ 0 (tutarlılık)", tot > 0 and pos / tot >= 0.6, f"{pos}/{tot}"),
    ]
    return [{"ad": a, "gecti": bool(b), "deger": v} for a, b, v in items]


def acceptance_md(items: list[dict]) -> str:
    return dg.md(["kabul ölçütü", "sonuç", "değer"], [[i["ad"], "GEÇTİ" if i["gecti"] else "KALDI", i["deger"]] for i in items])


# --------------------------------------------------------------------- TEST (tek seferlik)

def freeze(cfg: entry_quality.EntryQualityConfig, path: Path, meta: dict) -> str:
    payload = {"config": asdict(cfg), "meta": meta}
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=list), encoding="utf-8")
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_frozen(path: Path) -> entry_quality.EntryQualityConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))["config"]
    base = entry_quality.EntryQualityConfig()
    kw = {}
    for k, v in raw.items():
        d = getattr(base, k)
        kw[k] = tuple(v) if isinstance(d, tuple) else v
    return entry_quality.EntryQualityConfig(**kw)
