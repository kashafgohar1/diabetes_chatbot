"""Global prototype configuration.

`allow_patient_use` MUST default to False. Flipping it to True is the
deliberate, greppable act of turning this prototype into a live service —
grep the codebase for `allow_patient_use` before ever setting it True.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "protocol" / "triage_protocol.yaml"

# The single greppable switch. Do not set this True outside of a
# clinician-approved deployment decision.
ALLOW_PATIENT_USE: bool = False

PROTOTYPE_BANNER = (
    "⚠️ PROTOTYPE — NOT FOR REAL PATIENT USE. These clinical "
    "rules are provisional and have not been reviewed or approved by a "
    "clinician. This tool does not diagnose and does not replace medical "
    "care. If this is a medical emergency, go to the nearest hospital now."
)


@dataclass
class Settings:
    allow_patient_use: bool = ALLOW_PATIENT_USE
    protocol_path: Path = PROTOCOL_PATH
    whatsapp_app_secret: str | None = os.environ.get("WHATSAPP_APP_SECRET")
    whatsapp_access_token: str | None = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str | None = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str | None = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    llm_extraction_model: str = os.environ.get(
        "LLM_EXTRACTION_MODEL", "claude-haiku-4-5"
    )
    audit_log_path: Path = REPO_ROOT / "audit_logs" / "audit.jsonl"
    idempotency_window: int = 500  # bounded per-session message-id cache size
    loop_repeat_threshold: int = 3  # repeats of (message, pending_slot) before intervening


settings = Settings()
