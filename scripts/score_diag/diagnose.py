"""ESKİ sistemin tanılaması: problem gerçekten var mı, bileşenler birbirini ne kadar tekrarlıyor,
korumalar kararı gerçekten değiştiriyor mu? (Hindsight YALNIZ tanılama; hiçbir üretim özelliği değil.)

Tüm tablolar markdown döndürür. ``splits`` ile hangi bölmelerin kullanıldığı açıkça seçilir:
tasarım kararları için ("train", "val"); TEST yalnız ``compare.final_report`` ile.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from scripts.score_diag import prep
from scripts.score_diag.metrics import signal_stats, spearman

BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]
BUCKET_LABELS = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]


def md(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_c(x) for x in r) + " |")
    return "\n".join(out)


def _c(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        if math.isnan(x):
            return "—"
        if math.isinf(x):
            return "∞"
        return f"{x:.3f}" if abs(x) < 10 else f"{x:.1f}"
    return str(x)


def use(df: pd.DataFrame, splits=("train", "val")) -> pd.DataFrame:
    return df[df["split"].isin(splits)]


# --------------------------------------------------------------------- konum tabloları

def location_table(df: pd.DataFrame, side: pd.Series, rp_col: str = "rp60", h: int = 10,
                   label: str = "ESKİ") -> str:
    """Giriş konumu (aralık yüzdeliği) × yön: pay, taban pay, isabet, ortalama getiri, KONTROL kenarı.

    Kontrol: aynı konum kovasındaki TÜM barların aynı yönde ortalama getirisi (sinyal olmasa da).
    Kenar = sinyal ortalaması − kontrol ortalaması (konum etkisinden arındırılmış)."""
    rows = []
    d = df.dropna(subset=[rp_col, f"f{h}"])
    base_cnt = len(d)
    for sname, sv in (("SHORT", -1), ("LONG", 1)):
        sig = d[side.loc[d.index] == sv]
        for (lo, hi), lab in zip(BUCKETS, BUCKET_LABELS, strict=True):
            in_b = d[(d[rp_col] >= lo) & (d[rp_col] < hi)]
            s_b = sig[(sig[rp_col] >= lo) & (sig[rp_col] < hi)]
            ctrl = (sv * in_b[f"f{h}"]).mean() * 100 if len(in_b) else float("nan")
            if len(s_b):
                r = sv * s_b[f"f{h}"]
                z = (r / (s_b["atrp"] * math.sqrt(h))).mean()
                rows.append([label, sname, lab, len(s_b), f"{len(s_b) / max(1, len(sig)):.1%}",
                             f"{len(in_b) / max(1, base_cnt):.1%}", f"{(r > 0).mean():.1%}",
                             r.mean() * 100, ctrl, r.mean() * 100 - ctrl, z])
            else:
                rows.append([label, sname, lab, 0, "0.0%", f"{len(in_b) / max(1, base_cnt):.1%}",
                             "—", float("nan"), ctrl, float("nan"), float("nan")])
    return md(["sistem", "yön", f"{rp_col} kovası", "n", "sinyal payı", "taban payı", "isabet",
               f"ort. getiri% (h{h})", "kontrol%", "kenar%", "ort. z"], rows)


def location_share_summary(df: pd.DataFrame, side: pd.Series, rp_col: str = "rp60") -> dict:
    """Short'ların alt %20'de, long'ların üst %20'de olma payı ve taban payları."""
    d = df.dropna(subset=[rp_col])
    sh, lg = d[side.loc[d.index] == -1], d[side.loc[d.index] == 1]
    return {
        "n_short": len(sh), "n_long": len(lg),
        "short_in_bottom20": float((sh[rp_col] < 0.2).mean()) if len(sh) else float("nan"),
        "base_bottom20": float((d[rp_col] < 0.2).mean()),
        "long_in_top20": float((lg[rp_col] >= 0.8).mean()) if len(lg) else float("nan"),
        "base_top20": float((d[rp_col] >= 0.8).mean()),
    }


def location_by_group(df: pd.DataFrame, side: pd.Series, group: str) -> str:
    rows = []
    for g, d in df.groupby(group):
        s = location_share_summary(d, side)
        rows.append([g, s["n_short"], s["short_in_bottom20"], s["base_bottom20"], s["n_long"],
                     s["long_in_top20"], s["base_top20"]])
    return md([group, "n short", "short alt%20 payı", "taban", "n long", "long üst%20 payı", "taban"], rows)


# --------------------------------------------------------------------- durum tablosu

def add_situation_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Bağlam + gösterge kaynaklı durum bayrakları (yön-bağımsız; yön ile kesişim tabloda)."""
    out = df.copy()

    def has(o, kind, direction, max_age):
        if not o:
            return False
        return any(e["kind"] == kind and e["direction"] == direction and e["age"] <= max_age
                   for e in o.get("events", []))

    objs = out["ctx_obj"]
    out["choch_bull"] = [has(o, "choch", "bullish", 5) for o in objs]
    out["choch_bear"] = [has(o, "choch", "bearish", 5) for o in objs]
    out["div_bull"] = [has(o, "divergence", "bullish", 10) for o in objs]
    out["div_bear"] = [has(o, "divergence", "bearish", 10) for o in objs]
    # tükenme vekili (exhaustion.py varsayılan eşikleriyle: RSI uç ∨ 5-bar getiri ≥ %5)
    ret5 = out.groupby(["series", "tf"])["close"].transform(lambda s: s / s.shift(5) - 1.0)
    # satırlar stride'lı olabilir; 5 SATIR geriye = stride*5 bar → yalnız stride 1 için doğru, aksi halde ctx'ten al
    ret5 = np.where(out["move5_atr"].notna(), out["move5_atr"] * out["atrp"], ret5)
    out["exh_dn"] = (out["rsi"] <= 30) | (ret5 <= -0.05)
    out["exh_up"] = (out["rsi"] >= 70) | (ret5 >= 0.05)
    return out


