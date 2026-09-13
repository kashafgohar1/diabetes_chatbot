"""Regression tests for bugs from an earlier build of this project. Each
test name says which bug it guards.
"""

from __future__ import annotations

from diabetes_chatbot import lexicon
from diabetes_chatbot.state import Role, TriState


# --- Bug 1: negation ordering -------------------------------------------

def test_bug1_not_high_is_negative_not_a_false_positive():
    result = lexicon.detect("Not high, feeling okay.", lexicon.B_ISOLATED_HYPERGLYCEMIA_SYMPTOMS)
    assert result is TriState.NO


def test_bug1_mirrored_case_high_alone_is_still_detected_positive():
    """The task explicitly calls out the mirrored failure mode: fixing the
    negation bug must not cause an under-triage where genuine "high" is
    missed.
    """
    result = lexicon.detect("My sugar is high today.", lexicon.B_ISOLATED_HYPERGLYCEMIA_SYMPTOMS)
    assert result is TriState.YES


# --- Bug 2: substring role matching --------------------------------------

def test_bug2_someone_else_is_caregiver_not_patient():
    """'someone else' contains the substring 'me' — a naive check would
    misclassify this as the patient."""
    assert lexicon.detect_role("I'm asking about someone else.") is Role.CAREGIVER


def test_bug2_my_mother_is_caregiver():
    assert lexicon.detect_role("My mother is not feeling well.") is Role.CAREGIVER


def test_bug2_i_am_is_still_patient():
    assert lexicon.detect_role("I am feeling shaky and hungry.") is Role.PATIENT


# --- Bug 3: red-flag lexicon recall ---------------------------------------

def test_bug3_not_waking_up_properly_is_a_positive_red_flag():
    """'not waking up properly' is an idiom meaning unresponsive — it must
    be a POSITIVE match, not suppressed by generic negation handling just
    because it contains the word 'not'."""
    result = lexicon.detect("She's not waking up properly.", lexicon.UNCONSCIOUS_OR_NOT_RESPONDING)
    assert result is TriState.YES


def test_bug3_wont_wake_variant_is_also_positive():
    result = lexicon.detect("He won't wake up.", lexicon.UNCONSCIOUS_OR_NOT_RESPONDING)
    assert result is TriState.YES


def test_bug3_genuine_negation_of_unconscious_is_still_negative():
    """Fixing bug 3 must not break legitimate negation of a bare keyword."""
    result = lexicon.detect("He is not unconscious, just tired.", lexicon.UNCONSCIOUS_OR_NOT_RESPONDING)
    assert result is TriState.NO


# --- OQ-8: glucose value/unit capture, never guessed ----------------------

def test_bare_number_with_no_unit_is_flagged_ambiguous():
    value, unit, ambiguous = lexicon.extract_glucose_reading("It was 20 this morning")
    assert value == 20.0
    assert unit is None
    assert ambiguous is True


def test_mgdl_unit_is_captured_and_not_ambiguous():
    value, unit, ambiguous = lexicon.extract_glucose_reading("It read 126 mg/dL")
    assert value == 126.0
    assert unit == "mg/dL"
    assert ambiguous is False


def test_mmol_unit_is_captured_and_not_ambiguous():
    value, unit, ambiguous = lexicon.extract_glucose_reading("13.9 mmol/L this evening")
    assert value == 13.9
    assert unit == "mmol/L"
    assert ambiguous is False


def test_20_mgdl_and_20_mmol_are_never_conflated():
    _, unit_mgdl, _ = lexicon.extract_glucose_reading("20 mg/dL")
    _, unit_mmol, _ = lexicon.extract_glucose_reading("20 mmol/L")
    assert unit_mgdl == "mg/dL"
    assert unit_mmol == "mmol/L"
    assert unit_mgdl != unit_mmol


# --- Insulin/dose request detection (G2) ----------------------------------

def test_insulin_dose_request_detected_under_various_framings():
    for text in (
        "How much insulin should I take?",
        "how many units should i take",
        "can you calculate my insulin dose",
        "should I increase my insulin tonight",
    ):
        assert lexicon.detect_insulin_dose_request(text), text


def test_ordinary_message_is_not_a_dose_request():
    assert not lexicon.detect_insulin_dose_request("I'm feeling a bit shaky and hungry.")
