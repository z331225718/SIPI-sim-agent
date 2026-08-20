# P5-06d Canonical Normalized-Input Key Signature Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06d (canonical normalized-input key signature core)
- Status: delivered and cross-checked against an independent reference and
  the authoritative P5-06c surface. Advancing compare-readiness for the
  pending P5-06 compare matrix without invoking the MATLAB oracle.

## Method

Implement canonical_input_keys_v1.rs: given the normalized COM in_config
keys as (key, canonical value token) pairs, produce the byte-wise
lexicographically sorted canonical 'key=value' signature lines; the runner
adds a stable SHA-256 digest over the newline-joined lines. The canonical
value token is caller-supplied (float formatting is not normalized here so
product and reference agree on the exact token). Cross-check compares the
product path (runner binary) against an independent Python reference across
9 scenarios - 8 synthetic happy/fail cases plus the authoritative extraction
of the 82 in_config keys from the P5-06c surface - matching lines and digest
exactly.

## Result

- 9/9 matched_hash_bound, exercising BOTH happy paths (sorted keys, stable
  unsorted digest, value tokens with spaces, nested token lists) and failure
  paths (empty key, empty value, duplicate key, empty input).
- Authoritative in_config surface: 82 keys, product digest 9332d697... equals
  the independent reference digest.
- sipi-com unit suite 208 tests green (6 new canonical_input_keys tests).
- Profile-agnostic compare-readiness preflight only; no compare matrix, no
  metric derivation, no oracle invocation.

## Binding

- Verifier verify_p5_06d_canonical_input_keys.py + 6 tests; crosscheck
  evidence docs/baselines/p5-06d-canonical-input-keys-crosscheck-evidence.v1.yaml.
- Charter p5-06d-canonical-input-keys-stage.v1.yaml; source map
  p5-06d-mit-source-map.v1.yaml.
- PLAN **P5-06d**; ledger note/gate P5-06; coverage gates 109 -> 110.
