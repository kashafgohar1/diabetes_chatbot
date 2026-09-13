"""Runs the offline CLI simulator's built-in demo scenarios and checks each
lands on the expected tier — no API key, no WhatsApp credentials, no
network, matching what the demo actually shows.
"""

from __future__ import annotations

from diabetes_chatbot.cli.simulator import SCENARIOS, run_scenario


def test_caregiver_unresponsive_escalates_to_tier3_immediately():
    transcript = run_scenario("caregiver_unresponsive", verbose=False)
    assert any("Tier 3" in text for who, text in transcript if who == "bot")
    # Immediate: only the opening message and the bot's single reply.
    assert len(transcript) == 2


def test_insulin_request_is_refused_then_conversation_continues_to_tier1():
    transcript = run_scenario("insulin_request", verbose=False)
    bot_texts = [text for who, text in transcript if who == "bot"]
    assert any("can't calculate or suggest an insulin" in t.lower() for t in bot_texts)
    assert any("Tier 1" in t for t in bot_texts)


def test_mild_hypo_reaches_tier1():
    transcript = run_scenario("mild_hypo_tier1", verbose=False)
    bot_texts = [text for who, text in transcript if who == "bot"]
    assert any("Tier 1" in t for t in bot_texts)


def test_foot_problem_escalates_to_tier3_and_is_flagged_unsourced():
    transcript = run_scenario("foot_tier3", verbose=False)
    bot_texts = [text for who, text in transcript if who == "bot"]
    assert any("Tier 3" in t for t in bot_texts)
    assert any("has not yet been reviewed by a clinician" in t for t in bot_texts)


def test_bare_glucose_triggers_clarifying_question():
    transcript = run_scenario("bare_glucose_no_unit", verbose=False)
    bot_texts = [text for who, text in transcript if who == "bot"]
    assert any("mg/dl" in t.lower() or "mmol/l" in t.lower() for t in bot_texts)


def test_every_scenario_runs_without_a_missing_answer():
    for name in SCENARIOS:
        run_scenario(name, verbose=False)  # raises KeyError if the plan is incomplete
