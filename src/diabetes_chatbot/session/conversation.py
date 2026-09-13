"""Per-conversation state: clinical state plus session-management
bookkeeping (idempotency, loop detection) that is NOT clinical data and
must never leak into ClinicalState / the decision engine.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..config import settings
from ..engine.types import Verdict
from ..state import ClinicalState


@dataclass
class Session:
    session_id: str
    state: ClinicalState = field(default_factory=ClinicalState)

    consent_given: bool = False
    consent_declined: bool = False
    terminal: bool = False
    verdict: Verdict | None = None

    pending_slot: str | None = "consent"
    last_needs_info_tier: int = 0
    turn_count: int = 0

    # Bug #5 fix: bounded per-session message-ID idempotency.
    _seen_ids: deque = field(default_factory=lambda: deque(maxlen=settings.idempotency_window))
    _seen_id_set: set = field(default_factory=set)

    # Bug #4 fix: loop detection keyed on (message text, pending slot), not
    # message text alone — six different "no" answers to six different
    # questions is normal use, not a stuck user.
    _repeat_counts: dict = field(default_factory=dict)

    def already_seen(self, message_id: str | None) -> bool:
        if message_id is None:
            return False
        return message_id in self._seen_id_set

    def remember_message_id(self, message_id: str | None) -> None:
        if message_id is None:
            return
        self._seen_id_set.add(message_id)
        self._seen_ids.append(message_id)
        while len(self._seen_ids) > settings.idempotency_window:
            old = self._seen_ids.popleft()
            self._seen_id_set.discard(old)

    def register_repeat(self, effective_text: str, slot: str | None) -> int:
        key = (effective_text.strip().lower(), slot)
        count = self._repeat_counts.get(key, 0) + 1
        self._repeat_counts[key] = count
        return count
