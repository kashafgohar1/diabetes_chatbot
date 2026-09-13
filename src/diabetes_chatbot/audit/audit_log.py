"""Append-only audit log. Every turn, both directions, with tier, fired
rule IDs, guard results, and protocol version — a research artifact and
safety record, not a debugging convenience.

Each entry is one JSON line (JSONL) so it's trivially greppable and
diffable. Also kept in-memory per-process for tests and the CLI simulator,
which don't need to read the file back.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings

_PROTOCOL_VERSION = "0.1.0-draft"  # kept in sync with protocol/triage_protocol.yaml
_lock = threading.Lock()


@dataclass
class AuditEntry:
    timestamp: str
    session_id: str
    direction: str  # "inbound" | "outbound"
    turn: int
    message_id: str | None
    text: str
    phase: str
    tier: int | None
    fired_rule_ids: tuple[str, ...]
    invented_rules_used: tuple[str, ...]
    unsourced_rules_used: tuple[str, ...]
    guard_violations: tuple[str, ...]
    guard_passed: bool
    protocol_version: str
    extractor_used: str | None
    note: str = ""


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path or settings.audit_log_path
        self._entries: list[AuditEntry] = []

    def record(self, **kwargs: Any) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            protocol_version=_PROTOCOL_VERSION,
            **kwargs,
        )
        with _lock:
            self._entries.append(entry)
            self._write(entry)
        return entry

    def _write(self, entry: AuditEntry) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except OSError:
            # The audit log is a safety record, not something that may ever
            # crash message handling — but a write failure must not be
            # silently invisible either.
            import logging

            logging.getLogger(__name__).exception("audit_log: failed to write entry to %s", self.path)

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


# Process-wide default instance. The CLI/tests can construct their own
# AuditLog(path=...) when they need isolation.
default_log = AuditLog()
