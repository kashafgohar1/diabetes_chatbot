# Diabetes Triage Chatbot — Prototype

**⚠️ PROTOTYPE — NOT FOR REAL PATIENT USE.** Every clinical rule in this
repository is `PENDING_CLINICAL_REVIEW`. Nothing here has been approved by
a clinician. `config.ALLOW_PATIENT_USE` (and `protocol/triage_protocol.yaml`'s
`allow_patient_use`) default to `False` and must stay that way until a
clinician signs off — see `protocol/signoff/` and `docs/CLINICIAN_REVIEW.md`.

MS AI capstone project, LUMS — a patient-facing (and caregiver-facing)
diabetes triage chatbot for eventual deployment with Shalamar Hospital,
Lahore. It is explicitly **not a diagnostic tool**. Its only job is to work
out how urgently someone should be seen, and route them to one of three
tiers:

- **Tier 1** — Home management / low priority
- **Tier 2** — Management at a BHU (Basic Health Unit) / routine follow-up
- **Tier 3** — Shalamar Hospital or nearest tertiary facility (emergency)

## The core idea: the LLM never decides

This is **not** a RAG chatbot that reasons its way to an escalation level.
Retrieval and generation are non-deterministic, and non-determinism at the
DKA boundary is the failure mode this whole project exists to prevent. The
same clinical situation described two ways must produce the same tier,
every time (see `tests/test_determinism.py`).

```
inbound WhatsApp message
   |
   v
red-flag pre-filter        deterministic . raw text . runs BEFORE any model call . every turn
   |                       (diabetes_chatbot/redflags.py, lexicon.py)
   v
slot extraction            LLM (fails closed) OR deterministic keyword extractor
   |                       natural language -> strict tri-state clinical variables
   |                       (diabetes_chatbot/extraction/)
   v
triage decision engine     deterministic . versioned rules . NO model, NO network
   |                       (diabetes_chatbot/engine/) -- see the AST boundary test
   v
response rendering         approved content blocks only; LLM may rephrase, never author
   |                       (diabetes_chatbot/rendering/)
   v
output guardrail           deterministic . blocks doses, diagnoses, tier/text mismatch
   |                       (diabetes_chatbot/guardrail/)
   v
outbound reply + audit log (diabetes_chatbot/audit/)
```

The LLM extractor's entire job is translating between natural language and
structured tri-state clinical variables (`state.ClinicalState`). **It never
sees a tier and never decides anything.**

The safety argument is executable, not just asserted:
`tests/test_engine_boundary.py` parses the AST of every file in
`diabetes_chatbot.engine` and fails the build if it imports an LLM client,
a network library, or the extraction package. Run it any time someone asks
how you know the model isn't making the decision:

```bash
pytest tests/test_engine_boundary.py -v
```

## Repository layout

```
protocol/
  triage_protocol.yaml     versioned, machine-readable clinical rules (A1-D3, G1-G4, SN1-SN3),
                            source citations, approval status, open questions (OQ-1..OQ-9)
  signoff/                 per-rule-series clinician sign-off tracking (all currently unsigned)
docs/
  Provisional_Clinical_logic_draft.xlsx   the source rule table (see docs/CLINICIAN_REVIEW.md §6)
  CLINICIAN_REVIEW.md       every open question, invented rule, wording decision, and defect found
src/diabetes_chatbot/
  state.py                 tri-state (yes/no/unknown) ClinicalState -- the shared vocabulary
  config.py                allow_patient_use (defaults False), prototype banner, settings
  lexicon.py                deterministic text-matching primitives (shared by redflags + keyword extractor)
  redflags.py               deterministic pre-filter: G1/SN1/SN2 + insulin-request detection, every turn
  engine/                   THE DECISION ENGINE -- no LLM, no network, no extraction import (enforced by AST test)
    rules.py                one pure function per protocol rule ID
    engine.py                aggregation + structural G4 ("ask, don't guess, when ambiguous")
    types.py                 RuleResult / Verdict / Refusal / NeedsInfo
  extraction/
    keyword_extractor.py     deterministic, offline, no API key needed (used by CLI + tests + CI)
    llm_extractor.py         Claude-backed, strict JSON schema, FAILS CLOSED on any error/timeout/bad output
    schema.py                 the extractable slot vocabulary + JSON schema
  rendering/
    content_blocks.py         every approved message template (role-aware, banner-carrying)
    renderer.py                 selects + fills a template; optional (disabled) LLM rephrase hook
  guardrail/
    output_guardrail.py       blocks dose numbers/drug names, imperative dose instructions,
                               diagnostic assertions (G3), and tier/text urgency mismatches
  session/
    conversation.py            per-conversation state + idempotency/loop-detection bookkeeping
    session_manager.py         consent -> 18+ age gate -> patient/caregiver role -> triage state machine
  audit/audit_log.py         JSONL audit trail, every turn, both directions
  pipeline.py                 wires session -> guardrail -> audit together for any channel
  channel/whatsapp_adapter.py Meta Cloud API: webhook verify, HMAC check, send/parse (no clinical logic)
  api/app.py                  FastAPI app: real webhook + a /dev/message HTTP endpoint for demos/tests
  cli/simulator.py            offline CLI -- no API key, no WhatsApp credentials, no network
tests/                       130+ tests: one (or more) per protocol rule ID, determinism, AST boundary,
                              guardrail, lexicon regressions (bugs #1-3), session flow (bugs #4-5),
                              in-process API tests, and a REAL booted-server HTTP test (test_http_live.py)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements.txt
```

