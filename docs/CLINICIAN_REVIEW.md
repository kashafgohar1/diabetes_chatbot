# Clinician / Instructor Review Pack

**Status: nothing in this document or in `protocol/triage_protocol.yaml` has
been reviewed or approved by a clinician.** Every rule is
`PENDING_CLINICAL_REVIEW`. This document exists to take into the clinical
meeting: every open question, every rule the engineering team invented,
every wording decision that needs sign-off, and every defect found while
building the prototype.

Rule IDs referenced below are defined in `protocol/triage_protocol.yaml`,
which is the single source of clinical truth. Sign-offs are recorded
per-rule-series in `protocol/signoff/`.

---

## 1. Open questions from the provisional draft (OQ-1 … OQ-9)

These come from `Provisional_Clinical_logic_draft.xlsx` (see §6 on the
source file itself). Kashaf Gohar identified these ambiguities before
implementation began; each was resolved with an explicit, documented,
conservative default rather than silently picking an interpretation.

### OQ-1 — C1 returns two tiers
The draft lists C1 ("possible undiagnosed diabetes, no red flags") as
**Tier 1/2**. A chatbot cannot send a patient two tiers. **Implemented as
Tier 2**, per G4 (ambiguous cases default to the higher-urgency tier).
**Needs clinician confirmation**: is Tier 2 correct, or should undiagnosed
presentations always route to a BHU regardless of symptom severity (which
is what Tier 2 already does), or is there a genuine Tier-1-eligible subset
that Tier 2 over-triages?

