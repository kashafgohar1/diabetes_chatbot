"""One pure function per protocol rule ID.

STRUCTURAL SAFETY BOUNDARY: this module (and engine.py, types.py) must never
import an LLM client, any network library, or diabetes_chatbot.extraction.
tests/test_engine_boundary.py parses this package's AST and fails the build
if that import boundary is crossed — that test is the safety argument.

Every function here:
  * takes only a diabetes_chatbot.state.ClinicalState,
  * returns only a diabetes_chatbot.engine.types.RuleResult,
  * names its protocol rule ID in its docstring,
  * has a dedicated test in tests/test_rules.py named so that
    `pytest -k <RULE_ID>` selects it.

Tri-state discipline: a rule never treats UNKNOWN as NO. If a needed slot is
UNKNOWN, the rule returns CANNOT_DETERMINE and names the slot that would
resolve it — that is what lets the engine ask instead of guessing (OQ-9).
"""

from __future__ import annotations

from diabetes_chatbot.state import ClinicalState, PresentingComplaint, TriState

from .types import RuleOutcome, RuleResult

FIRES = RuleOutcome.FIRES
NO_FIRE = RuleOutcome.DOES_NOT_FIRE
CANNOT = RuleOutcome.CANNOT_DETERMINE


# ---------------------------------------------------------------------------
# Category A — severe hypoglycemia
# ---------------------------------------------------------------------------


def rule_a1(state: ClinicalState) -> RuleResult:
    """Protocol rule A1 (severe hypoglycemia -> Tier 1). Source: REF-01, REF-05.

    Mild/moderate symptoms (shaky, hungry, sweaty, mildly confused); able to
    self-treat and swallow safely.
    """
    mild = state.a_mild_symptoms
    if mild is TriState.NO:
        return RuleResult("A1", NO_FIRE, None, reason="no mild hypoglycemia symptoms reported")
    if mild is TriState.UNKNOWN:
        return RuleResult("A1", CANNOT, tier=1, needed_slot="a_mild_symptoms")

    swallow = state.a_able_to_swallow_safely
    if swallow is TriState.NO:
        return RuleResult("A1", NO_FIRE, None, reason="not able to swallow safely")
    if swallow is TriState.UNKNOWN:
        return RuleResult("A1", CANNOT, tier=1, needed_slot="a_able_to_swallow_safely")

    self_treat = state.a_able_to_self_treat_unaided
    if self_treat is TriState.NO:
        return RuleResult("A1", NO_FIRE, None, reason="not able to self-treat unaided")
    if self_treat is TriState.UNKNOWN:
        return RuleResult("A1", CANNOT, tier=1, needed_slot="a_able_to_self_treat_unaided")

    return RuleResult(
        "A1", FIRES, tier=1,
        reason="mild hypoglycemia symptoms, able to self-treat and swallow safely",
    )


def rule_a2(state: ClinicalState) -> RuleResult:
    """Protocol rule A2 (severe hypoglycemia -> Tier 2). Source: REF-05.

    Frequent hypos, past severe hypos, night hypos, or impaired awareness of
    symptoms.
    """
    slot = state.a_frequent_or_past_severe_or_impaired_awareness
    if slot is TriState.NO:
        return RuleResult("A2", NO_FIRE, None, reason="no history of frequent/severe/night hypos or impaired awareness")
    if slot is TriState.UNKNOWN:
        return RuleResult(
            "A2", CANNOT, tier=2,
            needed_slot="a_frequent_or_past_severe_or_impaired_awareness",
        )
    return RuleResult("A2", FIRES, tier=2, reason="frequent/past severe/night hypos or impaired awareness")


def rule_a3(state: ClinicalState) -> RuleResult:
    """Protocol rule A3 (severe hypoglycemia -> Tier 3). Source: REF-01, REF-05.

    Loss of consciousness, seizure, unable to swallow safely, or not
    responding normally.
    """
    unconscious = state.unconscious_or_not_responding
    if unconscious is TriState.YES:
        return RuleResult("A3", FIRES, tier=3, reason="loss of consciousness / seizure / not responding")
    if unconscious is TriState.UNKNOWN:
        return RuleResult("A3", CANNOT, tier=3, needed_slot="unconscious_or_not_responding")

    # unconscious is NO — check the "unable to swallow safely" clause
    swallow = state.a_able_to_swallow_safely
    if swallow is TriState.NO:
        return RuleResult("A3", FIRES, tier=3, reason="unable to swallow safely")
    if swallow is TriState.UNKNOWN:
        return RuleResult("A3", CANNOT, tier=3, needed_slot="a_able_to_swallow_safely")

    return RuleResult("A3", NO_FIRE, None, reason="conscious, responding normally, able to swallow safely")


