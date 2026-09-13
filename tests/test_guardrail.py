"""Output guardrail tests, including the G3 (no diagnostic assertion)
enforcement and the Tier-1-conditional-safety-netting subtlety.
"""

from __future__ import annotations

from diabetes_chatbot.guardrail import output_guardrail as guard


def test_blocks_number_adjacent_to_dose_unit():
    result = guard.evaluate("Take 10 units now.", tier=None)
    assert not result.passed
    assert "number_adjacent_to_dose_unit" in result.violations


def test_blocks_number_adjacent_to_drug_name():
    result = guard.evaluate("Take 500 metformin twice a day.", tier=None)
    assert not result.passed


def test_blocks_imperative_medication_instruction():
    result = guard.evaluate("You should increase your insulin tonight.", tier=None)
    assert not result.passed
    assert "imperative_medication_instruction" in result.violations


def test_does_not_block_glucose_reading_with_mgdl_unit():
    """mg/dL is a glucose-concentration unit, not a medication dose unit —
    it must never trip the dose-number check.
    """
    result = guard.evaluate("Your reading was 250 mg/dL.", tier=None)
    assert result.passed


def test_does_not_block_glucose_reading_with_mmol_unit():
    result = guard.evaluate("Your reading was 13.9 mmol/L.", tier=None)
    assert result.passed


def test_G3_blocks_diagnostic_assertion():
    result = guard.check_diagnostic_assertion("You have type 2 diabetes.")
    assert result == ["diagnostic_assertion"]


def test_G3_does_not_block_a_question_about_diagnosis_history():
    result = guard.check_diagnostic_assertion("Have you been diagnosed with diabetes before?")
    assert result == []


def test_G3_blocks_dka_diagnostic_assertion():
    result = guard.check_diagnostic_assertion("This means you have DKA.")
    assert result == ["diagnostic_assertion"]


def test_tier1_unconditional_emergency_language_is_a_violation():
    result = guard.evaluate("This is an emergency, go to the hospital now.", tier=1)
    assert not result.passed
    assert "tier_text_mismatch" in result.violations


def test_tier1_conditional_safety_netting_is_not_a_violation():
    """Required content: 'go to hospital immediately IF X happens' in a
    Tier 1 message must NOT be blocked.
    """
    text = "Come back or seek care immediately if you become drowsy, confused, or lose consciousness."
    result = guard.evaluate(text, tier=1)
    assert result.passed


def test_tier3_urgent_language_is_not_a_violation():
    result = guard.evaluate("This needs urgent in-person care now.", tier=3)
    assert result.passed


def test_clean_tier1_message_passes():
    result = guard.evaluate(
        "Based on what you've told me, this looks like something you can manage at home for now.",
        tier=1,
    )
    assert result.passed


def test_all_approved_content_blocks_pass_the_guardrail():
    """Regression guard: none of our own approved templates should ever
    trip the guardrail (that would mean every message gets replaced by the
    fallback)."""
    from diabetes_chatbot.rendering import content_blocks as blocks

    fixed_texts = [
        blocks.CONSENT_DECLINED_EXIT,
        blocks.UNDER_18_EXIT,
        blocks.NON_DIABETES_EMERGENCY_EXIT,
        blocks.PREGNANCY_EXIT,
        blocks.INSULIN_REFUSAL,
        blocks.GUARDRAIL_FALLBACK,
        blocks.LOOP_ESCALATION,
    ]
    for text in fixed_texts:
        result = guard.evaluate(text, tier=None)
        assert result.passed, f"approved content block unexpectedly blocked: {text!r} -> {result.violations}"

    for tier, trigger_text in blocks.DEFAULT_TRIGGER_LISTS.items():
        result = guard.evaluate(trigger_text, tier=tier)
        assert result.passed, f"trigger list for tier {tier} unexpectedly blocked: {result.violations}"

    for role_key in ("patient", "caregiver"):
        for q in blocks.QUESTION_BANK.values():
            text = q.patient_text if role_key == "patient" else q.caregiver_text
            result = guard.evaluate(text, tier=None)
            assert result.passed, f"question text unexpectedly blocked: {text!r} -> {result.violations}"
