# P6-09a Current-Topology Negative Gate Audit

- Scope: the P6 current-topology negative integration test, its test-only
  `sipi-pipeline` dependency, specification, P0 inventory refresh, and PLAN
  wording.
- Reviewer: one Orca terminal reviewer,
  `term_ac58e303-f0a2-4fd5-b5b7-b8e7c119e832`.
- Result: `0 P1 / 0 P2`.

The reviewer independently ran the focused integration test, existing CLI,
pipeline and runtime tests, clippy, and every P0 verifier. It confirmed that
a declared `tran.result -> link.request` project edge is rejected by the
non-executing planner before any domain work, and that a changed causal-FIR
policy cannot satisfy a record generated under the original policy.

The reviewer also confirmed that pre-cancelled and under-budget edge attempts
return no completed value, that an unsealed staging directory and a modified
published payload produce only the ordinary failure envelope plus diagnostic,
and that the positive report omits the temporary root, payload filename and
payload schema. The test-only publication bridge remains a dev dependency and
does not add a product route or executor.

Three non-blocking observations were recorded: the rejected-attempt test no
longer contains a vacuous filesystem assertion because this attempt API has no
file-I/O surface; the unsealed scenario covers the pre-seal staging state
rather than the sealed-but-unpublished rename window; and record drift is
tested through a changed policy/output pair rather than a separate output-only
variant. None changes the P6-09a acceptance scope.

Worker crash remains explicitly outside the current P6 topology. It is
separately exercised by P4B mock-worker tests and must not be presented as P6
worker integration evidence. This audit does not accept project execution,
multi-edge recovery, retry/cache behavior, AMI/COM integration, external
comparison, or a generic fault framework.