def situations(df: pd.DataFrame, side: pd.Series, h: int = 10, extra_v4: pd.Series | None = None,
               verdict: pd.Series | None = None) -> str:
    """İstenen özel durumlar: (durum, yön) için n, isabet, getiri, ayarlı z. ``verdict`` (YENİ) verilirse
    'YENİ korur%' ve 'WAIT'e dönen' sütunları eklenir."""
    d = df
    sh, lg = side == -1, side == 1
    conds = [
        ("RSI oversold (<30) short", sh & (d["rsi"] < 30)),
        ("RSI overbought (>70) long", lg & (d["rsi"] > 70)),
        ("exhaustion(aşağı) + short", sh & d["exh_dn"]),
        ("exhaustion(yukarı) + long", lg & d["exh_up"]),
        ("bullish CHoCH (≤5 bar) sonrası short", sh & d["choch_bull"]),
        ("bearish CHoCH (≤5 bar) sonrası long", lg & d["choch_bear"]),
        ("pozitif uyumsuzluk (≤10 bar) sonrası short", sh & d["div_bull"]),
        ("negatif uyumsuzluk (≤10 bar) sonrası long", lg & d["div_bear"]),
        ("aşırı EMA20/ATR uzaklığı (≥3 ATR) yönünde short", sh & (d["ext_ema20"] <= -3.0)),
        ("aşırı EMA20/ATR uzaklığı (≥3 ATR) yönünde long", lg & (d["ext_ema20"] >= 3.0)),
        ("Bollinger alt bant dışı short", sh & (d["bb_pctb"] < 0.0)),
        ("Bollinger üst bant dışı long", lg & (d["bb_pctb"] > 1.0)),
    ]
    if extra_v4 is not None:
        e = d["v4_elliott"].fillna(0.0)
        inv = d["zz_old_setup"].eq(True) & d["zz_old_valid"].eq(False) & (e != 0)
        val = d["zz_old_valid"].eq(True) & (e != 0)
        conds.append(("GEÇERSİZ 0-2 lensinin yönünde v4 işlemi", (extra_v4 != 0) & inv & (np.sign(e) == extra_v4)))
        conds.append(("geçerli 0-2 lensinin yönünde v4 işlemi", (extra_v4 != 0) & val & (np.sign(e) == extra_v4)))
    rows = []
    allsig = signal_stats(d, side, h, adjust=True)
    rows.append(["(tüm sinyaller)", allsig.get("n", 0), allsig.get("hit"), allsig.get("mean_pct"),
                 allsig.get("mean_z"), "—", "—"])
    for name, m in conds:
        sub = d[m.fillna(False)]
        sd = side.loc[sub.index]
        st = signal_stats(sub, sd, h, adjust=True)
        if st.get("n", 0) == 0:
            rows.append([name, 0, None, None, None, "—", "—"])
            continue
        kept = wait = "—"
        if verdict is not None:
            v = verdict.loc[sub.index]
            wait = f"{(v == 'wait').mean():.0%}"
            kept = f"{(v != 'wait').mean():.0%}"
        rows.append([name, st["n"], st["hit"], st["mean_pct"], st["mean_z"], kept, wait])
    return md(["durum", "n", "isabet", f"ort. getiri% (h{h}, sürüklenme-ayarlı)", "ort. z",
               "YENİ korur", "YENİ WAIT"], rows)