(`pip install -e .` registers the `diabetes_chatbot` package via
`pyproject.toml`; `requirements.txt` pins every dependency's exact
version.)

## Run the tests

```bash
pytest                      # full suite (130+ tests)
pytest -k A3                # every test bound to protocol rule A3
pytest tests/test_engine_boundary.py -v   # the safety-argument test
```

Every protocol rule ID has at least one test named so `pytest -k <ID>`
selects it (enforced by `tests/test_protocol_manifest.py`, which fails the
build if a rule ships with no matching test).

## Run the offline CLI simulator (no API key, no WhatsApp credentials)

```bash
python -m diabetes_chatbot.cli.simulator --list-scenarios
python -m diabetes_chatbot.cli.simulator --scenario caregiver_unresponsive
python -m diabetes_chatbot.cli.simulator --scenario insulin_request
python -m diabetes_chatbot.cli.simulator --scenario mild_hypo_tier1
python -m diabetes_chatbot.cli.simulator --scenario foot_tier3
python -m diabetes_chatbot.cli.simulator --scenario bare_glucose_no_unit
python -m diabetes_chatbot.cli.simulator --all     # run all five back to back
python -m diabetes_chatbot.cli.simulator            # interactive mode
```

## Run the API server

```bash
uvicorn diabetes_chatbot.api.app:app --host 0.0.0.0 --port 8000
```

- `GET /health` — liveness + confirms `allow_patient_use` is `False`.
- `GET/POST /webhook/whatsapp` — the real Meta Cloud API webhook
  (verification handshake + HMAC-signature-checked inbound messages). Set
  `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`,
  `WHATSAPP_PHONE_NUMBER_ID` to point it at a real WhatsApp Business
  number; with none of those set, it still verifies structurally and
  replies are captured by a dry-run transport (nothing is sent anywhere)
  rather than crashing.
- `POST /dev/message` — drives a full conversation over plain HTTP with a
  JSON body `{"session_id": "...", "text": "...", "button_value": "..."}`,
  for demos and automated tests without any WhatsApp payload shape:

```bash
curl -s -X POST http://localhost:8000/dev/message \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo1","text":"hi"}'
```

Set `ANTHROPIC_API_KEY` to switch the running server from the offline
keyword extractor to the Claude-backed LLM extractor for the real
(non-button) free-text path; with no key set, it uses the deterministic
keyword extractor automatically (this is also what makes the demo and CI
fully offline).

## Clean-room verification performed

From a fresh clone / fresh virtualenv: `pip install -e . && pip install -r
requirements.txt`, `pytest` (full suite green), booted `uvicorn` on a real
port and drove complete conversations over real HTTP with `curl` —
including the WhatsApp webhook's GET verification handshake, a rejected
bad-HMAC POST (403), an accepted correctly-signed POST (200), and a
same-message-ID replay that produced zero duplicate side effects (bug #5
regression, confirmed against the audit log, not just in-process) — then
ran all five CLI demo scenarios end to end. See `docs/CLINICIAN_REVIEW.md`
§7 for what broke along the way and how it was fixed.

## What is NOT built yet

See `docs/CLINICIAN_REVIEW.md` §4 for the full list. In short: no LLM
rephrasing pass is enabled (approved templates are sent verbatim), glucose
readings are captured but never acted on (OQ-8), there is no persistent
session store (in-memory only — a restart loses in-flight conversations),
no pregnancy-adjusted rule set (pregnancy always exits to Tier 3/out of
scope), no real Meta WhatsApp app has been registered, and the keyword
extractor's lexicon is illustrative rather than exhaustive (the LLM
extractor, which fails closed, is the intended path for broad free-text
coverage).

## Regression bugs from an earlier build, and where they're covered

1. **Negation ordering** ("Not high" matching "high") —
   `lexicon.py` module docstring + `tests/test_lexicon_regressions.py::test_bug1_*`
2. **Substring role matching** ("someone else" containing "me") —
   `lexicon.detect_role` + `tests/test_lexicon_regressions.py::test_bug2_*`
3. **Red-flag lexicon recall** ("not waking up properly") —
   `lexicon.UNCONSCIOUS_OR_NOT_RESPONDING` + `tests/test_lexicon_regressions.py::test_bug3_*`
4. **Loop detection** keyed on (message, pending slot) —
   `session/conversation.py::register_repeat` + `tests/test_session_flow.py::test_loop_detection_*`
   and `test_six_different_no_answers_*`
5. **Webhook redelivery / idempotency** —
   `session/conversation.py::already_seen`/`remember_message_id` +
   `tests/test_session_flow.py::test_idempotent_replay_*` (also verified
   manually against a real booted server and its audit log, not just
   in-process)
6. **Never commit a virtualenv** — `.venv/`, `audit_logs/`, `__pycache__/`
   etc. are in `.gitignore` from the first commit.
