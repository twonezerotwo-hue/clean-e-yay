"""Sentinel/VIX: YÖNSEL makro eğilim ile STRES/TÜKENME bağlamını ayrı ölçer (kör ters-okuma YOK).

İki ayrı soru:
1. Yönsel eğilim — VIX yükseliyor/yüksek: orta vadeli risk-off, short lehine mi? (Sentinel'in
   bugünkü pro-siklik okuması: yüksek VIX → bearish.)
2. Stres/tükenme bağlamı — VIX AŞIRI sıçramışken (z60 ≥ 2) YENİ short girişinin zamanlama kalitesi
   düşüyor mu? (Panik tepesinde short'a girmek = dipte short.)

Her ikisi de yalnız TRAIN+VALIDATION'da ölçülür; sonuç destekliyorsa ayrı bir giriş-kalitesi
terimi olarak önerilir, Sentinel'in YÖN skoruna dokunulmaz.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.score_diag import data as D
from scripts.score_diag import diagnose as dg


def load_vix(cache: Path = D.DEFAULT_CACHE) -> pd.DataFrame:
    df = pd.read_csv(D.download_vix(cache))
    df["date"] = pd.to_datetime(df["DATE"], utc=True).dt.normalize()
    df = df.sort_values("date").reset_index(drop=True)
    c = df["CLOSE"]
    mean60, std60 = c.rolling(60).mean(), c.rolling(60).std()
    df["vix"] = c
    df["vix_z60"] = (c - mean60) / std60
    df["vix_ratio20"] = c / c.rolling(20).mean()
    df["vix_chg5"] = c / c.shift(5) - 1.0
    return df[["date", "vix", "vix_z60", "vix_ratio20", "vix_chg5"]]


def attach(df: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """VIX özelliklerini barlara bağla. Günlük barlar: aynı gün kapanışı (bar o gün kapanır).
    Gün-içi barlar: ÖNCEKİ gün kapanışı (aynı günün VIX kapanışı henüz bilinmiyor — look-ahead yok)."""
    out = df.copy()
    day = out["ts"].dt.normalize()
    out["_day"] = day
    daily = out["tf"] == "1d"
    v = vix.set_index("date")
    prev = vix.assign(date=vix["date"] + pd.Timedelta(days=1)).set_index("date")
    for col in ("vix", "vix_z60", "vix_ratio20", "vix_chg5"):
        same = v[col].reindex(day).to_numpy()
        # önceki işlem gününün değeri: en yakın önceki tarih
        before = prev[col].reindex(day, method="ffill").to_numpy()
        out[col] = np.where(daily, same, before)
    return out.drop(columns="_day")


def stress_table(df: pd.DataFrame, cand: pd.Series, h: int = 10,
                 classes=("equity", "index_etf", "oil_etf")) -> str:
    d = df[df["asset_class"].isin(classes) & df["vix_z60"].notna() & cand.loc[df.index].ne(0)]
    side = cand.loc[d.index]
    r = side * (d[f"f{h}"] - d[f"drift{h}"])
    z = r / (d["atrp"] * math.sqrt(h))
    buckets = [(-9, -1.0, "z<-1 (rahat)"), (-1.0, 0.0, "-1..0"), (0.0, 1.0, "0..1"),
               (1.0, 2.0, "1..2 (yükselen stres)"), (2.0, 9, "z≥2 (AŞIRI sıçrama)")]
    rows = []
    for sname, sv in (("SHORT", -1), ("LONG", 1)):
        for lo, hi, lab in buckets:
            m = (side == sv) & (d["vix_z60"] >= lo) & (d["vix_z60"] < hi) & r.notna()
            if m.sum() < 30:
                rows.append([sname, lab, int(m.sum()), None, None, None])
                continue
            rows.append([sname, lab, int(m.sum()), float((r[m] > 0).mean()), float(r[m].mean() * 100), float(z[m].mean())])
    # kesişim: aşırı stres + aralığın altında
    low = d["rp60"] < 0.2
    for sname, sv in (("SHORT", -1),):
        m = (side == sv) & (d["vix_z60"] >= 2.0) & low & r.notna()
        rows.append([sname, "z≥2 ∧ aralık alt %20", int(m.sum()), float((r[m] > 0).mean()) if m.sum() else None,
                     float(r[m].mean() * 100) if m.sum() else None, float(z[m].mean()) if m.sum() else None])
    return dg.md(["yön", "VIX z60 kovası", "n", "isabet", f"ort. getiri% (h{h}, ayarlı)", "ort. z"], rows)