### OQ-2 — D3 is unsourced
D3 ("rapidly spreading redness, fever, or marked colour/temperature
difference" → Tier 3) is marked `NOT SOURCED` in the draft, and the
draft's own rationale column questions whether Tier 3 is right.
**Implemented as Tier 3**, and every decision and audit entry that uses D3
is flagged `unsourced: true` — distinctly from the sourced D1/D2 rules and
distinctly from the engineering-invented rules (A4, SN1–SN3). **Needs a
citation or a corrected tier from a clinician** — this is the single
highest-priority item in this whole document, since it is a sourced-draft
rule masquerading as evidence-based when it isn't.

### OQ-4 — the gap between A1 and A3
A1 requires "able to self-treat **and** swallow safely." A3 requires
"unconscious, seizure, **or** unable to swallow safely." A conscious
person who can swallow but cannot physically reach sugar/treatment
unaided (alone, immobile, no one available) satisfies neither — and
would fall through to no rule firing at all, i.e. a silent under-triage.
**Added rule A4 (Tier 3, invented, not in the draft)** to close this gap.
**Needs clinical judgment**: is Tier 3 right for "conscious, can swallow,
but can't reach sugar," or is Tier 2 with immediate safety-netting
("call someone now") more appropriate? The engineering team defaulted
high per G4 because a hypoglycemic person who cannot self-treat can
deteriorate to unconsciousness before help arrives.

### OQ-7 — A1 and A2 can both apply
A1 (mild symptoms now, Tier 1) and A2 (recurrent/impaired-awareness
history, Tier 2) are not mutually exclusive — someone can have mild
symptoms right now *and* a history of frequent hypos. **The higher tier
wins (G4) and both rule IDs are reported** in the verdict and audit trail
(`engine/engine.py::_verdict` sorts all fired rules by tier, but reports
every one that fired, not only the tier-deciding rule). No clinician
action needed — this is a resolved implementation detail, included here
for transparency about how G4 combines multiple simultaneously-true rules.

### OQ-8 — no rule uses a numeric glucose value
The draft's rules are entirely symptom-based; no rule ID references a
glucose number. Per the professor's brief, **glucose value and unit are
captured for the audit trail but never fed into any rule**. A bare number
with no stated unit (e.g. "it was 20") **always** triggers a clarifying
question rather than guessing — 20 mg/dL is a severe hypo, 20 mmol/L is an
extreme hyperglycemia/DKA reading, and Pakistan's standard is mg/dL, so
guessing wrong is exactly backwards. See `lexicon.extract_glucose_reading`
and the `glucose_unit_clarify` conversational interrupt in
`session/session_manager.py`. **Open design question for a future
protocol version**: should a captured, unit-confirmed glucose value ever
be allowed to *raise* (never lower) a tier as a refinement on top of the
symptom-only decision? Not implemented in this prototype — flagged in
§4 "not yet built."

### OQ-9 — B1 and C1 are absence rules
B1 ("no vomiting, breathing change, or confusion") and C1 ("no red
flags") require the *absence* of red-flag symptoms. An unasked question
is not evidence of absence. **Every red-flag slot is tri-state
(yes/no/unknown), defaults to unknown, and a rule can only conclude
absence (NO) once the corresponding question has actually been asked and
answered no** — never inferred from silence. This is enforced structurally
by `state.TriState` (see §5) and is the single most safety-critical piece
of the tri-state design.

---

## 2. Rules invented by the engineering team (not in the draft)

These must never be mistaken for sourced clinical logic. Every one is
flagged `invented: true` in the protocol file and in every decision/audit
entry that uses it.

| Rule | What it does | Why it was added | Needs from clinician |
|---|---|---|---|
| **A4** | Conscious, can swallow, cannot reach sugar unaided → Tier 3 | Closes OQ-4 | Confirm tier; see OQ-4 above |
| **SN1** | Non-diabetes emergency (chest pain, stroke signs, severe breathing difficulty) → Tier 3, states the bot only handles diabetes, exits | The draft has no path for a genuine non-diabetes emergency raised mid-triage; silence would produce a diabetes-tier answer to a non-diabetes emergency | Confirm the exit wording is appropriate and doesn't discourage someone from calling emergency services directly |
| **SN2** | Pregnancy declared → Tier 3, out-of-scope exit | Every diabetes threshold changes in pregnancy; the draft doesn't mention pregnancy at all | This is a blunt instrument (always Tier 3/exit) — confirm this is safer than a pregnancy-adjusted rule set, which is out of scope for this prototype |
| **SN3** | Nothing fires and no further question would change the outcome → Tier 2 with safety-netting | G4 forbids ever defaulting to Tier 1 by omission; some conversations will exhaust every category rule without a clean match | Confirm Tier 2 (not Tier 1) is the right floor, and that the generic safety-netting language is adequate |
| **LOOP_SAFETY** (not a protocol rule ID — an engine-adjacent session-layer safety valve) | After 3 identical non-answers to the same pending question, stop asking and escalate to at least Tier 2 (or the tier that was already reachable, whichever is higher) | Prevents an infinite loop when extraction genuinely cannot resolve a slot (bug #4 fix); doing nothing would leave the user stuck | Confirm escalating rather than "please try again" is the right behavior — this trades a possible false Tier-2 escalation for never leaving someone stuck below a tier they might need |

---

## 3. Wording decisions needing clinician sign-off

None of the message text in `rendering/content_blocks.py` has been
clinically reviewed. In particular:

1. **Trigger lists** (`DEFAULT_TRIGGER_LISTS` for each tier) are generic
   ("come back if you become drowsy, can't keep fluids down..."). A real
   deployment should have per-scenario trigger lists (e.g. different
   wording for a hypo Tier 1 vs. a foot-problem Tier 1).
2. **Tier labels and intros** (`TIER_LABELS`, `TIER_INTROS`) — the exact
   phrasing of "home management," "BHU," "Shalamar Hospital or nearest
   tertiary facility" should be confirmed against how Shalamar actually
   wants patients to describe these options.
3. **Insulin refusal wording** (`INSULIN_REFUSAL`) — confirms the tone is
   firm but not alarming; needs sign-off that it doesn't read as dismissive
   of a genuinely anxious caregiver.
4. **Pregnancy exit wording** — currently generic ("Because pregnancy is
   involved..."); does not attempt to route to a specific obstetric
   pathway because none was specified.
5. **Under-18 exit wording** — still carries emergency safety-netting
   language per the success criteria, but the age cutoff itself (18) was
   given as a hard constraint, not derived clinically.
6. **Category question wording** (`PRESENTING_COMPLAINT_QUESTION`) — the
   five options (hypo / hyper-DKA / undiagnosed / foot / other) are an
   engineering simplification of the four symptom categories in the draft
   plus a general "something else" escape hatch. This is a **UX/flow
   decision, not a change to any rule's clinical meaning** — every rule
   from the draft still exists and fires exactly as specified once a
   category is selected — but it does mean the bot asks "what's the main
   reason" before diving into the sourced rules, which is not explicitly
   in the draft. Flagging it here for visibility.

---

## 4. Not yet built / known limitations

- **No LLM rephrasing is enabled** (`rendering/renderer.ENABLE_LLM_REPHRASE
  = False`). Every message sent is the approved template verbatim. The
  architecture supports an LLM rephrasing pass that never sees a tier and
  never authors content, but it isn't turned on for this prototype —
  turning it on is future work, and it would still need to pass through
  the same output guardrail before sending.
- **Glucose value/unit is captured but never acted on** (OQ-8). No
  refinement logic exists yet to let a confirmed reading raise a tier.
- **No persistent session storage.** Sessions live in an in-memory dict
  (`SessionManager.sessions`). A server restart loses all in-flight
  conversations. A real deployment needs a database or Redis-backed store.
- **No pregnancy-adjusted rule set.** SN2 always exits to Tier 3/out of
  scope rather than applying pregnancy-specific thresholds.
- **English only**, as scoped. No localization.
- **The audit log is a local JSONL file** (`audit_logs/audit.jsonl`), not a
  queryable database — fine for a prototype/demo, not for production scale
  or multi-instance deployment.
- **The keyword extractor's lexicon is illustrative, not exhaustive.** It
  covers the phrasings exercised by the CLI demo scenarios and the test
  suite; a real deployment needs much broader phrase coverage (ideally
  built from real transcripts) and should lean on the LLM extractor (which
  fails closed) for the long tail rather than trying to hand-enumerate
  every phrasing.
- **Meta app registration was not performed** — the WhatsApp adapter is
  built and tested (webhook verification, HMAC signature checking, replies
  with real Graph API calls when credentials are configured) but no real
  Meta Business/WhatsApp app exists to point it at.

---

## 5. Design decisions worth the clinical team understanding

These aren't open questions so much as architectural choices that
determine how the above gets enforced. Included so the "how do you know
the model isn't deciding" conversation has concrete answers.

- **Tri-state, not boolean.** Every symptom slot is `yes` / `no` /
  `unknown` (`state.TriState`). `TriState.__bool__` deliberately raises an
  exception rather than letting `unknown` be silently read as falsy/"no"
  anywhere in the codebase — this is the direct fix for the bug class the
  professor named as the reason the architecture exists.
- **G4 is structural, not a prompt.** `engine/engine.py::evaluate()` will
  not return a verdict while any not-yet-determined rule could still land
  at or above the tier already reached; it returns a "needs info" result
  naming the next question instead. See `tests/test_engine.py` for the
  executable proof.
- **The import-boundary test is the safety argument.**
  `tests/test_engine_boundary.py` parses the AST of every file in
  `diabetes_chatbot.engine` and fails the build if it imports an LLM
  client, a network library, or the extraction package. Run it any time
  someone asks "how do you know the model isn't making the decision."
- **Red flags are sticky within a session.** Once G1 (unconscious/seizure/
  not responding), SN1 (non-diabetes emergency), or SN2 (pregnancy) is
  detected from raw text, it can never be silently downgraded by a later,
  more ambiguous message in the same conversation — only ever upgraded.

---

## 6. On the source spreadsheet

`docs/Provisional_Clinical_logic_draft.xlsx` in this repository is a
**reconstruction** of the rule table exactly as given in the project
brief (the same 10 rows, IDs A1–D3/G1–G4, criteria, tiers, and source
citations), generated because the original `.xlsx` file authored by
Kashaf Gohar was not available inside this build session. If the original
file differs from this reconstruction in any way, **the original file is
authoritative** — replace the reconstruction and re-diff against
`protocol/triage_protocol.yaml` before the next clinical review.

---

## 7. Defects found and fixed during implementation

These surfaced while building this prototype (not from an earlier build)
and were fixed before the test suite went green. Listed for transparency,
since "what broke and why" is part of the record this document is meant
to carry into the room.

1. **OQ-7 reporting bug**: the engine's verdict-building step initially
   reported only the rule ID(s) at the winning tier (e.g. only `A2` when
   both A1 and A2 fired), not every fired rule. Fixed so `fired_rule_ids`
   always lists every rule that fired, sorted by tier — the winning tier
   still determines the outcome, but the audit trail shows the full
   clinical picture. Caught by `tests/test_engine.py::
   test_OQ7_higher_tier_wins_and_both_rule_ids_reported_when_A1_and_A2_both_apply`.
2. **Frozen-dataclass settings**: `config.Settings` was initially declared
   `frozen=True`, which is appropriate for `allow_patient_use` (never
   meant to change at runtime) but made test-time monkeypatching of
   per-test credentials (API keys, WhatsApp secrets) impossible. Changed
   to a mutable dataclass; `allow_patient_use`'s real protection is the
   separate module-level `ALLOW_PATIENT_USE` constant plus the protocol
   file's own `allow_patient_use: false`, both asserted equal in
   `tests/test_protocol_manifest.py`.
3. **`mg`/`mg/dL` guardrail collision**: an early version of the dose-unit
   guardrail pattern would have blocked any message stating a glucose
   reading in mg/dL, because "mg" is also a medication-dose unit. Fixed
   with a negative lookahead so `mg/dL` and `mmol/L` (glucose
   concentration units) never trip the medication-dose check. Covered by
   `tests/test_guardrail.py::test_does_not_block_glucose_reading_with_mgdl_unit`.