# --------------------------------------------------------------------- bileşen korelasyonu / ablation

def _clamp(x, lo=-1.0, hi=1.0):
    return np.minimum(hi, np.maximum(lo, x))


def add_components(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["l_rsi"] = _clamp((out["rsi"] - 50.0) / 50.0)
    out["l_macd"] = _clamp(out["macd_atr"] / 1.0)
    out["l_stack"] = out["stack"].map({"bullish": 1.0, "bearish": -1.0, "mixed": 0.0})
    # geriye dönük ROC10 (satır başına bar sayısı stride'a bağlı → close'tan bar-bazlı değil; ctx'ten türet)
    out["l_ext20"] = _clamp(out["ext_ema20"] / 3.0)
    out["l_move5"] = _clamp(out["move5_atr"] / 6.0)
    out["l_candle"] = _clamp(out["body_atr"] / 2.0)
    return out


def correlation_table(df: pd.DataFrame) -> str:
    cols = ["l_rsi", "l_macd", "l_stack", "l_ext20", "l_move5", "l_candle"]
    names = ["RSI", "MACD/ATR", "EMA dizilimi", "EMA20 uzaklığı(trend eğimi vekili)",
             "5-bar momentum", "mum gövdesi(candle momentum)"]
    extra = [c for c in ("v4_trend", "v4_rsi", "v4_yapi") if c in df.columns]
    d = df[cols + extra + ["core", "base"]].astype(float)
    pear = d.corr(method="pearson")
    rows = []
    for c, nm in zip(cols + extra + ["core", "base"], names + extra + ["momentum çekirdeği", "ESKİ skor (base)"], strict=False):
        rows.append([nm, *[pear.loc[c, k] for k in cols + extra + ["core", "base"]]])
    hdr = ["Pearson", "RSI", "MACD", "EMA-dizi", "EMA20-uzk", "mom5", "mum", *extra, "çekirdek", "base"]
    # benzersiz varyans: her lean'in diğerleri üzerine R²'si
    uniq = []
    mat = d[cols].dropna()
    for c in cols:
        others = [x for x in cols if x != c]
        X = np.column_stack([mat[others].to_numpy(), np.ones(len(mat))])
        y = mat[c].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        r2 = 1.0 - ((y - X @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        uniq.append([names[cols.index(c)], r2, 1.0 - r2])
    return md(hdr, rows) + "\n\n" + md(["bileşen", "diğerleriyle açıklanan R²", "benzersiz varyans"], uniq)


def _core(rsi, macd_atr, stack, drop=()):
    parts = []
    if "stack" not in drop and stack is not None:
        parts.append((stack, 0.40))
    if "rsi" not in drop and rsi is not None:
        parts.append((rsi, 0.30))
    if "macd" not in drop and macd_atr is not None:
        parts.append((macd_atr, 0.30))
    return parts


def core_score(df: pd.DataFrame, drop=(), rsi_mode: str = "linear") -> pd.Series:
    """Momentum çekirdeği (üretimdeki ağırlıklar 0.40/0.30/0.30; eksik bileşende normalize)."""
    rsi_l = df["l_rsi"]
    if rsi_mode == "band":     # 30/70'te doyan: (rsi-50)/20
        rsi_l = _clamp((df["rsi"] - 50.0) / 20.0)
    elif rsi_mode == "fold":   # 30/70'ten sonra tükenme: lean sönümlenir, 20/80'de 0
        a = (df["rsi"] - 50.0).abs()
        rsi_l = np.sign(df["rsi"] - 50.0) * np.where(a <= 20, a / 20.0, np.maximum(0.0, 1.0 - (a - 20.0) / 30.0))
    w = {"stack": (df["l_stack"], 0.40), "rsi": (rsi_l, 0.30), "macd": (df["l_macd"], 0.30)}
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for k, (lean, wt) in w.items():
        if k in drop or (k == "rsi" and rsi_mode == "none"):
            continue
        ok = lean.notna()
        num = num + np.where(ok, lean.fillna(0.0) * wt, 0.0)
        den = den + np.where(ok, wt, 0.0)
    return pd.Series(50.0 + np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0) * 50.0, index=df.index)


def apply_mults(core: pd.Series, df: pd.DataFrame, use=("gate", "chop", "exh")) -> pd.Series:
    mult = pd.Series(1.0, index=df.index)
    if "gate" in use:
        mult = mult * df["gate"].fillna(1.0)
    if "chop" in use:
        mult = mult * df["chop"].fillna(1.0)
    if "exh" in use:
        mult = mult * df["exh_mult"].fillna(1.0)
    return 50.0 + (core - 50.0) * mult


def score_quality(df: pd.DataFrame, score: pd.Series, h: int = 10) -> dict:
    """Skorun yön bilgisi: IC (Spearman), yön isabeti, eşik sinyallerinin sürüklenme-ayarlı z'si."""
    m = score.notna() & df[f"f{h}"].notna()
    s, r = score[m] - 50.0, df.loc[m, f"f{h}"] - df.loc[m, f"drift{h}"]
    ic = spearman(s, r) if m.sum() > 30 else float("nan")
    big = s.abs() >= 5
    acc = float((np.sign(s[big]) == np.sign(r[big])).mean()) if big.any() else float("nan")
    side = pd.Series(np.where(score >= 55, 1, np.where(score <= 45, -1, 0)), index=df.index)
    st = signal_stats(df, side, h, adjust=True)
    return {"ic": ic, "acc": acc, "n_sig": st.get("n", 0), "z": st.get("mean_z", float("nan")),
            "hit": st.get("hit", float("nan"))}


def ablation_table(df: pd.DataFrame, h: int = 10) -> str:
    d = add_components(df)
    full = apply_mults(core_score(d), d)
    variants = {
        "tam model (yeniden kurulmuş)": full,
        "RSI olmadan": apply_mults(core_score(d, drop=("rsi",)), d),
        "MACD olmadan": apply_mults(core_score(d, drop=("macd",)), d),
        "EMA dizilimi (trend) olmadan": apply_mults(core_score(d, drop=("stack",)), d),
        "konum/formasyon/hacim kapısı olmadan": apply_mults(core_score(d), d, use=("chop", "exh")),
        "chop koruması olmadan": apply_mults(core_score(d), d, use=("gate", "exh")),
        "tükenme koruması olmadan": apply_mults(core_score(d), d, use=("gate", "chop")),
        "hiç koruma yok (yalnız çekirdek)": core_score(d),
    }
    base_q = score_quality(d, variants["tam model (yeniden kurulmuş)"], h)
    rows = []
    for name, sc in variants.items():
        q = score_quality(d, sc, h)
        rows.append([name, q["n_sig"], q["ic"], q["ic"] - base_q["ic"], q["acc"], q["z"],
                     q["z"] - base_q["z"], q["hit"]])
    recon_ok = float((full - d["base"]).abs().le(1.0).mean())
    note = f"\nYeniden kurulan skor ile üretim skoru farkı ≤1 puan olan satır payı: {recon_ok:.1%} " \
           f"(reversion/yuvarlama dışı satırlar)."
    return md(["varyant", "n sinyal", "IC(h10)", "ΔIC", "yön isabeti", "ort. z (ayarlı)", "Δz", "isabet"], rows) + note


def rsi_table(df: pd.DataFrame, h: int = 10) -> str:
    d = add_components(df)
    rows = []
    for mode, label in (("linear", "lineer (üretim): (RSI−50)/50"), ("band", "bantlı: (RSI−50)/20, 30/70'te doyar"),
                        ("fold", "katlı: 30/70'ten sonra sönümlü, 20/80'de 0"), ("none", "RSI yok")):
        sc = core_score(d, rsi_mode=mode)
        q = score_quality(d, sc, h)
        rows.append([label, q["n_sig"], q["ic"], q["acc"], q["z"], q["hit"]])
    # uçlarda koşullu: RSI<25 iken ileri getiri (sürüklenme-ayarlı) — lineer RSI burada en çok 'bearish' der
    ext = []
    for lo, hi, lab in ((0, 20, "<20"), (20, 30, "20-30"), (30, 45, "30-45"), (45, 55, "45-55"),
                        (55, 70, "55-70"), (70, 80, "70-80"), (80, 101, ">80")):
        m = (d["rsi"] >= lo) & (d["rsi"] < hi) & d[f"f{h}"].notna()
        if m.sum() < 30:
            continue
        r = (d.loc[m, f"f{h}"] - d.loc[m, f"drift{h}"])
        ext.append([lab, int(m.sum()), r.mean() * 100, (r > 0).mean(), (r / (d.loc[m, "atrp"] * math.sqrt(h))).mean()])
    return (md(["RSI kullanımı (çekirdek)", "n sinyal", "IC", "yön isabeti", "ort. z", "isabet"], rows) + "\n\n"
            + md(["RSI bandı", "n", f"ileri getiri% (h{h}, ayarlı)", "yukarı olasılığı", "ort. z"], ext))


# --------------------------------------------------------------------- koruma etkisi

def _cls(score: pd.Series) -> pd.Series:
    return pd.Series(np.where(score >= 55, 1, np.where(score <= 45, -1, 0)), index=score.index)


def _size(score: pd.Series) -> pd.Series:
    """Konsensüs eşiklerinden taban boyut: güçlü (≥65/≤35) 1.5; normal (≥55/≤45) 1.0; yoksa 0."""
    return pd.Series(np.where((score >= 65) | (score <= 35), 1.5, np.where((score >= 55) | (score <= 45), 1.0, 0.0)),
                     index=score.index)


def guard_effect_table(df: pd.DataFrame) -> str:
    """Her korumanın kararı NE KADAR değiştirdiği: yalnız yön çevirme sayısıyla ölçülmez."""
    d = add_components(df)
    full = apply_mults(core_score(d), d)
    rows = []
    for name, drop in (("konum/formasyon/hacim kapısı", "gate"), ("chop (ADX) koruması", "chop"),
                       ("tükenme koruması", "exh"), ("TÜM korumalar", "all")):
        without = core_score(d) if drop == "all" else apply_mults(core_score(d), d, use=tuple(
            x for x in ("gate", "chop", "exh") if x != drop))
        cw, cf = _cls(without), _cls(full)
        active = (without - full).abs() > 0.05
        cand_before = cw != 0
        veto = cand_before & (cf == 0)
        flip = (cw * cf) < 0
        conf_b, conf_a = (without - 50).abs() / 50, (full - 50).abs() / 50
        rows.append([name, f"{active.mean():.1%}", float((without - full).abs()[active].mean()) if active.any() else float("nan"),
                     f"{(cw != cf).mean():.2%}", f"{veto.sum() / max(1, cand_before.sum()):.1%}",
                     f"{flip.sum() / max(1, cand_before.sum()):.2%}", float((conf_a - conf_b)[cand_before].mean()),
                     float((_size(full) - _size(without))[cand_before].mean())])
    return md(["koruma", "aktif satır", "ort. |Δskor| (aktifken)", "yön sınıfı değişti", "işlem VETO (WAIT)",
               "yön ÇEVİRME", "güven Δ (adaylarda)", "boyut Δ (adaylarda)"], rows)


# --------------------------------------------------------------------- 0-2 / v4

def feature_ic_table(df: pd.DataFrame, cand: pd.Series, h: int = 10) -> str:
    """Giriş-uzama özelliklerinin (işlem yönünde 'ne kadar zaten gitti') sonuçla Spearman IC'si:
    varlık sınıfı × bölme. Negatif IC = uzama kötü sonuç (ortalamaya dönüş, sahibin hipotezi);
    pozitif IC = uzama devam eder (momentum). Sınıflar arası TUTARLILIK tabloda görülür."""
    d = df[cand.loc[df.index] != 0].copy()
    side = cand.loc[d.index]
    d["y"] = side * (d[f"f{h}"] - d[f"drift{h}"]) / (d["atrp"] * math.sqrt(h))
    d = d[d["y"].notna()]
    side = side.loc[d.index]
    f = pd.DataFrame(index=d.index)
    f["EMA20 uzama"] = side * d["ext_ema20"]
    f["EMA50 uzama"] = side * d["ext_ema50"]
    f["5-bar hareket"] = side * d["move5_atr"]
    f["RSI uzama"] = side * (d["rsi_ctx"] - 50)
    f["Bollinger uzama"] = side * (d["bb_pctb"] - 0.5)
    f["aralık ucu (60)"] = -side * (d["rp60"] - 0.5)
    f["yönlü mum serisi"] = np.where(d["run_dir"] == side, d["run_len"], 0)
    f["hacim oranı"] = d["vol_ratio"]
    f["ATR genişlemesi"] = d["atr_ratio"]
    rows = []
    for cls in ["TÜMÜ", *sorted(d["asset_class"].unique())]:
        for sp in [x for x in ("train", "val", "test") if x in set(d["split"])]:
            m = (d["split"] == sp) if cls == "TÜMÜ" else ((d["split"] == sp) & (d["asset_class"] == cls))
            if m.sum() < 500:
                continue
            rows.append([cls, sp, int(m.sum()), *[spearman(f.loc[m, c], d.loc[m, "y"]) for c in f.columns]])
    return md(["sınıf", "bölme", "n", *f.columns], rows)


def zero_two_table(df: pd.DataFrame, h: int = 10) -> str:
    d = df[df["tf"].isin(["4h", "1d"]) & df["v4"].notna()].copy()
    d4 = d[d["tf"] == "4h"]
    rows = []
    for label, sub in (("4h", d4), ("1d", d[d["tf"] == "1d"])):
        if sub.empty:
            continue
        lens = sub["v4_elliott"].fillna(0.0) if "v4_elliott" in sub else pd.Series(0.0, index=sub.index)
        act = lens != 0
        invalid = act & sub["zz_old_valid"].eq(False)
        rows.append([label, len(sub), f"{act.mean():.1%}", f"{(invalid.sum() / max(1, act.sum())):.1%}"])
    q4 = score_quality(d4, d4["v4"], h) if len(d4) else {}
    q4c = score_quality(d4, d4["v4c"], h) if len(d4) else {}
    comp = [["v4 (eski 0-2 lensi)", q4.get("n_sig"), q4.get("ic"), q4.get("acc"), q4.get("z"), q4.get("hit")],
            ["v4c (kanonik 0-2)", q4c.get("n_sig"), q4c.get("ic"), q4c.get("acc"), q4c.get("z"), q4c.get("hit")]]
    return (md(["TF", "satır", "0-2 lensi aktif", "aktifken GEÇERSİZ setup payı"], rows) + "\n\n"
            + md(["4h v4 varyantı", "n sinyal", "IC", "yön isabeti", "ort. z (ayarlı)", "isabet"], comp))


def v4_ablation_table(df: pd.DataFrame, tf: str, h: int = 10) -> str:
    """v4 sabit ağırlıklarıyla leave-one-lens-out (4h veya 1d)."""
    from packages.scoring import tf_scoring_v4 as v4m
    d = df[(df["tf"] == tf) & df["v4"].notna()]
    w = v4m.WEIGHTS[tf]
    rows = []
    for variant in ("v4", "v4c"):
        lean_cols = {k: d.get(f"{variant}_{k}") for k in w}
        if any(v is None for v in lean_cols.values()):
            continue
        for drop in [None, *w]:
            tot = sum(wi for k, wi in w.items() if k != drop)
            s = sum(wi * lean_cols[k].fillna(0.0) for k, wi in w.items() if k != drop) / tot
            sc = 50.0 + 50.0 * np.where(s.abs() < v4m.MIN_CONVICTION, 0.0, s.clip(-1, 1))
            q = score_quality(d, pd.Series(sc, index=d.index), h)
            rows.append([variant, "tam" if drop is None else f"{drop} olmadan", q["n_sig"], q["ic"], q["acc"], q["z"], q["hit"]])
    return md(["varyant", "lens", "n sinyal", "IC", "yön isabeti", "ort. z (ayarlı)", "isabet"], rows)


__all__ = [
    "ablation_table",
    "add_components",
    "add_situation_flags",
    "correlation_table",
    "feature_ic_table",
    "guard_effect_table",
    "location_by_group",
    "location_share_summary",
    "location_table",
    "md",
    "prep",
    "rsi_table",
    "situations",
    "use",
    "v4_ablation_table",
    "zero_two_table",
]