def rule_a4(state: ClinicalState) -> RuleResult:
    """Protocol rule A4 (severe hypoglycemia -> Tier 3; INVENTED, closes OQ-4).

    Not in the original draft. Conscious, able to swallow safely, but unable
    to get to sugar/treatment unaided — satisfies neither A1 nor A3 and
    would otherwise fall through to a lower tier.
    """
    unconscious = state.unconscious_or_not_responding
    if unconscious is TriState.YES:
        return RuleResult("A4", NO_FIRE, None, reason="A3 applies instead (unconscious/not responding)", invented=True)
    if unconscious is TriState.UNKNOWN:
        return RuleResult("A4", CANNOT, tier=3, needed_slot="unconscious_or_not_responding", invented=True)

    swallow = state.a_able_to_swallow_safely
    if swallow is TriState.NO:
        return RuleResult("A4", NO_FIRE, None, reason="A3 applies instead (cannot swallow safely)", invented=True)
    if swallow is TriState.UNKNOWN:
        return RuleResult("A4", CANNOT, tier=3, needed_slot="a_able_to_swallow_safely", invented=True)

    self_treat = state.a_able_to_self_treat_unaided
    if self_treat is TriState.NO:
        return RuleResult(
            "A4", FIRES, tier=3, invented=True,
            reason="conscious and able to swallow, but cannot reach sugar/treatment unaided",
        )
    if self_treat is TriState.UNKNOWN:
        return RuleResult("A4", CANNOT, tier=3, needed_slot="a_able_to_self_treat_unaided", invented=True)

    return RuleResult("A4", NO_FIRE, None, reason="able to reach treatment unaided", invented=True)


# ---------------------------------------------------------------------------
# Category B — DKA / severe hyperglycemia
# ---------------------------------------------------------------------------


def rule_b1(state: ClinicalState) -> RuleResult:
    """Protocol rule B1 (DKA/hyperglycemia -> Tier 2). Source: REF-03.

    Isolated hyperglycemia symptoms (thirst, fatigue, frequent urination,
    blurred vision); no vomiting, breathing change or confusion. This is an
    absence rule (OQ-9): the DKA red-flag slot must have been asked and
    answered NO, never left UNKNOWN, before B1 can fire.
    """
    isolated = state.b_isolated_hyperglycemia_symptoms
    if isolated is TriState.NO:
        return RuleResult("B1", NO_FIRE, None, reason="no isolated hyperglycemia symptoms reported")
    if isolated is TriState.UNKNOWN:
        return RuleResult("B1", CANNOT, tier=2, needed_slot="b_isolated_hyperglycemia_symptoms")

    red_flags = state.b_dka_red_flags
    if red_flags is TriState.YES:
        return RuleResult("B1", NO_FIRE, None, reason="DKA red flags present — B2 applies instead")
    if red_flags is TriState.UNKNOWN:
        # Evidence of absence required (OQ-9) — cannot conclude B1 fires yet,
        # and the missing info could also mean B2 (Tier 3), so ask.
        return RuleResult("B1", CANNOT, tier=2, needed_slot="b_dka_red_flags")

    return RuleResult("B1", FIRES, tier=2, reason="isolated hyperglycemia symptoms, no DKA red flags")


def rule_b2(state: ClinicalState) -> RuleResult:
    """Protocol rule B2 (DKA/hyperglycemia -> Tier 3). Source: REF-02, REF-06.

    Persistent vomiting, abdominal pain, fruity breath, deep/fast breathing,
    confusion or drowsiness, known high ketones, OR any DKA-type symptom in
    a person with no diabetes diagnosis.
    """
    red_flags = state.b_dka_red_flags
    if red_flags is TriState.YES:
        return RuleResult("B2", FIRES, tier=3, reason="DKA red flag symptom(s) present")
    if red_flags is TriState.UNKNOWN:
        return RuleResult("B2", CANNOT, tier=3, needed_slot="b_dka_red_flags")

    # red_flags is NO — still fires if hyperglycemia symptoms occur with no
    # prior diabetes diagnosis (undiagnosed DKA-risk clause).
    isolated = state.b_isolated_hyperglycemia_symptoms
    diagnosed = state.diabetes_diagnosed
    if isolated is TriState.YES and diagnosed is TriState.NO:
        return RuleResult(
            "B2", FIRES, tier=3,
            reason="hyperglycemia-type symptom in a person with no diabetes diagnosis",
        )
    if isolated is TriState.YES and diagnosed is TriState.UNKNOWN:
        return RuleResult("B2", CANNOT, tier=3, needed_slot="diabetes_diagnosed")

    return RuleResult("B2", NO_FIRE, None, reason="no DKA red flags")


