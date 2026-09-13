"""One (or more) test per protocol rule ID. Named so `pytest -k <RULE_ID>`
selects every test bound to that rule — e.g. `pytest -k A3` runs
test_A3_fires_on_unconscious and test_A3_cannot_determine_without_swallow_info.

See test_protocol_manifest.py for the check that fails the build if a
protocol rule ships with no matching test at all.
"""

from __future__ import annotations

from diabetes_chatbot.engine import rules
from diabetes_chatbot.engine.types import RuleOutcome
from diabetes_chatbot.state import ClinicalState, TriState

FIRES = RuleOutcome.FIRES
NO_FIRE = RuleOutcome.DOES_NOT_FIRE
CANNOT = RuleOutcome.CANNOT_DETERMINE


def blank() -> ClinicalState:
    return ClinicalState()


# --- A1 ----------------------------------------------------------------

def test_A1_fires_on_mild_symptoms_able_to_self_treat_and_swallow():
    s = blank()
    s.a_mild_symptoms = TriState.YES
    s.a_able_to_swallow_safely = TriState.YES
    s.a_able_to_self_treat_unaided = TriState.YES
    result = rules.rule_a1(s)
    assert result.outcome is FIRES
    assert result.tier == 1
    assert not result.invented and not result.unsourced


def test_A1_does_not_fire_when_symptoms_absent():
    s = blank()
    s.a_mild_symptoms = TriState.NO
    assert rules.rule_a1(s).outcome is NO_FIRE


def test_A1_cannot_determine_when_symptoms_unknown():
    s = blank()
    result = rules.rule_a1(s)
    assert result.outcome is CANNOT
    assert result.needed_slot == "a_mild_symptoms"
    assert result.tier == 1


# --- A2 ----------------------------------------------------------------

def test_A2_fires_on_frequent_or_impaired_awareness_history():
    s = blank()
    s.a_frequent_or_past_severe_or_impaired_awareness = TriState.YES
    result = rules.rule_a2(s)
    assert result.outcome is FIRES and result.tier == 2


def test_A2_does_not_fire_with_no_history():
    s = blank()
    s.a_frequent_or_past_severe_or_impaired_awareness = TriState.NO
    assert rules.rule_a2(s).outcome is NO_FIRE


def test_A2_cannot_determine_when_unknown():
    s = blank()
    result = rules.rule_a2(s)
    assert result.outcome is CANNOT and result.tier == 2


# --- A3 ----------------------------------------------------------------

def test_A3_fires_on_unconscious():
    s = blank()
    s.unconscious_or_not_responding = TriState.YES
    result = rules.rule_a3(s)
    assert result.outcome is FIRES and result.tier == 3


def test_A3_fires_on_unable_to_swallow_safely():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    s.a_able_to_swallow_safely = TriState.NO
    result = rules.rule_a3(s)
    assert result.outcome is FIRES and result.tier == 3


def test_A3_does_not_fire_when_conscious_and_swallowing_safely():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    s.a_able_to_swallow_safely = TriState.YES
    assert rules.rule_a3(s).outcome is NO_FIRE


def test_A3_cannot_determine_when_consciousness_unknown():
    s = blank()
    result = rules.rule_a3(s)
    assert result.outcome is CANNOT
    assert result.needed_slot == "unconscious_or_not_responding"


# --- A4 (invented, closes OQ-4) -----------------------------------------

def test_A4_fires_when_conscious_can_swallow_but_cannot_reach_sugar_unaided():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    s.a_able_to_swallow_safely = TriState.YES
    s.a_able_to_self_treat_unaided = TriState.NO
    result = rules.rule_a4(s)
    assert result.outcome is FIRES
    assert result.tier == 3
    assert result.invented is True


def test_A4_does_not_fire_when_able_to_reach_treatment_unaided():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    s.a_able_to_swallow_safely = TriState.YES
    s.a_able_to_self_treat_unaided = TriState.YES
    assert rules.rule_a4(s).outcome is NO_FIRE


def test_A4_cannot_determine_when_self_treat_capability_unknown():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    s.a_able_to_swallow_safely = TriState.YES
    result = rules.rule_a4(s)
    assert result.outcome is CANNOT
    assert result.needed_slot == "a_able_to_self_treat_unaided"


# --- B1 ------------------------------------------------------------------

def test_B1_fires_on_isolated_hyperglycemia_symptoms_no_red_flags():
    s = blank()
    s.b_isolated_hyperglycemia_symptoms = TriState.YES
    s.b_dka_red_flags = TriState.NO
    result = rules.rule_b1(s)
    assert result.outcome is FIRES and result.tier == 2


def test_B1_does_not_fire_when_red_flags_present():
    s = blank()
    s.b_isolated_hyperglycemia_symptoms = TriState.YES
    s.b_dka_red_flags = TriState.YES
    assert rules.rule_b1(s).outcome is NO_FIRE


def test_B1_cannot_determine_absence_of_red_flags_from_silence():
    """OQ-9: an unasked question must never be read as NO."""
    s = blank()
    s.b_isolated_hyperglycemia_symptoms = TriState.YES
    result = rules.rule_b1(s)
    assert result.outcome is CANNOT
    assert result.needed_slot == "b_dka_red_flags"


# --- B2 --------------------------------------------------------------------

def test_B2_fires_on_dka_red_flags():
    s = blank()
    s.b_dka_red_flags = TriState.YES
    result = rules.rule_b2(s)
    assert result.outcome is FIRES and result.tier == 3


