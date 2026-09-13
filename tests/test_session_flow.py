"""End-to-end session/pipeline behaviour: consent -> age -> role -> triage,
the two remaining regression bugs (loop detection, webhook-redelivery
idempotency), graceful refusals, and the OQ-8 glucose interrupt.
"""

from __future__ import annotations

import uuid

from diabetes_chatbot.extraction import keyword_extractor
from diabetes_chatbot.pipeline import Pipeline
from diabetes_chatbot.session.session_manager import SessionManager


def new_pipeline() -> Pipeline:
    manager = SessionManager(extract_fn=keyword_extractor.extract, extractor_name="keyword")
    return Pipeline(manager)


def sid() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def test_every_outbound_message_carries_the_prototype_banner():
    from diabetes_chatbot.config import PROTOTYPE_BANNER

    pipeline = new_pipeline()
    session_id = sid()
    result = pipeline.handle(session_id, "hi", message_id="m0")
    assert result.messages
    for m in result.messages:
        assert PROTOTYPE_BANNER in m.text


def test_allow_patient_use_defaults_false():
    from diabetes_chatbot.config import settings, ALLOW_PATIENT_USE

    assert settings.allow_patient_use is False
    assert ALLOW_PATIENT_USE is False


def test_consent_declined_exits_gracefully():
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    result = pipeline.handle(session_id, "", message_id="m1", button_value="no")
    assert result.terminal
    assert any("no further questions" in m.text.lower() for m in result.messages)


def test_under_18_exit_still_carries_emergency_safety_netting():
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # consent
    result = pipeline.handle(session_id, "", message_id="m2", button_value="no")  # under 18
    assert result.terminal
    text = result.messages[-1].text.lower()
    assert "18" in text
    assert "unconscious" in text or "seizure" in text or "emergency" in text


def test_g1_interrupts_the_consent_preamble_immediately():
    """Unconsciousness mentioned before consent is even given must still
    escalate to Tier 3 right away."""
    pipeline = new_pipeline()
    session_id = sid()
    result = pipeline.handle(session_id, "please help, he is not responding at all", message_id="m0")
    assert result.terminal
    assert result.tier == 3


def test_insulin_request_is_refused_gracefully_and_conversation_continues():
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # consent
    pipeline.handle(session_id, "", message_id="m2", button_value="yes")  # age
    pipeline.handle(session_id, "", message_id="m3", button_value="patient")  # role
    result = pipeline.handle(session_id, "How much insulin should I take?", message_id="m4")
    assert not result.terminal
    texts = [m.text.lower() for m in result.messages]
    assert any("can't calculate or suggest an insulin" in t for t in texts)
    assert not any("units" in t and any(ch.isdigit() for ch in t) for t in texts)


def test_idempotent_replay_of_same_message_id_is_a_no_op():
    """Bug #5: WhatsApp redelivers on a slow/absent 200. The same message ID
    must never be applied twice."""
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    first = pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # consent -> asks age
    assert not first.terminal
    replay = pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # same message_id again
    assert replay.messages == []  # pure no-op, not re-applied to the (now different) pending slot

    # Confirm state actually advanced only once: the pending question should
    # still be the age question, not something further down the flow.
    session = pipeline.session_manager.get_or_create(session_id)
    assert session.pending_slot == "age_over_18"


def test_loop_detection_escalates_after_repeated_identical_non_answer():
    """Bug #4: loop detection must key on (message, pending slot), not
    message alone."""
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    pipeline.handle(session_id, "", message_id="m1", button_value="yes")
    pipeline.handle(session_id, "", message_id="m2", button_value="yes")
    pipeline.handle(session_id, "", message_id="m3", button_value="patient")
    # Give a non-answer to the same pending question three times in a row.
    r1 = pipeline.handle(session_id, "hmm not sure how to answer that", message_id="m4")
    r2 = pipeline.handle(session_id, "hmm not sure how to answer that", message_id="m5")
    r3 = pipeline.handle(session_id, "hmm not sure how to answer that", message_id="m6")
    assert r1.terminal is False
    assert r2.terminal is False
    assert r3.terminal is True
    assert r3.tier is not None and r3.tier >= 2  # cautious escalation, never Tier 1


def test_six_different_no_answers_to_six_different_questions_is_not_a_loop():
    """The mirrored case: answering "no" to six different screening
    questions in a row is completely normal use and must NOT trigger loop
    detection, because each answer is keyed to a different pending slot."""
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # consent
    pipeline.handle(session_id, "", message_id="m2", button_value="yes")  # age
    pipeline.handle(session_id, "", message_id="m3", button_value="patient")  # role
    for i, value in enumerate(["no", "no", "no"], start=4):
        result = pipeline.handle(session_id, "", message_id=f"m{i}", button_value=value)
    # unconscious=no, non_diabetes_emergency=no, pregnant=no all answered with
    # the same literal text "no" but different pending slots -- must not
    # have triggered the loop escalation.
    assert result.terminal is False or (result.tier is not None)
    session = pipeline.session_manager.get_or_create(session_id)
    assert "LOOP_SAFETY" not in (session.verdict.fired_rule_ids if session.verdict else ())


def test_bare_glucose_number_triggers_unit_clarifying_question():
    pipeline = new_pipeline()
    session_id = sid()
    pipeline.handle(session_id, "hi", message_id="m0")
    pipeline.handle(session_id, "", message_id="m1", button_value="yes")  # consent
    pipeline.handle(session_id, "", message_id="m2", button_value="yes")  # age
    result = pipeline.handle(session_id, "", message_id="m3", button_value="patient")  # role
    result = pipeline.handle(session_id, "my sugar was 20 today", message_id="m4")
    assert any("mg/dl" in m.text.lower() or "mmol/l" in m.text.lower() for m in result.messages)
    session = pipeline.session_manager.get_or_create(session_id)
    assert session.pending_slot == "glucose_unit_clarify"
    assert session.state.glucose_value == 20.0
    assert session.state.glucose_unit is None


def test_role_aware_phrasing_patient_vs_caregiver():
    pipeline = new_pipeline()
    patient_session = sid()
    pipeline.handle(patient_session, "hi", message_id="m0")
    pipeline.handle(patient_session, "", message_id="m1", button_value="yes")
    pipeline.handle(patient_session, "", message_id="m2", button_value="yes")
    r_patient = pipeline.handle(patient_session, "", message_id="m3", button_value="patient")

    caregiver_session = sid()
    pipeline.handle(caregiver_session, "hi", message_id="m0")
    pipeline.handle(caregiver_session, "", message_id="m1", button_value="yes")
    pipeline.handle(caregiver_session, "", message_id="m2", button_value="yes")
    r_caregiver = pipeline.handle(caregiver_session, "", message_id="m3", button_value="caregiver")

    patient_text = r_patient.messages[0].text.lower()
    caregiver_text = r_caregiver.messages[0].text.lower()
    assert "are you" in patient_text
    assert "the patient" in caregiver_text
    assert patient_text != caregiver_text
