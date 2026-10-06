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
    assert len(rows) <= 3  # satır tavanı aşılmaz (kompaksiyon tavanın altına kırpar)
    assert path.read_text(encoding="utf-8").count("\n") == len(rows)


def test_world_archive_compaction_is_not_triggered_on_every_write_at_cap(tmp_path, monkeypatch):
    """Tavana ulaşınca her yazımda tam oku+yaz geri gelmemeli (histerezis)."""
    path = tmp_path / "archive.jsonl"
    monkeypatch.setenv("WORLD_STATE_ARCHIVE_PATH", str(path))
    monkeypatch.setattr(
        archive, "_cfg",
        lambda: {"cadence_seconds": 300, "max_snapshots": 100, "material_change_epsilon": 0.02},
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
    compactions = []
    real = archive._compact
    monkeypatch.setattr(archive, "_compact", lambda *a, **k: (compactions.append(a[1]), real(*a, **k)))
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(130):
        archive.record(object(), now=base + timedelta(seconds=400 * i))
    # Tavan 100: 101., 112. ve 123. yazımda (her ~%10 tavanlık yazımda bir) %90'a kırpılır —
    # 30 tavan-üstü yazımda 30 değil 3 tam yeniden yazım (canlıda 5000 → ~500 yazımda bir).
    assert compactions == [90, 90, 90]
    assert len(archive.all_records()) == 97         # 90 + 123. sonrası 7 yazım


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

def test_budget_counts_by_actual_provider_not_mode(tmp_path, monkeypatch):
    """Sayım cevabı GERÇEKTEN veren sağlayıcıya göre: Ollama modunda da sohbet önce
    Groq'a gider — o kullanım sayılmalı (mod 'ollama' diye serbest bırakılmamalı)."""
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    monkeypatch.setenv("LLM_DAILY_TOKEN_BUDGET", "100")
    budget.record(1000, "groq")  # ücretli → sayılır
    assert budget.used_tokens() == 1000
    budget.record(5000, "ollama")  # yerel → SAYILMAZ
    budget.record(300, "mock")     # test çifti ücretli sayılır
    assert budget.used_tokens() == 1300
    assert budget.can_spend(1) is False


def test_budget_gate_drops_only_paid_providers_when_exhausted(tmp_path, monkeypatch):
    from packages.agent.llm.client import (
        FallbackLLMClient,
        GroqClient,
        OllamaClient,
        OpenRouterClient,
    )

    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "budget.json"))
    monkeypatch.setenv("LLM_DAILY_TOKEN_BUDGET", "100")
    chat_chain = FallbackLLMClient([GroqClient(), OpenRouterClient(), OllamaClient()])  # Ollama modu sohbet sırası
    assert budget.gate(chat_chain, 50) is chat_chain                 # bütçe yetiyor → zincir aynen
    budget.record(200, "groq")                                       # bütçe doldu
    gated = budget.gate(chat_chain, 50)
    assert isinstance(gated, OllamaClient)                           # sohbet kilitlenmez, yerelde sürer
    assert budget.gate(GroqClient(), 50) is None                     # yalnız ücretli → aşıldı
    local = OllamaClient()
    assert budget.gate(local, 10_000) is local                       # yerel hiç kilitlenmez
    assert budget.gate(None, 1) is None


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


# ── (4) tick döngüsü: hedef aralık + en az 10 sn dinlenme (owner kararı 2026-10-06) ──

def test_tick_rest_targets_interval_but_never_below_min_rest():
    from apps.supervisor.main import _rest_seconds

    assert _rest_seconds(30, 12, 10) == 18      # hızlı tick → 30 sn döngüye hizalan
    assert _rest_seconds(30, 34, 10) == 10      # aralıktan uzun tick → yine 10 sn dinlen
    assert _rest_seconds(30, 25, 10) == 10      # kalan 5 sn < 10 → 10
