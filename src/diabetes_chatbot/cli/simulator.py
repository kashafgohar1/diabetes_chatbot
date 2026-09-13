"""Offline CLI simulator. No API key, no WhatsApp credentials, no network —
uses the deterministic keyword extractor throughout, so it runs anywhere.

Usage:
    python -m diabetes_chatbot.cli.simulator                  # interactive
    python -m diabetes_chatbot.cli.simulator --scenario NAME  # scripted demo
    python -m diabetes_chatbot.cli.simulator --list-scenarios
"""

from __future__ import annotations

import argparse
import sys
import uuid

from ..extraction import keyword_extractor
from ..pipeline import Pipeline
from ..session.session_manager import SessionManager

Answer = tuple[str, str]  # ("button", value) | ("text", raw_text)


def _b(value: str) -> Answer:
    return ("button", value)


def _t(text: str) -> Answer:
    return ("text", text)


SCENARIOS: dict[str, dict] = {
    "caregiver_unresponsive": {
        "description": "Caregiver reports an unresponsive patient — must escalate to Tier 3 immediately.",
        "opening": "My mother is not waking up properly!",
        "plan": {},
    },
    "insulin_request": {
        "description": "An insulin dose request mid-flow — must be refused gracefully, then continue.",
        "opening": "hi",
        "plan": {
            "consent": _b("yes"),
            "age_over_18": _b("yes"),
            "role": _b("patient"),
            "unconscious_or_not_responding": _b("no"),
            "non_diabetes_emergency_signs": _b("no"),
            "pregnant": _b("no"),
            "diabetes_diagnosed": _b("yes"),
            "presenting_complaint": _t("How much insulin should I take?"),
            # After the refusal, the same presenting_complaint question is
            # re-asked — answer it for real this time to show the
            # conversation actually continues to a verdict.
            "presenting_complaint_retry": _b("hypo"),
            "a_able_to_swallow_safely": _b("yes"),
            "a_able_to_self_treat_unaided": _b("yes"),
            "a_frequent_or_past_severe_or_impaired_awareness": _b("no"),
            "a_mild_symptoms": _b("yes"),
        },
    },
    "mild_hypo_tier1": {
        "description": "Mild, self-treatable hypo symptoms — should resolve to Tier 1 (rule A1).",
        "opening": "hi",
        "plan": {
            "consent": _b("yes"),
            "age_over_18": _b("yes"),
            "role": _b("patient"),
            "unconscious_or_not_responding": _b("no"),
            "non_diabetes_emergency_signs": _b("no"),
            "pregnant": _b("no"),
            "diabetes_diagnosed": _b("yes"),
            "presenting_complaint": _b("hypo"),
            "a_able_to_swallow_safely": _b("yes"),
            "a_able_to_self_treat_unaided": _b("yes"),
            "a_frequent_or_past_severe_or_impaired_awareness": _b("no"),
            "a_mild_symptoms": _b("yes"),
        },
    },
    "foot_tier3": {
        "description": "Foot problem with severe/unsourced signs — should resolve to Tier 3 (rule D3, flagged unsourced).",
        "opening": "hi",
        "plan": {
            "consent": _b("yes"),
            "age_over_18": _b("yes"),
            "role": _b("caregiver"),
            "unconscious_or_not_responding": _b("no"),
            "non_diabetes_emergency_signs": _b("no"),
            "pregnant": _b("no"),
            "diabetes_diagnosed": _b("yes"),
            "presenting_complaint": _b("foot"),
            "d_severe_signs": _b("yes"),
        },
    },
    "bare_glucose_no_unit": {
        "description": "A bare glucose number with no unit — must trigger a clarifying question, never guess.",
        "opening": "hi",
        "plan": {
            "consent": _b("yes"),
            "age_over_18": _b("yes"),
            "role": _b("patient"),
            "unconscious_or_not_responding": _t("I'm okay, my sugar reading was 250 today"),
            "glucose_unit_clarify": _b("mg/dL"),
            "unconscious_or_not_responding_retry": _b("no"),
            "non_diabetes_emergency_signs": _b("no"),
            "pregnant": _b("no"),
            "diabetes_diagnosed": _b("yes"),
            "presenting_complaint": _b("other"),
        },
    },
}


