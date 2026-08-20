# P5-02k MATLAB Numeric Literal / Vector-Matrix Defaults — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02k (full parse_matlab_literal port: vector/matrix
  default layout)
- Status: delivered and cross-checked against the agent-com Python oracle.
  The product parser is a declared superset of the oracle for two-part colon
  ranges; that boundary is recorded as an oracle limitation, not a match.

## Method

Port agent_com.config.literals.py into sipi-com matlab_literal_v1.rs:
- parse_matlab_literal dispatch: [] -> Empty; [..] -> vector/matrix (rows
  split by ';', each row via _vector after _expand_scaled_ones); bare colon
  range -> vector; else scalar.
- _vector row semantics: colon-space compaction, single-negative
  disambiguation ([1 - 2] == -1 vs [1 -2] == [1,-2]), split on spaces/commas,
  per-token colon-range expansion or scalar evaluation.
- _COLON three-part ranges (N:M:K); single-digit two-part ranges are an
  oracle limitation (ValueError in agent-com because it unpacks only non-None
  groups), the product expands them (superset).
- _expand_scaled_ones: bounded N*ones(1,M) with 1 <= M <= 4096 inside a
  bracket row.
An external-custody cross-check binds the product parser to the oracle across
15 literal cases; a declared oracle-limitation case is verified to raise in
the oracle and is recorded with product superset value.

## Result

- 15/15 literal cases matched hash-bound (tolerance 1e-12): [1 3 2 4],
  [50,50], [0 0], [1 2; 3 4], the 14-row pkg_Z_c-style matrix, [1:1:3],
  [1 - 2] / [1 -2], [-50 -50], [0.5*ones(1,4)], scalars 78.2 / 92 /
  6.191e-3 / 0.5*1e9, and the [] empty literal.
- Oracle limitation [1:3] verified: agent-com _vector raises ValueError
  (oracle_raises: true); the product expands it to [1,2,3] and that value is
  recorded as the product superset, not a mutually matched reference.
- sipi-com unit suite 150 tests green (6 new matlab_literal tests).

## Binding

- Verifier verify_p5_02k_matlab_literal.py + 6 tests; crosscheck evidence
  docs/baselines/p5-02k-matlab-literal-crosscheck-evidence.v1.yaml.
- Charter p5-02k-matlab-literal-stage.v1.yaml; source map
  p5-02k-mit-source-map.v1.yaml.
- PLAN **P5-02k**; ledger note/gate; coverage gates 88 -> 89.
