"""Deterministic, network-free text-matching lexicon shared by the red-flag
prefilter and the offline keyword extractor.

Matching order per concept — this is the fix for two known regression bugs:

  1. "Negation ordering" bug: a button/free-text reply like "Not high"
     matched the bare positive keyword "high" first, producing a false
     positive. Fixed by checking `negation_patterns` BEFORE
     `positive_keywords`.
  2. "Red-flag lexicon recall" bug: "not waking up properly" was intended
     as a POSITIVE symptom report (an idiom meaning unresponsive) but a
     naive negation check would treat the leading "not" as negating it.
     Fixed by checking `explicit_positive_phrases` (fixed idioms, where the
     word "not"/"won't"/"can't" is part of the symptom phrase itself)
     BEFORE `negation_patterns` runs at all.

So the order is always: explicit_positive_phrases -> negation_patterns ->
explicit_negative_phrases -> positive_keywords -> UNKNOWN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .state import Role, TriState


@dataclass(frozen=True)
class Concept:
    name: str
    explicit_positive_phrases: tuple[str, ...] = ()
    negation_patterns: tuple[str, ...] = ()
    explicit_negative_phrases: tuple[str, ...] = ()
    positive_keywords: tuple[str, ...] = ()


def _contains_phrase(text: str, phrase: str) -> bool:
    if " " in phrase or "-" in phrase or "'" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def detect(text: str, concept: Concept) -> TriState:
    t = text.lower().replace("’", "'")

    for phrase in concept.explicit_positive_phrases:
        if _contains_phrase(t, phrase):
            return TriState.YES

    for pattern in concept.negation_patterns:
        if re.search(pattern, t):
            return TriState.NO

    for phrase in concept.explicit_negative_phrases:
        if _contains_phrase(t, phrase):
            return TriState.NO

    for phrase in concept.positive_keywords:
        if _contains_phrase(t, phrase):
            return TriState.YES

    return TriState.UNKNOWN


# ---------------------------------------------------------------------------
# Global-override / red-flag concepts
# ---------------------------------------------------------------------------

UNCONSCIOUS_OR_NOT_RESPONDING = Concept(
    name="unconscious_or_not_responding",
    explicit_positive_phrases=(
        "not waking up properly", "not waking up", "not waking",
        "won't wake up", "wont wake up", "won't wake", "wont wake",
        "can't wake", "cant wake", "cannot wake", "can't rouse", "cant rouse",
        "not responding normally", "not responding", "won't respond", "wont respond",
        "unresponsive", "not conscious", "losing consciousness", "lost consciousness",
        "passed out", "collapsed", "seizure", "convulsion", "convulsing", "fitting",
        "having a fit", "blacked out", "not waking her up", "not waking him up",
    ),
    negation_patterns=(
        r"\bnot\b[^.,;!?]{0,25}\b(unconscious|seizure|convulsing)\b",
        r"\bno\b[^.,;!?]{0,25}\b(seizure|unconscious|convulsion)\b",
        r"isn'?t\s+unconscious",
    ),
    positive_keywords=("unconscious", "seizure"),
)

NON_DIABETES_EMERGENCY = Concept(
    name="non_diabetes_emergency",
    explicit_positive_phrases=(
        "chest pain", "crushing chest pain", "can't breathe", "cant breathe",
        "cannot breathe", "difficulty breathing", "severe difficulty breathing",
        "trouble breathing", "struggling to breathe", "gasping for air",
        "face drooping", "face is drooping", "slurred speech", "weakness on one side",
        "one side of the body is weak", "sudden severe headache", "worst headache",
        "heart attack", "can't move one side", "cant move one side",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,25}\bchest pain\b",
        r"\bnot\b[^.,;!?]{0,25}\bchest pain\b",
        r"\bno\b[^.,;!?]{0,25}\bdifficulty breathing\b",
    ),
    positive_keywords=("stroke",),
)

PREGNANCY = Concept(
    name="pregnancy",
    explicit_positive_phrases=(
        "pregnant", "pregnancy", "expecting a baby", "she's expecting", "shes expecting",
        "she is expecting",
    ),
    negation_patterns=(
        r"\bnot\b[^.,;!?]{0,20}\bpregnant\b",
        r"\bno\b[^.,;!?]{0,20}\bpregnant\b",
        r"isn'?t\s+pregnant",
    ),
)

# ---------------------------------------------------------------------------
# Clinical slot concepts (category A/B/C/D)
# ---------------------------------------------------------------------------

A_MILD_SYMPTOMS = Concept(
    name="a_mild_symptoms",
    explicit_positive_phrases=("feeling shaky", "feel shaky", "sweating a lot"),
    negation_patterns=(
        r"\bnot\b[^.,;!?]{0,20}\b(shaky|hungry|sweaty|confused)\b",
        r"\bno\b[^.,;!?]{0,20}\b(shakiness|confusion|sweating)\b",
    ),
    positive_keywords=("shaky", "shakiness", "hungry", "sweaty", "sweating", "mildly confused", "trembling", "dizzy"),
)

A_ABLE_TO_SWALLOW_SAFELY = Concept(
    name="a_able_to_swallow_safely",
    explicit_positive_phrases=("can swallow", "able to swallow", "swallowing fine", "drinking juice fine"),
    negation_patterns=(
        r"\b(can'?t|cannot|unable to|not able to)\b[^.,;!?]{0,20}\bswallow\b",
    ),
    positive_keywords=("swallowing normally", "swallowing ok", "swallowing okay"),
)

A_ABLE_TO_SELF_TREAT_UNAIDED = Concept(
    name="a_able_to_self_treat_unaided",
    explicit_positive_phrases=(
        "can get to sugar", "can get some juice", "has juice nearby", "someone is helping",
        "can reach", "got some sugar",
    ),
    negation_patterns=(
        r"\b(can'?t|cannot|unable to|not able to)\b[^.,;!?]{0,30}\b(reach|get to|get)\b",
        r"\balone\b[^.,;!?]{0,20}\bno ?one\b",
        r"\bno ?one (else )?(is )?(around|home|there|available)\b",
    ),
    positive_keywords=(),
)

A_FREQUENT_OR_PAST_SEVERE_OR_IMPAIRED_AWARENESS = Concept(
    name="a_frequent_or_past_severe_or_impaired_awareness",
    explicit_positive_phrases=(
        "happens a lot", "happens often", "keeps happening", "frequent hypos", "frequent lows",
        "night hypos", "hypos at night", "low at night", "doesn't feel it coming",
        "doesn't feel it coming on", "no warning before it happens", "can't tell when it's low",
        "cant tell when it's low", "had this before", "happened before", "hospital before for this",
    ),
    negation_patterns=(
        r"\b(first time|never happened before|no history)\b",
    ),
    positive_keywords=("recurrent", "recurring"),
)

B_ISOLATED_HYPERGLYCEMIA_SYMPTOMS = Concept(
    name="b_isolated_hyperglycemia_symptoms",
    explicit_positive_phrases=(
        "very thirsty", "always thirsty", "peeing a lot", "urinating a lot",
        "frequent urination", "blurry vision", "blurred vision", "sugar is high",
        "glucose is high", "reading is high", "very tired lately",
    ),
    negation_patterns=(
        r"\bnot\b[^.,;!?]{0,20}\bhigh\b",
        r"\bno\b[^.,;!?]{0,20}\bhigh\b",
        r"isn'?t\s+high",
    ),
    positive_keywords=("thirsty", "thirst", "fatigue"),
)

B_DKA_RED_FLAGS = Concept(
    name="b_dka_red_flags",
    explicit_positive_phrases=(
        "throwing up", "vomiting", "keeps vomiting", "fruity breath", "fruity smell",
        "breathing fast", "breathing very fast", "deep breathing", "hard to breathe",
        "stomach pain", "abdominal pain", "belly pain", "very drowsy", "hard to wake",
        "high ketones", "ketones are high", "confused today",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,25}\b(vomiting|abdominal pain|stomach pain|confusion)\b",
        r"\bnot\b[^.,;!?]{0,25}\b(vomiting|confused|drowsy)\b",
    ),
    positive_keywords=("vomit", "drowsy", "drowsiness"),
)

C_NEW_SYMPTOMS = Concept(
    name="c_new_symptoms",
    explicit_positive_phrases=(
        "losing weight", "lost weight", "weight loss", "sores that won't heal",
        "sores that wont heal", "wounds that won't heal", "slow healing", "blurry vision",
        "blurred vision", "very thirsty", "peeing a lot", "urinating a lot", "always hungry",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,20}\b(symptoms|weight loss)\b",
    ),
    positive_keywords=("thirst", "fatigue", "hunger"),
)

C_RED_FLAGS = Concept(
    name="c_red_flags",
    explicit_positive_phrases=(
        "getting worse fast", "rapidly worse", "throwing up", "vomiting", "diarrhoea",
        "diarrhea", "stomach pain", "very confused", "drowsy", "breathing fast",
        "breathing hard", "deep breathing",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,25}\b(vomiting|diarrhoea|diarrhea|stomach pain|confusion)\b",
    ),
    positive_keywords=("confusion",),
)

D_STABLE_NON_INFECTED = Concept(
    name="d_stable_non_infected",
    explicit_positive_phrases=("just a bit sore", "minor discomfort", "looks fine", "no redness"),
    negation_patterns=(
        r"\b(worse|worsening|spreading|infected)\b",
    ),
    positive_keywords=("stable", "comfortable", "mild"),
)

D_INFECTION_SIGNS = Concept(
    name="d_infection_signs",
    explicit_positive_phrases=(
        "not healing", "won't heal", "wont heal", "discharge", "pus", "bad smell",
        "smells bad", "warm to touch", "swollen",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,20}\b(redness|swelling|discharge|smell|infection)\b",
    ),
    positive_keywords=("redness", "swelling", "warmth", "odour", "odor", "infected"),
)

D_SEVERE_SIGNS = Concept(
    name="d_severe_signs",
    explicit_positive_phrases=(
        "spreading fast", "spreading quickly", "rapidly spreading", "red line spreading",
        "colour is different", "color is different", "much darker than the other foot",
        "cold compared to the other foot", "hot compared to the other foot",
        "very different from the other foot",
    ),
    negation_patterns=(
        r"\bno\b[^.,;!?]{0,20}\bfever\b",
    ),
    positive_keywords=("fever",),
)

DIABETES_DIAGNOSED = Concept(
    name="diabetes_diagnosed",
    explicit_positive_phrases=(
        "diagnosed with diabetes", "have diabetes", "has diabetes", "type 1 diabetic",
        "type 2 diabetic", "type 1 diabetes", "type 2 diabetes", "diabetic",
    ),
    negation_patterns=(
        r"\bnot\b[^.,;!?]{0,20}\bdiabetic\b",
        r"\bno\b[^.,;!?]{0,20}\bdiabetes\b",
        r"\bnever\b[^.,;!?]{0,20}\bdiagnosed\b",
        r"\bdon'?t have diabetes\b",
        r"\bdoesn'?t have diabetes\b",
    ),
)


# ---------------------------------------------------------------------------
# Role detection — caregiver phrases are checked BEFORE any patient pattern.
# Regression fix: "someone else" contains the substring "me", so a plain
# substring check for "me" wrongly classified it as the patient. Word-
# boundary regex plus caregiver-first ordering fixes this.
# ---------------------------------------------------------------------------

_CAREGIVER_PHRASES = (
    "someone else", "my mother", "my father", "my mom", "my dad", "my husband",
    "my wife", "my son", "my daughter", "my grandmother", "my grandfather",
    "my grandma", "my grandpa", "my parent", "my aunt", "my uncle", "my sister",
    "my brother", "my child", "my elderly", "on behalf of", "for my", "he is",
    "she is", "they are", "my patient", "looking after", "caring for", "caregiver",
    "family member", "not for me", "not me",
)

_PATIENT_PATTERNS = (
    r"\bi am\b", r"\bi'm\b", r"\bim\b", r"\bmyself\b", r"\bi have\b", r"\bi feel\b",
    r"\bme\b", r"\bmy own\b", r"\bi'?ve been\b",
)


def detect_role(text: str) -> Role | None:
    t = text.lower().replace("’", "'")
    for phrase in _CAREGIVER_PHRASES:
        if phrase in t:
            return Role.CAREGIVER
    for pattern in _PATIENT_PATTERNS:
        if re.search(pattern, t):
            return Role.PATIENT
    return None


# ---------------------------------------------------------------------------
# Insulin / medication dose request detection (G2) — request detector, not a
# tri-state clinical fact, so it lives outside the Concept machinery.
# ---------------------------------------------------------------------------

_DOSE_REQUEST_PHRASES = (
    "how much insulin", "how many units of insulin", "how many units should i take",
    "how many units should he take", "how many units should she take",
    "insulin dose", "dose of insulin", "increase my insulin", "increase his insulin",
    "increase her insulin", "how much insulin should i take", "units of insulin should i take",
    "how many units", "what dose of insulin", "insulin dosage", "how much metformin",
    "how many units of humalog", "how many units of lantus", "how much lantus",
    "how much humalog", "novorapid dose", "lantus dose", "increase the insulin",
    "decrease the insulin", "reduce the insulin", "stop taking insulin", "stop the insulin",
    "double the dose", "double my dose", "how many mg should i take", "adjust my insulin",
    "change my dose", "what should my dose be", "calculate my insulin",
    "correction dose", "correction factor", "how much should i inject",
)

_DOSE_REQUEST_PATTERNS = (
    r"how (much|many)[^.,;!?]{0,25}\b(insulin|units?|dose|dosage|mg|milligrams?)\b",
    r"\b(insulin|dose|dosage)\b[^.,;!?]{0,20}should i (take|give|use|inject)",
)


def detect_insulin_dose_request(text: str) -> bool:
    t = text.lower().replace("’", "'")
    for phrase in _DOSE_REQUEST_PHRASES:
        if phrase in t:
            return True
    for pattern in _DOSE_REQUEST_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


# ---------------------------------------------------------------------------
# Glucose value + unit extraction (OQ-8: captured only, never acted on).
# Bare numbers with no unit are flagged ambiguous rather than guessed.
# ---------------------------------------------------------------------------

_MGDL_PATTERNS = (r"mg\s*/?\s*d\s*l", r"\bmg/dl\b", r"\bmgdl\b")
_MMOL_PATTERNS = (r"mmol\s*/?\s*l", r"\bmmol/l\b", r"\bmmol\b")
_NUMBER_PATTERN = re.compile(r"(?<![a-zA-Z])(\d{1,3}(?:\.\d+)?)(?![a-zA-Z])")


def extract_glucose_reading(text: str) -> tuple[float | None, str | None, bool]:
    """Returns (value, unit, ambiguous). unit is 'mg/dL', 'mmol/L', or None.
    ambiguous is True iff a number was found but no unit was stated.
    """
    t = text.lower()
    match = _NUMBER_PATTERN.search(t)
    if not match:
        return None, None, False
    value = float(match.group(1))
    for pat in _MGDL_PATTERNS:
        if re.search(pat, t):
            return value, "mg/dL", False
    for pat in _MMOL_PATTERNS:
        if re.search(pat, t):
            return value, "mmol/L", False
    return value, None, True
