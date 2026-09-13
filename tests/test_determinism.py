"""The same clinical state must produce the same outcome, every time — no
model, no randomness, no hidden state in the engine.
"""

from __future__ import annotations

from diabetes_chatbot.engine import engine
from diabetes_chatbot.engine.types import NeedsInfo, Verdict
from diabetes_chatbot.state import ClinicalState, PresentingComplaint, TriState


def _make_states():
    fired_state = ClinicalState()
    fired_state.unconscious_or_not_responding = TriState.YES

    verdict_state = ClinicalState()
    verdict_state.unconscious_or_not_responding = TriState.NO
    verdict_state.non_diabetes_emergency_signs = TriState.NO
    verdict_state.pregnant = TriState.NO
    verdict_state.presenting_complaint = PresentingComplaint.FOOT
    verdict_state.d_stable_non_infected = TriState.YES
    verdict_state.d_infection_signs = TriState.NO
    verdict_state.d_severe_signs = TriState.NO

    needs_info_state = ClinicalState()
    needs_info_state.presenting_complaint = PresentingComplaint.HYPOGLYCEMIA
    needs_info_state.unconscious_or_not_responding = TriState.NO
    needs_info_state.non_diabetes_emergency_signs = TriState.NO
    needs_info_state.pregnant = TriState.NO

    return [fired_state, verdict_state, needs_info_state]


def test_evaluate_is_deterministic_across_many_repeated_calls():
    for state in _make_states():
        results = [engine.evaluate(state) for _ in range(200)]
        first = results[0]
        for r in results[1:]:
            assert type(r) is type(first)
            if isinstance(r, Verdict):
                assert r == first
            elif isinstance(r, NeedsInfo):
                assert r == first


def test_evaluate_result_is_identical_for_independently_constructed_equal_states():
    def build():
        s = ClinicalState()
        s.unconscious_or_not_responding = TriState.NO
        s.non_diabetes_emergency_signs = TriState.NO
        s.pregnant = TriState.NO
        s.presenting_complaint = PresentingComplaint.FOOT
        s.d_stable_non_infected = TriState.YES
        s.d_infection_signs = TriState.NO
        s.d_severe_signs = TriState.NO
        return s

    result_a = engine.evaluate(build())
    result_b = engine.evaluate(build())
    assert result_a == result_b


def test_same_clinical_situation_described_two_ways_yields_the_same_tier():
    """This is the concrete DKA-boundary claim: two different extraction
    paths that land on the same clinical slots must yield the same tier.
    """
    def hypo_state_from_extraction_a():
        s = ClinicalState()
        s.unconscious_or_not_responding = TriState.NO
        s.non_diabetes_emergency_signs = TriState.NO
        s.pregnant = TriState.NO
        s.presenting_complaint = PresentingComplaint.HYPOGLYCEMIA
        s.a_able_to_swallow_safely = TriState.NO  # "can't swallow"
        return s

    def hypo_state_from_extraction_b():
        s = ClinicalState()
        s.unconscious_or_not_responding = TriState.NO
        s.non_diabetes_emergency_signs = TriState.NO
        s.pregnant = TriState.NO
        s.presenting_complaint = PresentingComplaint.HYPOGLYCEMIA
        s.a_able_to_swallow_safely = TriState.NO  # "unable to swallow safely"
        return s

    result_a = engine.evaluate(hypo_state_from_extraction_a())
    result_b = engine.evaluate(hypo_state_from_extraction_b())
    assert result_a == result_b
    assert isinstance(result_a, Verdict)
    assert result_a.tier == 3