def test_B2_fires_on_hyperglycemia_symptom_with_no_diagnosis():
    s = blank()
    s.b_dka_red_flags = TriState.NO
    s.b_isolated_hyperglycemia_symptoms = TriState.YES
    s.diabetes_diagnosed = TriState.NO
    result = rules.rule_b2(s)
    assert result.outcome is FIRES and result.tier == 3


def test_B2_does_not_fire_with_no_red_flags_and_known_diagnosis():
    s = blank()
    s.b_dka_red_flags = TriState.NO
    s.b_isolated_hyperglycemia_symptoms = TriState.YES
    s.diabetes_diagnosed = TriState.YES
    assert rules.rule_b2(s).outcome is NO_FIRE


# --- C1 (OQ-1: draft says 1/2, implemented as Tier 2) ------------------

def test_C1_fires_as_tier_2_per_OQ1():
    s = blank()
    s.c_new_symptoms = TriState.YES
    s.c_red_flags = TriState.NO
    result = rules.rule_c1(s)
    assert result.outcome is FIRES and result.tier == 2


def test_C1_does_not_fire_when_red_flags_present():
    s = blank()
    s.c_new_symptoms = TriState.YES
    s.c_red_flags = TriState.YES
    assert rules.rule_c1(s).outcome is NO_FIRE


def test_C1_cannot_determine_red_flags_from_silence():
    s = blank()
    s.c_new_symptoms = TriState.YES
    result = rules.rule_c1(s)
    assert result.outcome is CANNOT and result.needed_slot == "c_red_flags"


# --- C2 ------------------------------------------------------------------

def test_C2_fires_with_red_flags():
    s = blank()
    s.c_red_flags = TriState.YES
    result = rules.rule_c2(s)
    assert result.outcome is FIRES and result.tier == 3


def test_C2_does_not_fire_without_red_flags():
    s = blank()
    s.c_red_flags = TriState.NO
    assert rules.rule_c2(s).outcome is NO_FIRE


# --- D1 --------------------------------------------------------------------

def test_D1_fires_on_stable_non_infected_foot():
    s = blank()
    s.d_stable_non_infected = TriState.YES
    s.d_infection_signs = TriState.NO
    s.d_severe_signs = TriState.NO
    result = rules.rule_d1(s)
    assert result.outcome is FIRES and result.tier == 1


def test_D1_does_not_fire_when_not_stable():
    s = blank()
    s.d_stable_non_infected = TriState.NO
    assert rules.rule_d1(s).outcome is NO_FIRE


# --- D2 --------------------------------------------------------------------

def test_D2_fires_on_infection_signs():
    s = blank()
    s.d_infection_signs = TriState.YES
    s.d_severe_signs = TriState.NO
    result = rules.rule_d2(s)
    assert result.outcome is FIRES and result.tier == 2


def test_D2_does_not_fire_without_infection_signs():
    s = blank()
    s.d_infection_signs = TriState.NO
    assert rules.rule_d2(s).outcome is NO_FIRE


# --- D3 (unsourced, OQ-2) ------------------------------------------------

def test_D3_fires_and_is_flagged_unsourced():
    s = blank()
    s.d_severe_signs = TriState.YES
    result = rules.rule_d3(s)
    assert result.outcome is FIRES
    assert result.tier == 3
    assert result.unsourced is True


def test_D3_does_not_fire_without_severe_signs():
    s = blank()
    s.d_severe_signs = TriState.NO
    result = rules.rule_d3(s)
    assert result.outcome is NO_FIRE
    assert result.unsourced is True  # flagged even when it doesn't fire


# --- G1 ------------------------------------------------------------------

def test_G1_fires_on_unconscious_mention():
    s = blank()
    s.unconscious_or_not_responding = TriState.YES
    result = rules.rule_g1(s)
    assert result.outcome is FIRES and result.tier == 3


def test_G1_does_not_fire_when_explicitly_denied():
    s = blank()
    s.unconscious_or_not_responding = TriState.NO
    assert rules.rule_g1(s).outcome is NO_FIRE


# --- G2 ------------------------------------------------------------------

def test_G2_fires_on_insulin_dose_request():
    s = blank()
    s.insulin_dose_request_detected = True
    result = rules.rule_g2(s)
    assert result.outcome is FIRES
    assert result.action == "refuse_gracefully"


def test_G2_does_not_fire_without_a_dose_request():
    s = blank()
    assert rules.rule_g2(s).outcome is NO_FIRE


# --- SN1 / SN2 / SN3 (engineering safety nets — invented) ----------------

def test_SN1_fires_on_non_diabetes_emergency_and_is_invented():
    s = blank()
    s.non_diabetes_emergency_signs = TriState.YES
    result = rules.rule_sn1_non_diabetes_emergency(s)
    assert result.outcome is FIRES and result.tier == 3 and result.invented is True


def test_SN2_fires_on_pregnancy_and_is_invented():
    s = blank()
    s.pregnant = TriState.YES
    result = rules.rule_sn2_pregnancy(s)
    assert result.outcome is FIRES and result.tier == 3 and result.invented is True


def test_SN3_fires_as_tier2_floor_when_nothing_else_resolved():
    result = rules.rule_sn3_fallback_safety_net(unresolved=False)
    assert result.outcome is FIRES and result.tier == 2 and result.invented is True


def test_SN3_does_not_fire_while_something_remains_unresolved():
    result = rules.rule_sn3_fallback_safety_net(unresolved=True)
    assert result.outcome is NO_FIRE