# ---------------------------------------------------------------------------
# Category C — possible undiagnosed diabetes
# ---------------------------------------------------------------------------


def rule_c1(state: ClinicalState) -> RuleResult:
    """Protocol rule C1 (undiagnosed -> Tier 2 per OQ-1). Source: REF-02, REF-09.

    Increased thirst/urination/hunger, fatigue, blurred vision, unexplained
    weight loss, slow-healing sores — no red flags. Draft says "1/2";
    implemented as Tier 2 per G4 (OQ-1). Absence rule (OQ-9): red flags must
    be asked and answered NO, never inferred from silence.
    """
    new_symptoms = state.c_new_symptoms
    if new_symptoms is TriState.NO:
        return RuleResult("C1", NO_FIRE, None, reason="no new undiagnosed-diabetes symptoms reported")
    if new_symptoms is TriState.UNKNOWN:
        return RuleResult("C1", CANNOT, tier=2, needed_slot="c_new_symptoms")

    red_flags = state.c_red_flags
    if red_flags is TriState.YES:
        return RuleResult("C1", NO_FIRE, None, reason="red flags present — C2 applies instead")
    if red_flags is TriState.UNKNOWN:
        return RuleResult("C1", CANNOT, tier=2, needed_slot="c_red_flags")

    return RuleResult(
        "C1", FIRES, tier=2,
        reason="possible undiagnosed diabetes symptoms, no red flags (OQ-1: implemented as Tier 2)",
    )


def rule_c2(state: ClinicalState) -> RuleResult:
    """Protocol rule C2 (undiagnosed -> Tier 3). Source: REF-07.

    Any C1-type symptom plus rapid worsening, vomiting/diarrhoea, stomach
    pain, drowsiness/confusion, or fast/deep breathing.
    """
    red_flags = state.c_red_flags
    if red_flags is TriState.YES:
        return RuleResult("C2", FIRES, tier=3, reason="undiagnosed-diabetes symptoms with red flags")
    if red_flags is TriState.UNKNOWN:
        return RuleResult("C2", CANNOT, tier=3, needed_slot="c_red_flags")
    return RuleResult("C2", NO_FIRE, None, reason="no red flags")


# ---------------------------------------------------------------------------
# Category D — foot problems
# ---------------------------------------------------------------------------


def rule_d1(state: ClinicalState) -> RuleResult:
    """Protocol rule D1 (foot -> Tier 1). Source: REF-04.

    Stable, non-infected wound or general foot discomfort.
    """
    stable = state.d_stable_non_infected
    if stable is TriState.NO:
        return RuleResult("D1", NO_FIRE, None, reason="foot problem not stable/non-infected")
    if stable is TriState.UNKNOWN:
        return RuleResult("D1", CANNOT, tier=1, needed_slot="d_stable_non_infected")

    infection = state.d_infection_signs
    if infection is TriState.YES:
        return RuleResult("D1", NO_FIRE, None, reason="infection signs present — D2 applies instead")
    if infection is TriState.UNKNOWN:
        return RuleResult("D1", CANNOT, tier=1, needed_slot="d_infection_signs")

    severe = state.d_severe_signs
    if severe is TriState.YES:
        return RuleResult("D1", NO_FIRE, None, reason="severe signs present — D3 applies instead")
    if severe is TriState.UNKNOWN:
        return RuleResult("D1", CANNOT, tier=1, needed_slot="d_severe_signs")

    return RuleResult("D1", FIRES, tier=1, reason="stable, non-infected foot problem")


def rule_d2(state: ClinicalState) -> RuleResult:
    """Protocol rule D2 (foot -> Tier 2). Source: REF-04 (indirect).

    Signs of infection (redness, swelling, warmth, discharge, odour) or a
    wound not healing.
    """
    infection = state.d_infection_signs
    if infection is TriState.NO:
        return RuleResult("D2", NO_FIRE, None, reason="no infection signs reported")
    if infection is TriState.UNKNOWN:
        return RuleResult("D2", CANNOT, tier=2, needed_slot="d_infection_signs")

    severe = state.d_severe_signs
    if severe is TriState.YES:
        return RuleResult("D2", NO_FIRE, None, reason="severe signs present — D3 applies instead")
    if severe is TriState.UNKNOWN:
        return RuleResult("D2", CANNOT, tier=2, needed_slot="d_severe_signs")

    return RuleResult("D2", FIRES, tier=2, reason="signs of foot infection or non-healing wound")


