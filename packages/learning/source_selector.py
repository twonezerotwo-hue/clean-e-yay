"""I3 — Kaynak Seçici (Source Selector): canlı kanıt ince olduğunda, GEREKTİĞİNDE
shadow/backtest kanıtını AYRI DAMGALI kanalda dahil eder.

Amaç (owner talebi 2026-07-05, `docs/LEARNING_INTEGRATION_REPORT.md`): bir
öğrenici "bu rejim için canlı kanıt yok/ince" dediğinde, elde biriken shadow ve
backtest kanıtı ATIL kalmasın — ama gerçek canlı hücreye KARIŞMADAN, kaynak
damgalı olarak. İlk tüketici: FAZ-4 sinyal-kalitesi boş rejimlerini (canlı
outcome hiç yok) backtest quantum karnesiyle destekle.

TASARIM (F5-1 `cf_by_tf` ilkesi — gerçek hücre kirlenmez):
- Canlı HER ZAMAN önce; canlı yeterli örneğe ulaşıyorsa fallback hiç bakılmaz.
- Fallback YALNIZCA `LEARNING_INCLUDE_SHADOW` (env, DEFAULT OFF) açıkken devreye
  girer. Kapalıyken bu görünüm SALT canlıdır — hiçbir shadow/backtest kanıt
  sızmaz (bayt-aynı: mevcut tüketici davranışı değişmez, çünkü fallback boş).
- Fallback damgalı ayrı `augmented` alanında döner (`source: backtest|shadow`);
  canlı `live_n`/`per_regime` sayısına ASLA eklenmez → gerçek hücre kirlenmez.
- Rollback = flag'i kapat (anında salt-canlı).

Bu modül evidence_bus (I1) çıktısını OKUR; hiçbir şey üretmez/karara bağlamaz.
KIRMIZI ÇİZGİ: kaynak seçimi kanıt SUNAR, terfi/yön/execution YAPMAZ (I4/I5;
yön motoru owner onayı olmadan asla otomatik).

PAPER_SAFE / NO_EXECUTION / SALT-GÖZLEM.
"""
from __future__ import annotations

import os
from dataclasses import asdict

from packages.learning import evidence_bus as eb
from packages.learning import maturity_gate

FLAG = "LEARNING_INCLUDE_SHADOW"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})

# Canlı "ince" sayılır: min-örnek altındaysa (I2 olgunluk kapısıyla aynı taban).
MIN_LIVE_SAMPLES = maturity_gate.MIN_SAMPLES

# Canlı-olmayan fallback önceliği (küçük = tercih): backtest (rejim-çeşitli,
# kontrollü prova) shadow'dan (gözlem) önce gelir. Canlı bu sıraya GİRMEZ — o
# her zaman ayrı ve önce değerlendirilir.
_FALLBACK_PRIORITY = {eb.BACKTEST: 0, eb.SHADOW: 1}


def include_shadow() -> bool:
    """LEARNING_INCLUDE_SHADOW açık mı? (backtest_recon deseni — DEFAULT OFF,
    explicit opt-in)."""
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def _best_fallback(candidates: list[eb.EvidenceRecord]) -> eb.EvidenceRecord | None:
    """Adaylardan en güçlü fallback: önce kaynak önceliği, eşitlikte daha çok
    örnek. Aday yoksa None."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda r: (_FALLBACK_PRIORITY.get(r.source, 99), -int(r.n_samples or 0)),
    )


def regime_coverage(
    topic: str = "signal_quality",
    *,
    records: list[eb.EvidenceRecord] | None = None,
    min_live: int = MIN_LIVE_SAMPLES,
) -> dict:
    """Bir konu için rejim-kapsama: her rejimde canlı kanıt var mı / ince mi; ince
    + flag ON ise AYRI DAMGALI kanalda en iyi fallback (backtest/shadow) eklenir.

    Flag OFF → yalnız canlı rejimler + boş `augmented` (salt-canlı görünüm).
    Flag ON  → canlı-ince/boş rejimlere damgalı fallback (gerçek `live_n` kirlenmez).
    """
    records = records if records is not None else eb.collect()
    include = include_shadow()

    live_by_regime: dict[str, list[eb.EvidenceRecord]] = {}
    fallback_by_regime: dict[str, list[eb.EvidenceRecord]] = {}
    for r in records:
        if not r.regime:
            continue
        if r.source == eb.LIVE and r.topic == topic:
            live_by_regime.setdefault(r.regime, []).append(r)
        elif r.source != eb.LIVE:
            fallback_by_regime.setdefault(r.regime, []).append(r)

    # Flag OFF ise fallback-only rejimler görünmez (salt-canlı → bayt-aynı görünüm).
    regimes = set(live_by_regime)
    if include:
        regimes |= set(fallback_by_regime)

    per_regime: dict[str, dict] = {}
    for regime in sorted(regimes):
        live = live_by_regime.get(regime, [])
        live_n = max((int(r.n_samples or 0) for r in live), default=0)
        thin = live_n < min_live
        entry: dict = {
            "live_n": live_n,
            "thin": thin,
            "source_used": "live" if not thin else "none",
            "augmented": [],
        }
        if thin and include:
            fb = _best_fallback(fallback_by_regime.get(regime, []))
            if fb is not None:
                entry["augmented"] = [asdict(fb)]  # damgalı (source: backtest|shadow)
                entry["source_used"] = fb.source
        per_regime[regime] = entry

    return {
        "topic": topic,
        "include_shadow": include,
        "min_live_samples": min_live,
        "per_regime": per_regime,
        "note": (
            "kaynak seçici (I3, salt-gözlem): canlı önce; ince rejimde flag ON ise "
            "damgalı backtest/shadow fallback. flag OFF=salt-canlı. rollback=flag kapat."
        ),
    }


def viewmodel() -> dict:
    """`GET /learning/source-selection` görünümü (read-only, PAPER_SAFE)."""
    return regime_coverage()


__all__ = ["FLAG", "MIN_LIVE_SAMPLES", "include_shadow", "regime_coverage", "viewmodel"]
