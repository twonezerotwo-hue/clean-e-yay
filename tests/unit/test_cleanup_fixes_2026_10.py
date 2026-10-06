"""Temizlik dönemi (2026-10) düzeltmeleri — regresyon testleri.

H-katmanı mantık/performans düzeltmelerini kilitler:
  1. Dünya arşivi APPEND-ONLY yazar; retention/row-cap YALNIZ tavan aşılınca
     kompaksiyonla uygulanır (her yazımda 40MB+ dosya yeniden yazılmaz).
  2. Ortak LLM bütçesi ÜCRETLİ tokenları sayar; ücretsiz/yerel modu (ollama)
     saymaz ve o modda bütçe kilidi uygulanmaz.
  3. LLM cache TTL=0 anında dolar (`>=` karşılaştırması).
  4. Yerleşik haber kuralları KELİME sınırlı eşleşir (alt-dize yanlış
     eşleşmeleri: "turmoil" ≠ oil, "software" ≠ war, "FedEx" ≠ fed,
     "Goldman" ≠ gold).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.agent.llm import budget, cache
from packages.data.providers.news import classify
from packages.world_state import archive

# ── (1) dünya arşivi: append-only + tavan kompaksiyonu ───────────────────────

def test_world_archive_appends_and_compacts_to_cap(tmp_path, monkeypatch):
    path = tmp_path / "archive.jsonl"
    monkeypatch.setenv("WORLD_STATE_ARCHIVE_PATH", str(path))
    monkeypatch.setattr(
        archive, "_cfg",
        lambda: {"cadence_seconds": 300, "max_snapshots": 3, "material_change_epsilon": 0.02},
    )
    monkeypatch.setattr(
        archive, "compact_record",
        lambda world, **kwargs: {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "snapshot_as_of": "2026-01-01T00:00:00+00:00",
            "factors": {}, "regime": "NEUTRAL", "flow_state": {},
            "event_ids": [], "statement_ids": [], "expectation_ids": [],
            "macro_event_ids": [], "interactions": [],
        },
    )
    archive._ROW_COUNT.clear()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    written = sum(
        1 if archive.record(object(), now=base + timedelta(seconds=400 * i)) is not None else 0
        for i in range(5)
    )
    assert written == 5  # her koşu kadence dolduğu için bir satır yazar
    rows = archive.all_records()
    assert len(rows) == 3  # satır tavanı: yalnız son 3 satır kalır
    assert path.read_text(encoding="utf-8").count("\n") == 3


def test_world_archive_no_rewrite_below_cap(tmp_path, monkeypatch):
    """Tavan altında dosya APPEND-ONLY büyür (tam yeniden yazım yok)."""
    path = tmp_path / "archive.jsonl"
    monkeypatch.setenv("WORLD_STATE_ARCHIVE_PATH", str(path))
    monkeypatch.setattr(
        archive, "_cfg",
        lambda: {"cadence_seconds": 300, "max_snapshots": 10, "material_change_epsilon": 0.02},
    )
    monkeypatch.setattr(
        archive, "compact_record",
        lambda world, **kwargs: {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "snapshot_as_of": "2026-01-01T00:00:00+00:00",
            "factors": {}, "regime": "NEUTRAL", "flow_state": {},
            "event_ids": [], "statement_ids": [], "expectation_ids": [],
            "macro_event_ids": [], "interactions": [],
        },
    )
    archive._ROW_COUNT.clear()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        archive.record(object(), now=base + timedelta(seconds=400 * i))
    # Kompaksiyon çağrılmamalı (tavan 10 > 3) → dosya append-only büyür.
    assert path.read_text(encoding="utf-8").count("\n") == 3
    assert str(path) in archive._ROW_COUNT  # sayaç tutuluyor


# ── (2) ortak LLM bütçesi: ücretsiz yerel mod sayılmaz ───────────────────────

def test_budget_free_local_mode_not_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    monkeypatch.setenv("LLM_DAILY_TOKEN_BUDGET", "100")
    budget.record(1000, "groq")  # ücretli → sayılır
    assert budget.used_tokens() == 1000
    budget.record(5000, "ollama")  # ücretsiz/yerel → SAYILMAZ
    assert budget.used_tokens() == 1000
    # Bütçe dolu olsa da yerel/mock mod serbest; ücretli mod kilitli.
    assert budget.can_spend(1, "ollama") is True
    assert budget.can_spend(1, "groq") is False
    # Mod verilmezse eski davranış (varsayılan = ücretli say).
    assert budget.can_spend(1) is False


# ── (3) LLM cache TTL=0 anında dolar ─────────────────────────────────────────

def test_llm_cache_ttl_zero_expires_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("LLM_CACHE_TTL_SEC", "0")
    cache.put("k", {"v": 1})
    assert cache.get("k") is None


# ── (4) yerleşik haber kuralları kelime-sınırlı ──────────────────────────────

@pytest.mark.parametrize(
    ("title", "symbol"),
    [
        ("Market turmoil grips investors", "BRENT"),   # "turmoil" ≠ oil
        ("Software stocks rally on cloud demand", "VIX"),  # "software" ≠ war
        ("FedEx shares jump after earnings", "DXY"),   # "FedEx" ≠ fed
        ("Goldman Sachs raises price target", "XAUUSD"),  # "Goldman" ≠ gold
    ],
)
def test_builtin_news_rules_reject_substring_false_positive(title, symbol, monkeypatch):
    monkeypatch.setattr("packages.data.registry.assets.all_assets", lambda: [])
    assert symbol not in classify.classify_asset_impact(title, "bearish")


@pytest.mark.parametrize(
    ("title", "symbol"),
    [
        ("Oil prices surge on OPEC cuts", "BRENT"),
        ("War fears rise across the region", "VIX"),
        ("Fed hikes rates to fight inflation", "DXY"),
        ("Gold rallies to a record high", "XAUUSD"),
    ],
)
def test_builtin_news_rules_still_match_real_signals(title, symbol, monkeypatch):
    monkeypatch.setattr("packages.data.registry.assets.all_assets", lambda: [])
    assert symbol in classify.classify_asset_impact(title, "bearish")
