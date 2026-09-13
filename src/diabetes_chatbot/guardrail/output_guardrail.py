"""Deterministic output guardrail — the last line of defence before a
message reaches the patient.

Runs on every rendered message. On any violation: DISCARD the message, send
the approved fallback (content_blocks.GUARDRAIL_FALLBACK), and log the
incident. Never patch, never silently regenerate — a retry would hide
exactly the events this project most needs to count.

No network, no LLM. Pure text/regex checks, deliberately conservative
(prefers a false-positive block over a false-negative leak).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DRUG_NAMES = (
    "insulin", "metformin", "humalog", "novorapid", "novolog", "lantus",
    "levemir", "actrapid", "mixtard", "glimepiride", "glipizide", "gliclazide",
    "sulfonylurea", "sitagliptin", "empagliflozin", "canagliflozin",
    "dapagliflozin", "tresiba", "humulin",
)
_DRUG_PATTERN = r"(?:" + "|".join(_DRUG_NAMES) + r")"

# Number adjacent to a dose unit. mg/dL and mmol/L are glucose-CONCENTRATION
# units, not medication dose units, and must not trip this check — excluded
# via negative lookahead.
_DOSE_NUMBER_PATTERN = re.compile(
    rf"\b\d+(?:\.\d+)?\s*(?:units?|iu|mg(?!\s*/\s*d?l)|ml(?!\s*/\s*l)|cc)\b",
    re.IGNORECASE,
)

_NUMBER_NEAR_DRUG_PATTERN = re.compile(
    rf"(?:\b\d+(?:\.\d+)?\b[^.\n]{{0,15}}\b{_DRUG_PATTERN}\b)"
    rf"|(?:\b{_DRUG_PATTERN}\b[^.\n]{{0,15}}\b\d+(?:\.\d+)?\b)",
    re.IGNORECASE,
)

_IMPERATIVE_DOSE_PATTERNS = (
    re.compile(
        rf"\b(?:take|increase|decrease|reduce|start|stop|double|halve|adjust|up)\b"
        rf"[^.\n]{{0,25}}\b(?:{_DRUG_PATTERN}|dose|dosage|medication)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_DRUG_PATTERN}\b[^.\n]{{0,20}}\b(?:take|increase|decrease|reduce|start|stop)\b",
        re.IGNORECASE,
    ),
)

_DIAGNOSTIC_ASSERTION_PATTERNS = (
    re.compile(r"\byou(?:'ve| have)\b[^.\n]{0,20}\bdiabetes\b", re.IGNORECASE),
    re.compile(r"\byou are (?:a )?diabetic\b", re.IGNORECASE),
    re.compile(r"\bthis (?:is|means)\b[^.\n]{0,20}\bdiabetes\b", re.IGNORECASE),
    re.compile(r"\byou (?:definitely|certainly) have\b[^.\n]{0,20}\bdiabetes\b", re.IGNORECASE),
    re.compile(r"\bconfirms?(?: that)? you have\b[^.\n]{0,20}\bdiabetes\b", re.IGNORECASE),
    re.compile(r"\byou have (?:dka|diabetic ketoacidosis)\b", re.IGNORECASE),
)

_EMERGENCY_PHRASE_PATTERNS = (
    re.compile(r"\bgo to (?:the )?(?:nearest )?hospital\b[^.\n]{0,25}\b(?:now|right now|immediately)\b", re.IGNORECASE),
    re.compile(r"\bcall (?:an )?ambulance\b[^.\n]{0,15}\bnow\b", re.IGNORECASE),
    re.compile(r"\bthis is an emergency\b", re.IGNORECASE),
    re.compile(r"\bseek emergency care\b", re.IGNORECASE),
    re.compile(r"\bneeds? urgent[^.\n]{0,20}\bnow\b", re.IGNORECASE),
)

_CONDITIONAL_KEYWORDS_PATTERN = re.compile(
    r"\b(?:if|unless|should|in case|were to|becomes?|worsens?|comes? back|come back)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardrailResult:
    passed: bool
    violations: tuple[str, ...] = ()


def check_dose_content(text: str) -> list[str]:
    violations = []
    if _DOSE_NUMBER_PATTERN.search(text):
        violations.append("number_adjacent_to_dose_unit")
    if _NUMBER_NEAR_DRUG_PATTERN.search(text):
        violations.append("number_adjacent_to_drug_name")
    for pattern in _IMPERATIVE_DOSE_PATTERNS:
        if pattern.search(text):
            violations.append("imperative_medication_instruction")
            break
    return violations


def check_diagnostic_assertion(text: str) -> list[str]:
    """Enforces protocol rule G3: no output may state or imply a diagnosis."""
    for pattern in _DIAGNOSTIC_ASSERTION_PATTERNS:
        if pattern.search(text):
            return ["diagnostic_assertion"]
    return []


def check_tier_text_mismatch(text: str, tier: int | None) -> list[str]:
    """Unconditional emergency language is a violation for Tier 1/2 verdicts.
    Conditional safety-netting ("go to hospital immediately IF X happens")
    is required content and must NOT be blocked — a match is only a
    violation if its sentence carries no conditional keyword.
    """
    if tier not in (1, 2):
        return []
    sentences = re.split(r"[.\n;]", text)
    for sentence in sentences:
        for pattern in _EMERGENCY_PHRASE_PATTERNS:
            if pattern.search(sentence) and not _CONDITIONAL_KEYWORDS_PATTERN.search(sentence):
                return ["tier_text_mismatch"]
    return []


def evaluate(text: str, tier: int | None = None) -> GuardrailResult:
    violations: list[str] = []
    violations += check_dose_content(text)
    violations += check_diagnostic_assertion(text)
    violations += check_tier_text_mismatch(text, tier)
    return GuardrailResult(passed=not violations, violations=tuple(violations))
