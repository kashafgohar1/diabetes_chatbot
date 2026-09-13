"""Tests for the engine's structural aggregation and G4 behaviour.

G4 ("ambiguous cases default to the higher-urgency tier, never lower") is
not a prompt instruction — it's structural. These tests are what that claim
actually rests on.
"""

from __future__ import annotations

from diabetes_chatbot.engine import engine
from diabetes_chatbot.engine.types import NeedsInfo, Refusal, Verdict
from diabetes_chatbot.state import ClinicalState, PresentingComplaint, TriState


def _resolved_hypo_state(**overrides) -> ClinicalState:
    s = ClinicalState()
    s.unconscious_or_not_responding = TriState.NO
    s.non_diabetes_emergency_signs = TriState.NO
    s.pregnant = TriState.NO
    s.presenting_complaint = PresentingComplaint.HYPOGLYCEMIA
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_G4_never_concludes_while_a_higher_tier_rule_is_undetermined():
    """Nothing has fired yet and category rules are all CANNOT_DETERMINE —
    the engine must ask, not guess, and it must ask about the *highest*
    reachable tier first.
    """
    s = _resolved_hypo_state()
    result = engine.evaluate(s)
    assert isinstance(result, NeedsInfo)
    assert result.highest_reachable_tier == 3  # A3/A4 outrank A1/A2


def test_G4_keeps_asking_until_nothing_higher_is_reachable_then_concludes():
    s = _resolved_hypo_state(
        a_able_to_swallow_safely=TriState.YES,
        a_able_to_self_treat_unaided=TriState.YES,
        a_frequent_or_past_severe_or_impaired_awareness=TriState.NO,
        a_mild_symptoms=TriState.YES,
    )
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 1
    assert "A1" in result.fired_rule_ids


def test_OQ7_higher_tier_wins_and_both_rule_ids_reported_when_A1_and_A2_both_apply():
    s = _resolved_hypo_state(
        a_able_to_swallow_safely=TriState.YES,
        a_able_to_self_treat_unaided=TriState.YES,
        a_frequent_or_past_severe_or_impaired_awareness=TriState.YES,  # A2 also applies
        a_mild_symptoms=TriState.YES,  # A1 also applies
    )
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 2  # higher tier wins (A2 > A1)
    assert "A2" in result.fired_rule_ids
    assert "A1" in result.fired_rule_ids  # OQ-7: both rule IDs are reported


def test_urgent_override_fires_from_partial_state_before_role_or_age_known():
    """G1 must be able to interrupt the consent/age-gate preamble — this is
    what check_urgent_override is for.
    """
    s = ClinicalState()  # role, age, consent all still unset
    s.unconscious_or_not_responding = TriState.YES
    override = engine.check_urgent_override(s)
    assert isinstance(override, Verdict)
    assert override.tier == 3
    assert override.fired_rule_ids == ("G1",)


def test_urgent_override_is_none_when_nothing_has_fired_yet():
    s = ClinicalState()
    assert engine.check_urgent_override(s) is None


def test_urgent_override_does_not_proactively_ask_anything():
    """check_urgent_override must be silent (return None) rather than
    prompt about SN1/SN2/G1 before the normal safety pre-screen — it only
    reacts to evidence already present in state.
    """
    s = ClinicalState()  # everything UNKNOWN
    assert engine.check_urgent_override(s) is None


def test_G2_refusal_returned_before_any_tier_reasoning():
    s = ClinicalState()
    s.insulin_dose_request_detected = True
    result = engine.evaluate(s)
    assert isinstance(result, Refusal)
    assert result.rule_id == "G2"


def test_non_diabetes_emergency_overrides_everything_else():
    s = ClinicalState()
    s.non_diabetes_emergency_signs = TriState.YES
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 3
    assert "SN1" in result.fired_rule_ids
    assert "SN1" in result.invented_rules_used


def test_pregnancy_overrides_category_reasoning():
    s = ClinicalState()
    s.pregnant = TriState.YES
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 3
    assert "SN2" in result.fired_rule_ids


def test_safety_net_floor_is_tier_2_never_tier_1_when_nothing_fires():
    """G4 forbids defaulting low. If a category is picked and nothing
    resolves, the floor must be Tier 2, never Tier 1.
    """
    s = _resolved_hypo_state(
        a_able_to_swallow_safely=TriState.YES,
        a_able_to_self_treat_unaided=TriState.YES,
        a_frequent_or_past_severe_or_impaired_awareness=TriState.NO,
        a_mild_symptoms=TriState.NO,  # nothing in category A fires
    )
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 2
    assert result.safety_net is True
    assert "SN3" in result.fired_rule_ids


def test_other_category_with_no_rules_falls_back_to_sn3():
    s = ClinicalState()
    s.unconscious_or_not_responding = TriState.NO
    s.non_diabetes_emergency_signs = TriState.NO
    s.pregnant = TriState.NO
    s.presenting_complaint = PresentingComplaint.OTHER
    result = engine.evaluate(s)
    assert isinstance(result, Verdict)
    assert result.tier == 2
    assert result.fired_rule_ids == ("SN3",)


def test_needs_info_requests_category_only_after_global_overrides_clear():
    s = ClinicalState()  # nothing resolved at all
    result = engine.evaluate(s)
    assert isinstance(result, NeedsInfo)
    assert result.slot != "presenting_complaint"  # must resolve G1/SN1/SN2 first
