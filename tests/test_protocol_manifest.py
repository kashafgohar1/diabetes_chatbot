"""Traceability check: every rule ID in protocol/triage_protocol.yaml must
have (a) an implementing function and (b) at least one test whose name
names that rule ID. This is the test that "fails if a rule ships without a
test" — a protocol change that adds/renames a rule ID and forgets the test
fails right here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from diabetes_chatbot.config import PROTOCOL_PATH, REPO_ROOT
from diabetes_chatbot.engine import rules as rules_module
from diabetes_chatbot.guardrail import output_guardrail

TESTS_DIR = Path(__file__).parent


def _load_protocol() -> dict:
    with open(PROTOCOL_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_test_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in TESTS_DIR.glob("test_*.py"))


def _has_test_for(rule_id: str, source: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(rule_id)}(?![A-Za-z0-9])")
    for match in pattern.finditer(source):
        # only count occurrences inside a `def test_...` line's neighborhood is
        # overkill; simpler and sufficient: require it to appear somewhere in
        # a line that also contains "def test_".
        line_start = source.rfind("\n", 0, match.start()) + 1
        line_end = source.find("\n", match.end())
        line = source[line_start:line_end if line_end != -1 else None]
        if "def test_" in line:
            return True
    return False


def test_every_protocol_rule_has_a_named_test():
    protocol = _load_protocol()
    source = _all_test_source()
    missing = []
    for rule_id in protocol["rules"]:
        if not _has_test_for(rule_id, source):
            missing.append(rule_id)
    assert not missing, f"protocol rule(s) with no matching test function: {missing}"


def test_every_protocol_rule_has_an_implementing_function_or_guardrail_check():
    protocol = _load_protocol()
    missing = []
    for rule_id, spec in protocol["rules"].items():
        implemented_by = spec.get("implemented_by")
        implemented_note = spec.get("implemented_note", "")
        if implemented_by is None:
            # G4 is structural (documented via implemented_note pointing at
            # engine.evaluate) rather than a single function.
            if "engine.evaluate" not in implemented_note:
                missing.append(rule_id)
            continue
        if implemented_by.startswith("guardrail."):
            func_name = implemented_by.rsplit(".", 1)[-1]
            if not hasattr(output_guardrail, func_name):
                missing.append(rule_id)
        else:
            if not hasattr(rules_module, implemented_by):
                missing.append(rule_id)
    assert not missing, f"protocol rule(s) with no resolvable implementation: {missing}"


def test_allow_patient_use_defaults_false_in_both_protocol_and_config():
    protocol = _load_protocol()
    assert protocol["allow_patient_use"] is False
    from diabetes_chatbot.config import ALLOW_PATIENT_USE, settings

    assert ALLOW_PATIENT_USE is False
    assert settings.allow_patient_use is False


def test_every_rule_carries_an_approval_status_of_pending_clinical_review():
    protocol = _load_protocol()
    for rule_id, spec in protocol["rules"].items():
        assert spec.get("status") == "PENDING_CLINICAL_REVIEW", rule_id


def test_invented_and_unsourced_flags_are_present_and_consistent():
    protocol = _load_protocol()
    # D3 must be unsourced; A4/SN1/SN2/SN3 must be invented; G-series must not.
    assert protocol["rules"]["D3"]["unsourced"] is True
    for invented_id in ("A4", "SN1", "SN2", "SN3"):
        assert protocol["rules"][invented_id]["invented"] is True
    for sourced_id in ("A1", "A2", "A3", "B1", "B2", "C1", "C2", "D1", "D2"):
        assert protocol["rules"][sourced_id]["invented"] is False
        assert protocol["rules"][sourced_id]["unsourced"] is False


def test_docs_clinician_review_exists_and_mentions_every_open_question():
    protocol = _load_protocol()
    review_path = REPO_ROOT / "docs" / "CLINICIAN_REVIEW.md"
    assert review_path.exists(), "docs/CLINICIAN_REVIEW.md must exist"
    content = review_path.read_text(encoding="utf-8")
    for oq_id in protocol["open_questions"]:
        assert oq_id in content, f"{oq_id} not mentioned in docs/CLINICIAN_REVIEW.md"