def run_scenario(name: str, verbose: bool = True) -> list[tuple[str, str]]:
    spec = SCENARIOS[name]
    plan: dict[str, Answer] = dict(spec["plan"])
    session_id = f"cli-{name}-{uuid.uuid4().hex[:8]}"
    manager = SessionManager(extract_fn=keyword_extractor.extract, extractor_name="keyword")
    pipeline = Pipeline(manager)

    transcript: list[tuple[str, str]] = []

    def emit_bot(messages) -> None:
        for m in messages:
            transcript.append(("bot", m.text))
            if verbose:
                print(f"[bot] {m.text}\n")

    def emit_user(label: str) -> None:
        transcript.append(("user", label))
        if verbose:
            print(f"[user] {label}\n")

    emit_user(spec["opening"])
    result = pipeline.handle(session_id, spec["opening"], message_id=f"{session_id}-0")
    emit_bot(result.messages)

    turn = 1
    used_keys: set[str] = set()
    while not result.terminal and turn < 30:
        session = manager.get_or_create(session_id)
        slot = session.pending_slot
        if slot is None:
            break
        # Allow a "<slot>_retry" plan key for a slot answered more than once
        # in the same scenario (e.g. after a refusal or a glucose interrupt).
        key = slot if slot not in used_keys else f"{slot}_retry"
        if key not in plan:
            key = slot
        if key not in plan:
            raise KeyError(f"scenario {name!r} has no planned answer for pending slot {slot!r}")
        used_keys.add(slot)
        mode, value = plan[key]

        if mode == "button":
            emit_user(f"[button: {value}]")
            result = pipeline.handle(session_id, "", message_id=f"{session_id}-{turn}", button_value=value)
        else:
            emit_user(value)
            result = pipeline.handle(session_id, value, message_id=f"{session_id}-{turn}")
        emit_bot(result.messages)
        turn += 1

    if verbose:
        session = manager.get_or_create(session_id)
        print(f"--- scenario {name!r} finished: tier={result.tier} terminal={result.terminal} ---")
        if session.verdict:
            print(
                f"fired_rule_ids={session.verdict.fired_rule_ids} "
                f"invented={session.verdict.invented_rules_used} "
                f"unsourced={session.verdict.unsourced_rules_used}"
            )
    return transcript


def _interactive() -> None:
    session_id = f"cli-interactive-{uuid.uuid4().hex[:8]}"
    manager = SessionManager(extract_fn=keyword_extractor.extract, extractor_name="keyword")
    pipeline = Pipeline(manager)
    print("Diabetes Triage Chatbot Prototype — offline CLI (type 'quit' to exit)\n")
    turn = 0
    text = "hi"
    while True:
        result = pipeline.handle(session_id, text, message_id=f"{session_id}-{turn}")
        for m in result.messages:
            print(f"\n[bot] {m.text}")
            if m.buttons:
                print("      options: " + ", ".join(f"[{label}]" for label, _ in m.buttons))
        if result.terminal:
            print("\n--- conversation finished ---")
            break
        turn += 1
        try:
            text = input("\n[you] ")
        except EOFError:
            break
        if text.strip().lower() in ("quit", "exit"):
            break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="run a scripted demo scenario")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--all", action="store_true", help="run every scenario in sequence")
    args = parser.parse_args(argv)

    if args.list_scenarios:
        for name, spec in SCENARIOS.items():
            print(f"{name}: {spec['description']}")
        return 0

    if args.all:
        for name in SCENARIOS:
            print(f"\n===== SCENARIO: {name} =====\n")
            run_scenario(name)
        return 0

    if args.scenario:
        run_scenario(args.scenario)
        return 0

    _interactive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
