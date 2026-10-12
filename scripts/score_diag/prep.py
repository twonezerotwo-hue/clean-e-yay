"""Sinyal CSV'lerini yükle, bağlamı aç, kronolojik train/validation/test ata.

Bölme (her (seri, tf) için ayrı, ZAMANA GÖRE): ilk %50 TRAIN, sonraki %20 VALIDATION,
son %30 TEST. Sınır komşuluğunda ileri getiri örtüşmesi (en çok 20 bar) sızıntı olmasın
diye her iki sınırın EN FAZLA 20 barlık kısmı atılır (purge). Eşik/parametre seçimi
yalnız TRAIN+VALIDATION'da yapılır; TEST yalnız dondurulmuş config ile bir kez okunur
(``compare.final_report``).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20)
SPLITS = ("train", "val", "test")
PURGE = 20  # bar


def load(sig_dir: str | Path) -> pd.DataFrame:
    frames = []
    for p in sorted(Path(sig_dir).glob("*.csv.gz")):
        frames.append(pd.read_csv(p))
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values(["series", "tf", "i"]).reset_index(drop=True)
    return df


def assign_splits(df: pd.DataFrame, frac=(0.5, 0.2, 0.3)) -> pd.DataFrame:
    """Zamana göre bölme + sınırlarda purge. ``split`` = train|val|test|purge."""
    out = df.copy()
    out["split"] = "train"
    for _, g in out.groupby(["series", "tf"], sort=False):
        n = len(g)
        idx = g.index.to_numpy()
        a, b = int(n * frac[0]), int(n * (frac[0] + frac[1]))
        out.loc[idx[a:b], "split"] = "val"
        out.loc[idx[b:], "split"] = "test"
        # purge: sınırdan önceki PURGE satır (ileri getirileri sonraki bölmeye taşar)
        stride = max(1, int(np.median(np.diff(g["i"].to_numpy()))))
        k = max(1, math.ceil(PURGE / stride))
        out.loc[idx[max(0, a - k):a], "split"] = "purge"
        out.loc[idx[max(0, b - k):b], "split"] = "purge"
    return out


def parse_ctx(df: pd.DataFrame) -> pd.DataFrame:
    """ctx JSON'unu sütunlara aç; olaylar sözlük listesi olarak ``ctx_obj``'te kalır."""
    objs = [json.loads(s) if isinstance(s, str) else None for s in df["ctx"]]
    out = df.copy()
    out["ctx_obj"] = objs

    def col(fn):
        return [fn(o) if o else np.nan for o in objs]

    for n in ("20", "60", "120"):
        out[f"rp{n}"] = col(lambda o, n=n: (o.get("range_pos") or {}).get(n, np.nan))
    for k in ("ext_ema20", "ext_ema50", "ext_vwap", "bb_pctb", "move5_atr", "body_atr",
              "range_atr", "atr_ratio", "vol_ratio", "run_dir", "run_len"):
        out[k] = col(lambda o, k=k: np.nan if o.get(k) is None else o.get(k))
    out["rsi_ctx"] = col(lambda o: np.nan if o.get("rsi") is None else o.get("rsi"))
    return out


def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    """ATR-normalize getiri ve sürüklenme-ayarı. Sürüklenme YALNIZ TRAIN'den (seri bazlı)."""
    out = df.copy()
    out["atrp"] = out["atr"] / out["close"]
    for h in HORIZONS:
        out[f"drift{h}"] = np.nan
        for _, g in out.groupby(["series", "tf"], sort=False):
            tr = g[g["split"] == "train"][f"f{h}"].dropna()
            out.loc[g.index, f"drift{h}"] = float(tr.mean()) if len(tr) else 0.0
    return out


def prepare(sig_dir: str | Path) -> pd.DataFrame:
    df = load(sig_dir)
    df = assign_splits(df)
    df = parse_ctx(df)
    df = add_returns(df)
    return df


def candidates(df: pd.DataFrame, col: str = "base", long_min: float = 55.0,
               short_max: float = 45.0) -> pd.Series:
    """Konsensüs eşikleriyle ham niyet: +1 long, −1 short, 0 hold (eşikler thresholds_v1.0)."""
    s = df[col]
    return pd.Series(np.where(s >= long_min, 1, np.where(s <= short_max, -1, 0)), index=df.index)


def signed_returns(df: pd.DataFrame, side: pd.Series, h: int, adjust: bool = False) -> pd.Series:
    """İşlem yönünde getiri (long +, short −); ``adjust`` → TRAIN sürüklenmesi çıkarılmış."""
    f = df[f"f{h}"] - (df[f"drift{h}"] if adjust else 0.0)
    return side * f


def znorm(df: pd.DataFrame, r: pd.Series, h: int) -> pd.Series:
    """Getiriyi ATR% ve √h ile ölçekle (varlıklar/TF'ler arası karşılaştırılabilir)."""
    return r / (df["atrp"] * math.sqrt(h))
