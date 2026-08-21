# P5-08h main scoped closure

P5-08h is an additive current disposition for owner decision `D6=A`. It
supersedes the current disposition recorded by P5-08g without changing that
historical record. The selected public route is the narrow
`com run-artifact` command: caller-owned explicit parameter partitions, one
sealed exact `pulse.f64le` artifact, and a caller-owned output root/id. The
legacy `com.run` command remains unavailable.

This closes the P5-08 main checklist item only for the selected
specified/non-oracle route. It does not promote generalized COM conformance,
Agent-COM parity, an authoritative profile or oracle, external provenance,
acceptance, hostile-writer safety, workbook ingestion, IEEE certification, or
release evidence. Those statements remain unchanged from P5-08g. P5-02 and
P5-06 remain external blockers; P7 remains a release blocker.

The verifier first invokes the current product `commands --json` surface and
passes that result through the publication verifier. It then checks the
publication row for `com.run-artifact` (`available`/`specified`/non-oracle),
the legacy `com.run` row (`unavailable`/`blocked`), the exact request/result
schemas, and the command protocol descriptor. It calls the historical P5-08g
verifier and binds its immutable SHA-256, requiring the historical
`p5_08_main_item_closed: false` disposition to remain intact. Budgets,
schema identifiers, threat-model flags, and non-claims are copied exactly
from that record and are checked for drift.

Focused mutation tests cover route promotion, historical tampering, main-item
reopening, budget/schema/threat/non-claim drift, and accidental promotion of
P5-02/P5-06/P7. Rust command-manifest and COM artifact tests, ledger/coverage,
session health, and the P0 boundary/license/source-map gates are run as
verification; this closure remains pre-release evidence only.
