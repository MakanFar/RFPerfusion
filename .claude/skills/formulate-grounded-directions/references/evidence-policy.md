# Formulation Evidence Policy

Interpret claim states as follows:

- `verified`: the quote was located in the cited paper and an independent entailment call judged that it supports the claim.
- `partial`: the located passage supports only part of the claim.
- `unsupported`: a real retrieved passage did not support the claim.
- `quote_mismatch`: the offered quotation could not be located in the cited paper.
- `no_evidence`: retrieval completed without a supporting passage. This is weaker than refutation because corpus and index coverage are incomplete.
- `error`: retrieval or verification failed; do not treat the claim as searched successfully.

A verified refutation is evidence against a claim and must remain visible. Only load-bearing claims determine the grounding fraction and grounding cap. Supporting claims add context but cannot repair an ungrounded foundation.

Report the decomposed axes rather than only the overall score: grounding, evidence strength, mechanistic plausibility, novelty, and testability. If `cap_applied` is true, state the cap and which load-bearing claims failed to verify.

The session JSON is the machine-readable audit trail. The Markdown report is the citable human artifact. Keep both together.
