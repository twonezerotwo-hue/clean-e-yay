"""Flag sapma guard'ı (denetim 2026-07-03, E-serisi tamamlayıcısı).

`scripts/flag-sync-check.sh` lokal .env ile AWS deploy arasındaki flag sapmasını
çalışma-zamanında yakalar (lokal .env gitignore'da → CI göremez). Bu test o
checker'ın KÖR NOKTASI olmadığını CI'da doğrular: deploy script'in
ensure_env/set_env ile set ettiği HER flag, checker'ın SYNC_FLAGS listesinde
tanınmalı. Aksi halde AWS bir flag'i kontrol ederken checker onu izlemez —
sessiz sapma riski geri gelir.

Lokal-only flag'ler (örn. LLM_MODE=ollama) bilinçle SYNC_FLAGS'te DEĞİL; bu test
yalnız deploy-kontrollü ⊆ checker yönünü zorlar (ters yönü değil)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "flag-sync-check.sh"
DEPLOY = ROOT / "scripts" / "deploy-from-github.sh"


def _sync_flags() -> set[str]:
    text = CHECK.read_text(encoding="utf-8")
    m = re.search(r'SYNC_FLAGS="(.*?)"', text, re.DOTALL)
    assert m, "flag-sync-check.sh içinde SYNC_FLAGS bloğu bulunamadı"
    return {tok for tok in m.group(1).split() if tok}


def _deploy_controlled_flags() -> set[str]:
    text = DEPLOY.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(?:ensure_env|set_env)\s+([A-Z0-9_]+)\s+", text, re.MULTILINE))


def test_check_script_exists_and_wired() -> None:
    assert CHECK.exists(), "flag-sync-check.sh yok"
    text = CHECK.read_text(encoding="utf-8")
    assert ".env" in text and "deploy-from-github.sh" in text  # iki tarafı da okur


def test_checker_has_no_blind_spots() -> None:
    """Deploy'un AWS'te kontrol ettiği her flag checker'da tanınmalı."""
    deploy_flags = _deploy_controlled_flags()
    sync_flags = _sync_flags()
    assert deploy_flags, "deploy script'te ensure_env/set_env direktifi bulunamadı"
    missing = deploy_flags - sync_flags
    assert not missing, (
        f"Bu flag'ler AWS deploy'da set ediliyor ama flag-sync-check SYNC_FLAGS'te "
        f"YOK (checker kör): {sorted(missing)} — scripts/flag-sync-check.sh'e ekle."
    )


def test_auto_only_flags_are_tracked() -> None:
    """E-4 aktivasyonunun senkron-flag'i (ve kardeşi) checker kapsamında."""
    sync_flags = _sync_flags()
    assert {"TF_TARGET_AUTO_ONLY", "TF_CALIBRATION_AUTO_ONLY"} <= sync_flags
