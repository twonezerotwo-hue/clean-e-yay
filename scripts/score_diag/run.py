"""Skor tanılama düzeneği CLI'ı.

    python -m scripts.score_diag.run fetch                       # Lean örnek verisini indir
    python -m scripts.score_diag.run extract --out OUT           # bar-bar sinyaller (4 çekirdekte dakikalar-onlarca dakika)
    python -m scripts.score_diag.run extract --out OUT --bar-history data/runtime/bar_history   # KENDİ arşivinde
    python -m scripts.score_diag.run diagnose --sig OUT --out R  # ESKİ sistem tanılaması (train+val)
    python -m scripts.score_diag.run tune --sig OUT --out R      # ızgara: TRAIN tara, VALIDATION seç, config'i DONDUR
    python -m scripts.score_diag.run validate --sig OUT --out R  # VALIDATION: ESKİ vs YENİ (sinyal + yürütme)
    python -m scripts.score_diag.run final --sig OUT --out R     # TEST: dondurulmuş config ile TEK SEFER

TEST disiplini: ``final`` yalnız ``R/frozen_config.json`` varken çalışır ve ``R/test_run.lock``
yazar; kilit varken ikinci kez çalışmayı reddeder (``--force`` bilinçli geçersiz kılma ve
log'a düşer). Böylece TEST üzerinde eşik/model ayarı yapılmadığı denetlenebilir.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from packages.scoring import entry_quality
from scripts.score_diag import compare as cp
from scripts.score_diag import data as D
from scripts.score_diag import diagnose as dg
from scripts.score_diag import prep, stress


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"yazıldı: {path}")


def cmd_fetch(a) -> None:
    paths = D.download(Path(a.cache))
    print(f"{len(paths)} dosya hazır → {a.cache}")


def cmd_extract(a) -> None:
    from scripts.score_diag import signals
    signals.run_all(a.cache, a.out, a.workers, a.only, a.bar_history)


def _uni(a):
    if a.bar_history:
        return D.bar_history_universe(Path(a.bar_history))
    return D.universe(Path(a.cache))


def _load(a):
    df = prep.prepare(a.sig)
    df = dg.add_situation_flags(df)
    df = dg.add_components(df)
    return df


def cmd_diagnose(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = _load(a)
    d = dg.use(df, ("train", "val"))
    cand = prep.candidates(d, "base")
    parts = ["# ESKİ sistem tanılaması (TRAIN+VALIDATION; TEST'e dokunulmadı)\n"]
    parts.append("## Veri\n" + dg.md(["seri", "tf", "satır", "ilk", "son"], [
        [s, tf, len(g), str(g["ts"].min().date()), str(g["ts"].max().date())]
        for (s, tf), g in d.groupby(["series", "tf"])]))
    parts.append("\n## Konum yanlılığı — ESKİ taban motor (60-bar aralık yüzdeliği)\n" + dg.location_table(d, cand))
    parts.append("\n### Özet: short'ların alt %20'de, long'ların üst %20'de olma payı\n"
                 + dg.md(["", "short alt%20", "taban", "long üst%20", "taban"], [[
                     "tümü", *[dg.location_share_summary(d, cand)[k] for k in
                               ("short_in_bottom20", "base_bottom20", "long_in_top20", "base_top20")]]]))
    parts.append("\n### TF kırılımı\n" + dg.location_by_group(d, cand, "tf"))
    parts.append("\n### Varlık sınıfı kırılımı\n" + dg.location_by_group(d, cand, "asset_class"))
    parts.append("\n## Özel durumlar\n" + dg.situations(d, cand))
    parts.append("\n## Giriş-uzama özelliklerinin sonuçla ilişkisi (IC; varlık sınıfı × bölme)\n" + dg.feature_ic_table(d, cand))
    parts.append("\n## Sentinel/VIX: stres bağlamı (yönsel eğilimden AYRI)\n"
                 + stress.stress_table(stress.attach(d, stress.load_vix(Path(a.cache))), cand))
    parts.append("\n## Bileşen korelasyonu\n" + dg.correlation_table(d))
    parts.append("\n## Ablation (leave-one-component-out)\n" + dg.ablation_table(d))
    parts.append("\n## RSI kullanımı\n" + dg.rsi_table(d))
    parts.append("\n## Koruma etkisi (yalnız yön çevirme değil)\n" + dg.guard_effect_table(d))
    parts.append("\n## 0-2 lensi\n" + dg.zero_two_table(d))
    for tf in ("4h", "1d"):
        parts.append(f"\n### v4 leave-one-lens-out ({tf})\n" + dg.v4_ablation_table(d, tf))
    _write(out / "01_diagnostics.md", "\n".join(parts))


def cmd_tune(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = _load(a)
    df = df[df["split"].isin(["train", "val"])]
    cand = prep.candidates(df, "base")
    base_cfg = entry_quality.EntryQualityConfig(mode="active")
    t0 = time.time()
    res = cp.tune(df, cand, base_cfg)
    print(f"ızgara {time.time() - t0:.0f}s")
    grid = res["grid"]
    grid.to_csv(out / "tuning_grid.csv", index=False)
    parts = ["# Parametre seçimi (TRAIN tara → VALIDATION seç)\n",
             f"Kısıt: korunan sinyal payı ≥ {cp.KEEP_MIN:.0%} (train ve val). Hedef J' = −(bloklanan payı)×(bloklananların z'si − tüm sinyal z'si), "
             "grup (seri,tf) eşit ağırlık; z sürüklenme-ayarlı.\n",
             "## TRAIN'de en iyi 5\n" + dg.md(list(res["top_train"].columns),
                                              res["top_train"].round(4).values.tolist())]
    if res["chosen"].empty:
        parts.append("\n**VALIDATION'da J' > 0 olan aday YOK → dondurulacak config yok (YENİ sistem kabul edilmez).**")
        _write(out / "02_tuning.md", "\n".join(parts))
        return
    ch = res["chosen"].iloc[0]
    cfg = entry_quality.EntryQualityConfig(
        mode="shadow", q_wait=float(ch["q_wait"]), reversal_wait=float(ch["reversal_wait"]),
        range_extreme=float(ch["range_extreme"]), loc_floor=float(ch["loc_floor"]))
    h = cp.freeze(cfg, out / "frozen_config.json", {"chosen": ch.to_dict(), "keep_min": cp.KEEP_MIN})
    parts.append(f"\n## Seçilen (VALIDATION J' en iyi, TRAIN J'>0): sha256[:16]={h}\n" +
                 dg.md(list(res["chosen"].columns), res["chosen"].round(4).values.tolist()))
    _write(out / "02_tuning.md", "\n".join(parts))


def _compare_split(df, cfg, uni, splits, label, cache=D.DEFAULT_CACHE) -> tuple[str, list[dict]]:
    d = df[df["split"].isin(splits)]
    cand = prep.candidates(d, "base")
    rep = cp.assess_rows(d, cand, cfg)
    sn = cp.new_side(cand, rep)
    parts = [f"## {label}: sinyal düzeyi (h10)\n" + cp.overview_table(d, cand, rep)]
    parts.append("\n### TF kırılımı\n" + cp.breakdown(d, cand, rep, "tf"))
    parts.append("\n### Varlık sınıfı kırılımı\n" + cp.breakdown(d, cand, rep, "asset_class"))
    parts.append("\n### Enstrüman kırılımı\n" + cp.breakdown(d, cand, rep, "series"))
    parts.append("\n### Piyasa rejimi (üretim sınıflandırıcısı)\n" + cp.breakdown(d.assign(market_regime=d["market_regime"].fillna("UNKNOWN")), cand, rep, "market_regime"))
    parts.append("\n### EMA dizilimi (trend durumu)\n" + cp.breakdown(d.assign(stack=d["stack"].fillna("na")), cand, rep, "stack"))
    for nm, sv in (("ESKİ", cand), ("YENİ", sn)):
        parts.append(f"\n### Giriş konumu — {nm}\n" + dg.location_table(d, sv, label=nm))
    parts.append("\n### Özel durumlar (ESKİ sinyaller; YENİ'nin kararı)\n" + dg.situations(d, cand, verdict=rep["verdict"]))
    parts.append("\n### Güven kalibrasyonu\n" + cp.confidence_calibration(d, cand, rep))
    parts.append("\n### YENİ katmanın bileşen katkısı (leave-one-out, J')\n" + cp.new_ablation(d, cand, cfg))
    parts.append("\n### Giriş-uzama özelliklerinin sonuçla ilişkisi (IC)\n" + dg.feature_ic_table(d, cand))
    parts.append("\n### Eski sistem tanıları bu bölmede\n#### Ablation\n" + dg.ablation_table(d)
                 + "\n\n#### RSI\n" + dg.rsi_table(d) + "\n\n#### Koruma etkisi\n" + dg.guard_effect_table(d)
                 + "\n\n#### 0-2 lensi\n" + dg.zero_two_table(d))
    parts.append("\n### VIX stres bağlamı\n"
                 + stress.stress_table(stress.attach(d, stress.load_vix(Path(cache))), cand))
    tp = cp.turning_points(d)
    parts.append("\n### Dönüm noktası tepkisi (hindsight — yalnız tanılama)\n"
                 + cp.reversal_reaction(d, cand, sn, tp))
    # yürütme
    old_tr = cp.run_exec(d, cand, (cand != 0).astype(float), uni, splits)
    new_tr = cp.run_exec(d, sn, rep["size"].where(sn != 0, 0.0), uni, splits)
    parts.append("\n### Yürütme backtesti (SL/TP/zaman stopu/ücret) — tümü\n" + cp.exec_table(old_tr, new_tr))
    for by in ("tf", "asset_class", "series"):
        parts.append(f"\n#### {by} kırılımı\n" + cp.exec_table(old_tr, new_tr, by=by))
    for mult in (0.0, 3.0):
        o2 = cp.run_exec(d, cand, (cand != 0).astype(float), uni, splits, cost_mult=mult)
        n2 = cp.run_exec(d, sn, rep["size"].where(sn != 0, 0.0), uni, splits, cost_mult=mult)
        parts.append(f"\n#### Maliyet duyarlılığı ×{mult}\n" + cp.exec_table(o2, n2))
    acc = cp.acceptance(d, cand, rep, old_tr, new_tr)
    parts.append("\n### Kabul ölçütleri\n" + cp.acceptance_md(acc))
    return "\n".join(parts), acc


def cmd_validate(a) -> None:
    out = Path(a.out)
    df = _load(a)
    uni = _uni(a)
    cfg = cp.load_frozen(out / "frozen_config.json")
    text, _ = _compare_split(df, cfg, uni, ("val",), "VALIDATION", a.cache)
    _write(out / "03_validation.md", "# VALIDATION: ESKİ vs YENİ\n\n" + text)


def cmd_final(a) -> None:
    out = Path(a.out)
    frozen = out / "frozen_config.json"
    lock = out / "test_run.lock"
    if not frozen.exists():
        sys.exit("dondurulmuş config yok — önce `tune`")
    if lock.exists() and not a.force:
        sys.exit(f"TEST zaten okundu ({lock.read_text().strip()}); tekrar ayar yapılamaz. --force bilinçli geçersiz kılar.")
    import hashlib
    h = hashlib.sha256(frozen.read_bytes()).hexdigest()[:16]
    lock.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} config_sha={h} force={a.force}\n", encoding="utf-8")
    df = _load(a)
    uni = _uni(a)
    cfg = cp.load_frozen(frozen)
    text, acc = _compare_split(df, cfg, uni, ("test",), "TEST (dokunulmamış)", a.cache)
    _write(out / "04_test.md", f"# TEST: ESKİ vs YENİ (config sha256[:16]={h})\n\n" + text)
    (out / "04_test_acceptance.json").write_text(json.dumps(acc, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("fetch", cmd_fetch), ("extract", cmd_extract), ("diagnose", cmd_diagnose),
                     ("tune", cmd_tune), ("validate", cmd_validate), ("final", cmd_final)):
        p = sub.add_parser(name)
        p.add_argument("--cache", default=str(D.DEFAULT_CACHE))
        p.add_argument("--sig", default="")
        p.add_argument("--out", default="")
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--only", nargs="*")
        p.add_argument("--bar-history", default=None, help="extract/validate/final: sahibin bar arşivi (data/runtime/bar_history)")
        p.add_argument("--force", action="store_true")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
