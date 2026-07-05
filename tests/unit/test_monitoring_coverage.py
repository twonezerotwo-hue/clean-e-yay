"""I5 — İzleme kapsama guard'ı.

İki kabul (roadmap I5):
  1. "izlemesiz canlı-dokunuş yok": AWS-senkron HER davranış flag'i (SYNC_FLAGS)
     monitoring_coverage'da bir izleme sınıfına bağlı — kör nokta oluşamaz.
  2. registry-kapsama: WATCHDOG sınıfı flag'ler activation_watchdog.REGISTRY'de
     GERÇEKTEN o env flag'iyle kayıtlı; REGISTRY'nin her env girdisi de kapsamada.

Ayrıca: OWN_ROLLBACK girişleri import edilebilir/callable; muaf sınıflar monitorsuz.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

from packages.learning import activation_watchdog as aw
from packages.learning import monitoring_coverage as mc

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "flag-sync-check.sh"


def _sync_flags() -> set[str]:
    text = CHECK.read_text(encoding="utf-8")
    m = re.search(r'SYNC_FLAGS="(.*?)"', text, re.DOTALL)
    assert m, "flag-sync-check.sh içinde SYNC_FLAGS bloğu bulunamadı"
    return {tok for tok in m.group(1).split() if tok}


# ---------------------------------- kabul 1: izlemesiz canlı-dokunuş yok --------

def test_coverage_matches_sync_flags_exactly() -> None:
    """SYNC_FLAGS == COVERAGE anahtarları: ne kör nokta (eksik) ne hayalet (stale)."""
    sync = _sync_flags()
    cov = set(mc.COVERAGE)
    missing = sync - cov
    extra = cov - sync
    assert not missing, (
        f"Bu davranış flag'leri AWS'e senkron ama izleme sınıfı YOK (kör nokta): "
        f"{sorted(missing)} — monitoring_coverage.COVERAGE'a sınıflandır."
    )
    assert not extra, (
        f"COVERAGE'da SYNC_FLAGS'te olmayan hayalet flag: {sorted(extra)}"
    )


def test_all_mechanisms_known() -> None:
    for flag, d in mc.COVERAGE.items():
        assert d["mechanism"] in mc.MECHANISMS, f"{flag}: bilinmeyen izleme sınıfı"
        assert d.get("reason"), f"{flag}: gerekçe (reason) zorunlu"


# ---------------------------------- kabul 2: registry-kapsama -------------------

def test_watchdog_flags_registered_with_exact_env() -> None:
    """Her WATCHDOG flag'i REGISTRY'de o EXACT env flag'iyle kayıtlı."""
    for flag, d in mc.COVERAGE.items():
        if d["mechanism"] != mc.WATCHDOG:
            continue
        key = d["monitor"]
        assert key in aw.REGISTRY, f"WATCHDOG {flag} → REGISTRY'de '{key}' yok"
        assert aw.REGISTRY[key]["source"] == ("env", flag), (
            f"REGISTRY['{key}'] kaynağı {flag} env flag'ini izlemiyor"
        )


def test_registry_env_flags_are_watchdog_classified() -> None:
    """Ters yön: REGISTRY'nin her ENV girdisi kapsamada WATCHDOG olarak var
    (izleyici var ama sınıflanmamış flag = gizli kapsama boşluğu)."""
    reg_env_flags = {
        ref for meta in aw.REGISTRY.values()
        for kind, ref in [meta["source"]] if kind == "env"
    }
    assert reg_env_flags == mc.watchdog_env_flags(), (
        "activation_watchdog REGISTRY env flag'leri ile COVERAGE WATCHDOG kümesi "
        "ayrıştı — biri güncellenince diğeri de güncellenmeli."
    )


# ---------------------------------- own-rollback + muaf sınıflar ----------------

def test_own_rollback_entrypoints_importable() -> None:
    """OWN_ROLLBACK 'modül:callable' girişi gerçekten import edilir + çağrılabilir."""
    for flag, d in mc.COVERAGE.items():
        if d["mechanism"] != mc.OWN_ROLLBACK:
            continue
        ref = d["monitor"]
        assert ref and ":" in ref, f"{flag}: OWN_ROLLBACK monitor 'modül:callable' olmalı"
        mod_name, fn_name = ref.split(":", 1)
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name, None)
        assert callable(fn), f"{flag}: {ref} import edilemedi/çağrılabilir değil"


def test_exempt_classes_have_no_monitor() -> None:
    for flag, d in mc.COVERAGE.items():
        if d["mechanism"] in (mc.INPUT_HYGIENE, mc.TUNING_PARAM, mc.SHADOW_EXEMPT):
            assert d["monitor"] is None, f"{flag}: muaf sınıf monitor taşımamalı"


# ---------------------------------- canlı özet ---------------------------------

def test_coverage_summary_marks_watchdog_registered() -> None:
    summary = mc.coverage_summary()
    assert summary["total"] == len(mc.COVERAGE)
    for row in summary["flags"]:
        if row["mechanism"] == mc.WATCHDOG:
            assert row["registered"] is True, f"{row['flag']} REGISTRY'de görünmüyor"
    # en az bir shadow-muaf ve bir own-rollback beklenir (sınıf çeşitliliği)
    assert summary["by_mechanism"].get(mc.SHADOW_EXEMPT, 0) >= 1
    assert summary["by_mechanism"].get(mc.OWN_ROLLBACK, 0) >= 1