def rule_d3(state: ClinicalState) -> RuleResult:
    """Protocol rule D3 (foot -> Tier 3; UNSOURCED in the draft). Source: none (OQ-2).

    Rapidly spreading redness, fever, or foot differs markedly in
    colour/temperature from the other foot.
    """
    severe = state.d_severe_signs
    if severe is TriState.YES:
        return RuleResult("D3", FIRES, tier=3, unsourced=True, reason="rapidly spreading redness/fever/marked colour-temperature difference")
    if severe is TriState.UNKNOWN:
        return RuleResult("D3", CANNOT, tier=3, needed_slot="d_severe_signs", unsourced=True)
    return RuleResult("D3", NO_FIRE, None, unsourced=True, reason="no severe foot signs")


# ---------------------------------------------------------------------------
# Global overrides
# ---------------------------------------------------------------------------


def rule_g1(state: ClinicalState) -> RuleResult:
    """Protocol rule G1 (global override -> Tier 3). Source: PROFESSOR.

    Any mention of unconsciousness, seizure, "can't wake up", or "not
    responding", at any point in the conversation. Supersedes everything
    else — the pipeline checks this before any other rule, every turn.
    """
    unconscious = state.unconscious_or_not_responding
    if unconscious is TriState.YES:
        return RuleResult("G1", FIRES, tier=3, reason="unconscious / seizure / not responding mentioned")
    if unconscious is TriState.UNKNOWN:
        return RuleResult("G1", CANNOT, tier=3, needed_slot="unconscious_or_not_responding")
    return RuleResult("G1", NO_FIRE, None, reason="no unconscious/not-responding red flag detected")


def rule_g2(state: ClinicalState) -> RuleResult:
    """Protocol rule G2 (global override -> refuse). Source: PROFESSOR.

    Any request for an insulin/medication dose calculation or suggestion,
    under any framing.
    """
    if state.insulin_dose_request_detected:
        return RuleResult("G2", FIRES, tier=None, action="refuse_gracefully", reason="insulin/dose request detected")
    return RuleResult("G2", NO_FIRE, None, reason="no dose request detected")


def rule_g4_would_ambiguity_permit_higher_tier(
    candidate_results: list[RuleResult], current_best_tier: int
) -> bool:
    """Structural helper for G4 (see engine.evaluate for the real
    implementation): true if any CANNOT_DETERMINE rule's candidate tier is
    >= current_best_tier, meaning the engine must ask rather than conclude.
    """
    return any(
        r.outcome is CANNOT and r.tier is not None and r.tier >= current_best_tier
        for r in candidate_results
    )


# ---------------------------------------------------------------------------
# Engineering safety nets (not in the draft — flagged invented on every use)
# ---------------------------------------------------------------------------


def rule_sn1_non_diabetes_emergency(state: ClinicalState) -> RuleResult:
    """Engineering safety net SN1 (-> Tier 3; INVENTED, not in the draft).

    Non-diabetes emergency (chest pain, stroke signs, severe breathing
    difficulty). The bot only handles diabetes triage — escalate and exit.
    """
    signs = state.non_diabetes_emergency_signs
    if signs is TriState.YES:
        return RuleResult("SN1", FIRES, tier=3, invented=True, reason="non-diabetes emergency signs reported")
    if signs is TriState.UNKNOWN:
        return RuleResult("SN1", CANNOT, tier=3, needed_slot="non_diabetes_emergency_signs", invented=True)
    return RuleResult("SN1", NO_FIRE, None, invented=True, reason="no non-diabetes emergency signs")


def rule_sn2_pregnancy(state: ClinicalState) -> RuleResult:
    """Engineering safety net SN2 (-> Tier 3; INVENTED, not in the draft).

    Pregnancy declared — out of scope, every threshold changes in
    pregnancy. Escalate and exit.
    """
    pregnant = state.pregnant
    if pregnant is TriState.YES:
        return RuleResult("SN2", FIRES, tier=3, invented=True, reason="pregnancy declared — out of scope")
    if pregnant is TriState.UNKNOWN:
        return RuleResult("SN2", CANNOT, tier=3, needed_slot="pregnant", invented=True)
    return RuleResult("SN2", NO_FIRE, None, invented=True, reason="not pregnant")


def rule_sn3_fallback_safety_net(unresolved: bool) -> RuleResult:
    """Engineering safety net SN3 (-> Tier 2; INVENTED, not in the draft).

    Nothing fires and no further question would change the outcome. G4
    forbids defaulting to Tier 1, so the floor is Tier 2 with
    safety-netting advice.
    """
    if unresolved:
        return RuleResult("SN3", NO_FIRE, None, invented=True, reason="an unresolved rule remains")
    return RuleResult("SN3", FIRES, tier=2, invented=True, reason="no rule fired and nothing left to ask — safety-net floor")
