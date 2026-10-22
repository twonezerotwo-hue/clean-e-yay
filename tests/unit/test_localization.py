from __future__ import annotations

from types import SimpleNamespace

from packages.agent import localization
from packages.agent.llm.client import LLMCompletion


def test_known_headline_is_turkish_without_model():
    text = localization.localize_text("Gold turns higher as oil prices dip")

    assert text == "Petrol fiyatları düşerken altın yükseliyor"


def test_translation_candidate_drops_model_control_suffix():
    candidate = localization._translation_candidate("Petrol fiyatları yükseliyor /no_stops")

    assert candidate == "Petrol fiyatları yükseliyor"


def test_local_model_translation_is_used_for_current_english_title(monkeypatch):
    title = "Witkoff calls Putin a humanitarian at Russia peace talks without Ukraine"
    completion = LLMCompletion(
        text='Witkoff, Rusya barış görüşmelerinde Putin\'i "insani" diye nitelendirdi.',
        model="test",
        input_tokens=1,
        output_tokens=1,
        source="ollama",
    )
    fake_client = SimpleNamespace(complete=lambda *args, **kwargs: completion)
    monkeypatch.setattr(localization.llm_client, "get_local_client", lambda: fake_client)
    localization.localize_news_title.cache_clear()

    result = localization.localize_news_title(title)

    assert "Rusya" in result
    assert result != title


def test_original_english_title_is_not_accepted_as_translation():
    title = "Bitcoin ticks up to $83.4k but oil jitters limit upside"

    assert localization._valid_translation(title, title) is False


def test_turkish_translation_can_keep_asset_names():
    original = "Bitcoin ticks up to $83.4k but oil jitters limit upside"
    translated = "Bitcoin 83,4 bin doları geçer ama petrol endişeleri yükselişi sınırlar."

    assert localization._valid_translation(translated, original) is True


def test_english_title_without_common_marker_is_detected():
    assert localization._looks_english(
        "First Trust Tactical High Yield ETF declares monthly dividend"
    ) is True
