# Clinician sign-off

One file per rule series (A-series, B-series, ...). Each file records, per
rule ID, whether a clinician has reviewed and approved it, who, and when.
This lets a signed A-series move forward into `allow_patient_use` while the
D-series (D3 is unsourced) is still under discussion.

**Nothing in this directory currently carries a real signature.** Every rule
is `PENDING_CLINICAL_REVIEW`. The placeholder files (`A-series.md`,
`B-series.md`, `C-series.md`, `D-series.md`, `global-and-safety-nets.md`)
show the format a clinician will fill in.

This directory is documentation only — it is not read by the engine at
runtime. The engine's behaviour is controlled by `protocol/triage_protocol.yaml`
(`status`, `invented`, `unsourced` fields) and `allow_patient_use`.
