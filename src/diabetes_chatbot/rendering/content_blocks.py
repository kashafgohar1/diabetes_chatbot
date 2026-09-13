"""Approved content blocks — the ONLY source of outbound wording.

Every one of these is a fixed, pre-written template. The renderer selects a
block and fills role/trigger-list placeholders; an LLM, if used at all, may
only rephrase a selected block's surface wording (see rendering/renderer.py
`llm_rephrase`, which is a no-op unless explicitly enabled) — it never
authors new clinical content and never sees a tier and never decides
anything.

All of this is PENDING_CLINICAL_REVIEW wording. See docs/CLINICIAN_REVIEW.md
for the list of wording decisions that need clinician sign-off.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import PROTOTYPE_BANNER
from ..state import Role

Button = tuple[str, str]  # (label shown to user, value sent back)


@dataclass(frozen=True)
class Question:
    patient_text: str
    caregiver_text: str
    buttons: tuple[Button, ...]

    def text_for(self, role: Role | None) -> str:
        if role is Role.CAREGIVER:
            return self.caregiver_text
        return self.patient_text


YES_NO_UNSURE: tuple[Button, ...] = (("Yes", "yes"), ("No", "no"), ("Not sure", "unknown"))

# ---------------------------------------------------------------------------
# Session preamble
# ---------------------------------------------------------------------------

CONSENT_QUESTION = Question(
    patient_text=(
        "Hi, I'm a prototype diabetes triage assistant. I can help figure out "
        "how urgently you should be seen — I do not diagnose, prescribe, or "
        "replace a clinician. Do you agree to continue?"
    ),
    caregiver_text=(
        "Hi, I'm a prototype diabetes triage assistant. I can help figure out "
        "how urgently the person you're asking about should be seen — I do "
        "not diagnose, prescribe, or replace a clinician. Do you agree to "
        "continue?"
    ),
    buttons=(("I agree", "yes"), ("I do not agree", "no")),
)

CONSENT_DECLINED_EXIT = (
    "Understood — no further questions will be asked. If this is ever a "
    "medical emergency, please go to the nearest hospital immediately."
)

AGE_QUESTION = Question(
    patient_text="Are you 18 years old or older?",
    caregiver_text="Is the patient 18 years old or older?",
    buttons=(("Yes, 18 or older", "yes"), ("No, under 18", "no")),
)

UNDER_18_EXIT = (
    "This prototype is designed for adults (18+) and can't continue for "
    "someone under 18 — please contact a pediatrician or your usual "
    "clinic. If at any point there are danger signs — unconsciousness, a "
    "seizure, not responding normally, severe difficulty breathing, or "
    "persistent vomiting — go to the nearest hospital emergency department "
    "immediately, regardless of age."
)

ROLE_QUESTION = Question(
    patient_text="Are you the person with diabetes, or messaging on behalf of someone else?",
    caregiver_text="Are you the person with diabetes, or messaging on behalf of someone else?",
    buttons=(("I'm the patient", "patient"), ("I'm a caregiver", "caregiver")),
)

# ---------------------------------------------------------------------------
# Safety pre-screen (resolves G1 / SN1 / SN2 before category selection)
# ---------------------------------------------------------------------------

UNCONSCIOUS_QUESTION = Question(
    patient_text="Are you fully awake, alert, and responding normally right now?",
    caregiver_text="Is the patient fully awake, alert, and responding normally right now?",
    buttons=YES_NO_UNSURE,
)

NON_DIABETES_EMERGENCY_QUESTION = Question(
    patient_text=(
        "Are you having chest pain, sudden difficulty breathing, or signs of "
        "a stroke (face drooping, slurred speech, one-sided weakness)?"
    ),
    caregiver_text=(
        "Is the patient having chest pain, sudden difficulty breathing, or "
        "signs of a stroke (face drooping, slurred speech, one-sided "
        "weakness)?"
    ),
    buttons=YES_NO_UNSURE,
)

PREGNANCY_QUESTION = Question(
    patient_text="Are you currently pregnant?",
    caregiver_text="Is the patient currently pregnant?",
    buttons=YES_NO_UNSURE,
)

DIABETES_DIAGNOSED_QUESTION = Question(
    patient_text="Have you been diagnosed with diabetes before (Type 1 or Type 2)?",
    caregiver_text="Has the patient been diagnosed with diabetes before (Type 1 or Type 2)?",
    buttons=YES_NO_UNSURE,
)

PRESENTING_COMPLAINT_QUESTION = Question(
    patient_text="What's the main reason you're reaching out today?",
    caregiver_text="What's the main reason you're reaching out today?",
    buttons=(
        ("Low blood sugar symptoms", "hypo"),
        ("High blood sugar / possible DKA", "hyper_dka"),
        ("New symptoms, not diagnosed", "undiagnosed"),
        ("A foot problem", "foot"),
        ("Something else", "other"),
    ),
)

# ---------------------------------------------------------------------------
# Category A — hypoglycemia
# ---------------------------------------------------------------------------

QUESTION_BANK: dict[str, Question] = {
    "unconscious_or_not_responding": UNCONSCIOUS_QUESTION,
    "non_diabetes_emergency_signs": NON_DIABETES_EMERGENCY_QUESTION,
    "pregnant": PREGNANCY_QUESTION,
    "diabetes_diagnosed": DIABETES_DIAGNOSED_QUESTION,
    "a_mild_symptoms": Question(
        patient_text="Are you feeling shaky, hungry, sweaty, or mildly confused right now?",
        caregiver_text="Is the patient feeling shaky, hungry, sweaty, or mildly confused right now?",
        buttons=YES_NO_UNSURE,
    ),
    "a_able_to_swallow_safely": Question(
        patient_text="Are you able to swallow safely right now (e.g. drink some juice)?",
        caregiver_text="Is the patient able to swallow safely right now (e.g. drink some juice)?",
        buttons=YES_NO_UNSURE,
    ),
    "a_able_to_self_treat_unaided": Question(
        patient_text="Can you get to sugar/juice/glucose tablets by yourself right now, without anyone's help?",
        caregiver_text="Can the patient get to sugar/juice/glucose tablets unaided right now, or is someone there to help them?",
        buttons=YES_NO_UNSURE,
    ),
    "a_frequent_or_past_severe_or_impaired_awareness": Question(
        patient_text=(
            "Does this happen often, has it happened badly before, does it "
            "happen at night, or do you often not notice the warning signs "
            "before it happens?"
        ),
        caregiver_text=(
            "Does this happen often, has it happened badly before, does it "
            "happen at night, or does the patient often not notice the "
            "warning signs before it happens?"
        ),
        buttons=YES_NO_UNSURE,
    ),
    "b_isolated_hyperglycemia_symptoms": Question(
        patient_text="Have you had increased thirst, tiredness, frequent urination, or blurred vision?",
        caregiver_text="Has the patient had increased thirst, tiredness, frequent urination, or blurred vision?",
        buttons=YES_NO_UNSURE,
    ),
    "b_dka_red_flags": Question(
        patient_text=(
            "Have you had persistent vomiting, belly pain, fruity-smelling "
            "breath, fast or deep breathing, or unusual confusion/drowsiness?"
        ),
        caregiver_text=(
            "Has the patient had persistent vomiting, belly pain, "
            "fruity-smelling breath, fast or deep breathing, or unusual "
            "confusion/drowsiness?"
        ),
        buttons=YES_NO_UNSURE,
    ),
    "c_new_symptoms": Question(
        patient_text=(
            "Have you noticed increased thirst, urination, or hunger, "
            "tiredness, blurred vision, unexplained weight loss, or "
            "slow-healing sores?"
        ),
        caregiver_text=(
            "Has the patient noticed increased thirst, urination, or hunger, "
            "tiredness, blurred vision, unexplained weight loss, or "
            "slow-healing sores?"
        ),
        buttons=YES_NO_UNSURE,
    ),
    "c_red_flags": Question(
        patient_text=(
            "Is it getting rapidly worse, or do you also have vomiting, "
            "diarrhoea, stomach pain, drowsiness/confusion, or fast/deep "
            "breathing?"
        ),
        caregiver_text=(
            "Is it getting rapidly worse, or does the patient also have "
            "vomiting, diarrhoea, stomach pain, drowsiness/confusion, or "
            "fast/deep breathing?"
        ),
        buttons=YES_NO_UNSURE,
    ),
    "d_stable_non_infected": Question(
        patient_text="Is the foot problem stable and not looking infected — just some discomfort?",
        caregiver_text="Is the patient's foot problem stable and not looking infected — just some discomfort?",
        buttons=YES_NO_UNSURE,
    ),
    "d_infection_signs": Question(
        patient_text="Is there redness, swelling, warmth, discharge, odour, or a wound that isn't healing?",
        caregiver_text="Is there redness, swelling, warmth, discharge, odour, or a wound that isn't healing?",
        buttons=YES_NO_UNSURE,
    ),
    "d_severe_signs": Question(
        patient_text=(
            "Is the redness spreading rapidly, is there a fever, or does the "
            "foot look or feel markedly different in colour or temperature "
            "from the other foot?"
        ),
        caregiver_text=(
            "Is the redness spreading rapidly, is there a fever, or does the "
            "patient's foot look or feel markedly different in colour or "
            "temperature from the other foot?"
        ),
        buttons=YES_NO_UNSURE,
    ),
}

GLUCOSE_UNIT_CLARIFY = Question(
    patient_text=(
        "You mentioned a blood sugar number — was that in mg/dL or mmol/L? "
        "(Most readings in Pakistan are mg/dL.) I record this for the "
        "record, but it won't change the guidance above on its own."
    ),
    caregiver_text=(
        "You mentioned a blood sugar number — was that in mg/dL or mmol/L? "
        "(Most readings in Pakistan are mg/dL.) I record this for the "
        "record, but it won't change the guidance above on its own."
    ),
    buttons=(("mg/dL", "mg/dL"), ("mmol/L", "mmol/L"), ("Not sure", "unknown")),
)

# ---------------------------------------------------------------------------
# Terminal / exit content
# ---------------------------------------------------------------------------

NON_DIABETES_EMERGENCY_EXIT = (
    "This sounds like it could be a medical emergency that isn't about "
    "diabetes. I only handle diabetes triage and can't assess this — please "
    "go to the nearest hospital emergency department right now, or call for "
    "emergency help."
)

PREGNANCY_EXIT = (
    "Because pregnancy is involved, this is outside what this prototype can "
    "safely assess — pregnancy changes every threshold for diabetes-related "
    "urgency. Please contact your obstetric or diabetes care team, or go to "
    "the nearest hospital, without delay."
)

INSULIN_REFUSAL = (
    "I can't calculate or suggest an insulin or medication dose — that has "
    "to come from a clinician who knows the full picture, and getting it "
    "wrong can be dangerous. What I can do is help figure out how urgently "
    "you should be seen. Can we continue with a few quick questions?"
)

GUARDRAIL_FALLBACK = (
    "Sorry, I can't send that response as written. I don't provide doses, "
    "diagnoses, or medication instructions. Let's continue with the triage "
    "questions so I can help you figure out how urgent this is."
)

LOOP_ESCALATION = (
    "I'm having trouble getting a clear answer to keep narrowing this down. "
    "For safety, I'd rather be cautious: please treat this as needing "
    "prompt attention (see the guidance below) rather than wait for a fully "
    "certain answer from me."
)

TIER_LABELS = {
    1: "Tier 1 — Home management",
    2: "Tier 2 — See a BHU (Basic Health Unit) / routine clinical follow-up",
    3: "Tier 3 — Go to Shalamar Hospital or the nearest tertiary facility now (Emergency)",
}

TIER_INTROS = {
    1: "Based on what you've told me, this looks like something you can manage at home for now.",
    2: "Based on what you've told me, this should be checked at a BHU (Basic Health Unit) or your usual clinic soon — not an emergency, but don't leave it.",
    3: "Based on what you've told me, this needs urgent in-person care now.",
}

DEFAULT_TRIGGER_LISTS = {
    1: (
        "Come back / seek care immediately if: you become drowsy or confused, "
        "you can't keep fluids down, symptoms get rapidly worse, or you lose "
        "consciousness or have a seizure."
    ),
    2: (
        "Go to the nearest hospital immediately if: there is persistent "
        "vomiting, fast or deep breathing, worsening confusion, fainting, or "
        "a seizure at any point."
    ),
    3: "This is urgent — please go now rather than waiting to see if it improves.",
}

UNSOURCED_NOTICE = (
    " (Note: part of this recommendation is based on an engineering safety "
    "rule that has not yet been reviewed by a clinician.)"
)


def banner() -> str:
    return PROTOTYPE_BANNER
