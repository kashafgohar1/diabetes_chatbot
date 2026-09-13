"""The deterministic triage decision engine.

STRUCTURAL SAFETY BOUNDARY: NO model, NO network, NO import of
diabetes_chatbot.extraction anywhere in this module or in rules.py/types.py.
tests/test_engine_boundary.py parses the AST of this package and fails the
build if that boundary is crossed.

How G4 ("ambiguous cases default to the higher-urgency tier, never lower")
is implemented: NOT as a prompt instruction. Structurally: evaluate() will
not return a Verdict while any rule whose outcome is CANNOT_DETERMINE has a
candidate tier at or above the current best resolvable tier. It returns
NeedsInfo instead, naming the next slot to ask about. Only once nothing
higher is reachable does it emit a Verdict.
"""

from __future__ import annotations

from typing import Optional, Union

from diabetes_chatbot.state import ClinicalState, PresentingComplaint

from . import rules
from .types import NeedsInfo, Refusal, RuleOutcome, RuleResult, Verdict

FIRES = RuleOutcome.FIRES
CANNOT = RuleOutcome.CANNOT_DETERMINE

# Fixed tie-break priority: when several undetermined (or fired) rules share
# the same candidate tier, this order decides which is asked about / cited
# first. Global overrides first, then highest-severity rule of each category.
_PRIORITY = [
    "G1", "SN1", "SN2",
    "A3", "A4", "A2", "A1",
    "B2", "B1",
    "C2", "C1",
    "D3", "D2", "D1",
]


def _priority_index(rule_id: str) -> int:
    try:
        return _PRIORITY.index(rule_id)
    except ValueError:
        return len(_PRIORITY)


_CATEGORY_RULES = {
    PresentingComplaint.HYPOGLYCEMIA: [rules.rule_a1, rules.rule_a2, rules.rule_a3, rules.rule_a4],
    PresentingComplaint.HYPERGLYCEMIA_DKA: [rules.rule_b1, rules.rule_b2],
    PresentingComplaint.UNDIAGNOSED: [rules.rule_c1, rules.rule_c2],
    PresentingComplaint.FOOT: [rules.rule_d1, rules.rule_d2, rules.rule_d3],
    PresentingComplaint.OTHER: [],
}

_GLOBAL_RULES = [rules.rule_g1, rules.rule_sn1_non_diabetes_emergency, rules.rule_sn2_pregnancy]


def _global_results(state: ClinicalState) -> list[RuleResult]:
    return [r(state) for r in _GLOBAL_RULES]


def _category_results(state: ClinicalState) -> list[RuleResult]:
    if state.presenting_complaint is None:
        return []
    return [r(state) for r in _CATEGORY_RULES.get(state.presenting_complaint, [])]


def check_urgent_override(state: ClinicalState) -> Optional[Verdict]:
    """Opportunistic check: has a global-override rule (G1/SN1/SN2) already
    FIRED from evidence already present in state (e.g. the red-flag
    prefilter matched raw text this turn)? This is what lets an emergency
    interrupt the consent/age-gate/role preamble at any point, without the
    engine ever proactively asking about it before the normal safety
    pre-screen phase — it only reacts to evidence already present, never
    prompts on its own here.
    """
    fired = [r for r in _global_results(state) if r.outcome is FIRES]
    if not fired:
        return None
    return _verdict(fired, safety_net=False)


def evaluate(state: ClinicalState) -> Union[Verdict, Refusal, NeedsInfo]:
    """Evaluate the current clinical state and return a Verdict, a Refusal
    (G2/G3-style non-tier outcome), or NeedsInfo (ask this slot next).

    Deterministic: calling this repeatedly with an unchanged state always
    returns the same result (see tests/test_determinism.py).
    """
    # G2 (insulin/dose request) is a per-turn refusal, not a triage
    # conclusion — it never blocks or advances the rest of the flow.
    g2 = rules.rule_g2(state)
    if g2.outcome is FIRES:
        return Refusal(rule_id="G2", reason=g2.reason)

    all_results: list[RuleResult] = _global_results(state)

    fired_global = [r for r in all_results if r.outcome is FIRES]
    if fired_global:
        # Global overrides (G1/SN1/SN2) are all Tier 3 — the ceiling — so no
        # further question could raise the outcome. Conclude immediately.
        return _verdict(fired_global, safety_net=False)

    if state.presenting_complaint is None:
        # No category selected yet. Before asking about it, confirm no
        # global-override rule is still unresolved (G4): if one is, and its
        # candidate tier is the ceiling (3), it must be asked about first.
        blocking = [r for r in all_results if r.outcome is CANNOT]
        if blocking:
            return _needs_info(blocking)
        return NeedsInfo(slot="presenting_complaint", candidate_rule_ids=(), highest_reachable_tier=0)

    all_results += _category_results(state)

    fired = [r for r in all_results if r.outcome is FIRES]
    best_tier = max((r.tier for r in fired), default=0)

    blocking = [
        r for r in all_results
        if r.outcome is CANNOT and r.tier is not None and r.tier >= max(best_tier, 1)
    ]
    if blocking:
        return _needs_info(blocking)

    if fired:
        return _verdict(fired, safety_net=False)

    # Nothing fired, nothing left to ask — SN3 safety-net floor (G4 forbids
    # defaulting to Tier 1).
    sn3 = rules.rule_sn3_fallback_safety_net(unresolved=False)
    return _verdict([sn3], safety_net=True)


def _needs_info(blocking: list[RuleResult]) -> NeedsInfo:
    blocking_sorted = sorted(
        blocking, key=lambda r: (-(r.tier or 0), _priority_index(r.rule_id))
    )
    target = blocking_sorted[0]
    same_tier = [r for r in blocking_sorted if r.tier == target.tier]
    return NeedsInfo(
        slot=target.needed_slot,
        candidate_rule_ids=tuple(r.rule_id for r in same_tier),
        highest_reachable_tier=target.tier or 0,
    )


def _verdict(fired: list[RuleResult], safety_net: bool) -> Verdict:
    best_tier = max(r.tier for r in fired)
    # OQ-7: when multiple rules fire (e.g. A1 and A2 both apply), the
    # higher tier wins for the DECISION, but every fired rule ID is still
    # reported — never just the winning one — so the audit trail shows the
    # full clinical picture, not only what determined the tier.
    all_sorted = sorted(fired, key=lambda r: (-(r.tier or 0), _priority_index(r.rule_id)))
    reason = "; ".join(f"{r.rule_id}: {r.reason}" for r in all_sorted)
    return Verdict(
        tier=best_tier,
        fired_rule_ids=tuple(r.rule_id for r in all_sorted),
        invented_rules_used=tuple(r.rule_id for r in all_sorted if r.invented),
        unsourced_rules_used=tuple(r.rule_id for r in all_sorted if r.unsourced),
        safety_net=safety_net,
        reason=reason,
    )
