"""Types shared by the decision engine. No imports beyond the standard
library and diabetes_chatbot.state — this module is part of the deterministic
core and is covered by the same AST import-boundary test as rules.py and
engine.py (see tests/test_engine_boundary.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RuleOutcome(str, Enum):
    FIRES = "fires"
    DOES_NOT_FIRE = "does_not_fire"
    CANNOT_DETERMINE = "cannot_determine"


@dataclass(frozen=True)
class RuleResult:
    """The result of evaluating one protocol rule against a ClinicalState."""

    rule_id: str
    outcome: RuleOutcome
    tier: Optional[int]  # candidate tier if this rule fires; None if it doesn't/can't
    invented: bool = False
    unsourced: bool = False
    needed_slot: Optional[str] = None  # which slot would resolve CANNOT_DETERMINE
    action: Optional[str] = None  # e.g. "refuse_gracefully" for G2/G3
    reason: str = ""


@dataclass(frozen=True)
class Verdict:
    """A terminal triage decision. Exactly one tier, plus which rules fired."""

    tier: int
    fired_rule_ids: tuple[str, ...]
    invented_rules_used: tuple[str, ...]
    unsourced_rules_used: tuple[str, ...]
    safety_net: bool
    reason: str


@dataclass(frozen=True)
class Refusal:
    """A non-tier terminal outcome: the engine is refusing to act (G2/G3)."""

    rule_id: str
    reason: str


@dataclass(frozen=True)
class NeedsInfo:
    """The engine cannot yet conclude — ask about this slot next.

    G4 is implemented by *never* returning a Verdict while a CANNOT_DETERMINE
    rule could still land at or above the current best resolvable tier;
    NeedsInfo is what gets returned instead.
    """

    slot: str
    candidate_rule_ids: tuple[str, ...]  # rules blocked on this slot
    highest_reachable_tier: int


EngineResult = "Verdict | Refusal | NeedsInfo"
