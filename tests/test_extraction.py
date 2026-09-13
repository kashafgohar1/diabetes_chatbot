"""Extractor tests: the deterministic keyword extractor (used offline/CI)
and the LLM extractor's fail-closed behaviour.
"""

from __future__ import annotations

from diabetes_chatbot.extraction import keyword_extractor, llm_extractor
from diabetes_chatbot.state import TriState


def test_keyword_extractor_fills_mild_symptom_slot():
    updates = keyword_extractor.extract("I'm feeling shaky and sweaty")
    assert updates.get("a_mild_symptoms") is TriState.YES


def test_keyword_extractor_uses_pending_slot_for_bare_yes_no():
    assert keyword_extractor.extract("yes", pending_slot="a_mild_symptoms")["a_mild_symptoms"] is TriState.YES
    assert keyword_extractor.extract("no", pending_slot="a_mild_symptoms")["a_mild_symptoms"] is TriState.NO


def test_keyword_extractor_never_fills_unrelated_slots_from_silence():
    updates = keyword_extractor.extract("I'm feeling shaky and sweaty")
    assert "d_infection_signs" not in updates


def test_keyword_extractor_captures_glucose_and_flags_ambiguous_unit():
    updates = keyword_extractor.extract("it was 145 this morning")
    assert updates["glucose_value"] == 145.0
    assert updates["glucose_unit"] is None
    assert updates["glucose_unit_ambiguous"] is True


def test_keyword_extractor_never_returns_unknown_for_an_untouched_slot():
    """Silence must mean 'no update', never an explicit UNKNOWN overwrite —
    that's the tri-state discipline this whole architecture depends on."""
    updates = keyword_extractor.extract("just checking in")
    assert "a_mild_symptoms" not in updates


def test_llm_extractor_fails_closed_with_no_api_key(monkeypatch):
    monkeypatch.setattr(llm_extractor.settings, "anthropic_api_key", None)
    result = llm_extractor.extract("I'm feeling shaky", pending_slot="a_mild_symptoms")
    assert result == {}


def test_llm_extractor_fails_closed_on_client_exception(monkeypatch):
    class ExplodingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("network is down")

    monkeypatch.setattr(llm_extractor.settings, "anthropic_api_key", "fake-key-for-test")
    monkeypatch.setattr(llm_extractor, "_client", lambda: ExplodingClient())
    result = llm_extractor.extract("I'm feeling shaky", pending_slot="a_mild_symptoms")
    assert result == {}


def test_llm_extractor_fails_closed_on_unparseable_output(monkeypatch):
    class Block:
        type = "text"
        text = "not valid json{{{"

    class Response:
        content = [Block()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return Response()

    monkeypatch.setattr(llm_extractor.settings, "anthropic_api_key", "fake-key-for-test")
    monkeypatch.setattr(llm_extractor, "_client", lambda: FakeClient())
    result = llm_extractor.extract("I'm feeling shaky", pending_slot="a_mild_symptoms")
    assert result == {}


def test_llm_extractor_sanitizes_out_of_schema_values(monkeypatch):
    class Block:
        type = "text"
        text = '{"a_mild_symptoms": "definitely", "tier": 3, "unconscious_or_not_responding": "yes"}'

    class Response:
        content = [Block()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return Response()

    monkeypatch.setattr(llm_extractor.settings, "anthropic_api_key", "fake-key-for-test")
    monkeypatch.setattr(llm_extractor, "_client", lambda: FakeClient())
    result = llm_extractor.extract("some text")
    assert "tier" not in result  # never trust a tier from the LLM, even if it sends one
    assert "a_mild_symptoms" not in result  # invalid enum value dropped
    assert result["unconscious_or_not_responding"] is TriState.YES
