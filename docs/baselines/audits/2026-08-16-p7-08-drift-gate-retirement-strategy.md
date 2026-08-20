# P7-08b Same-Batch Drift-Gate Retirement Strategy (Provisional Proposal)

The P7-08 blocker `blocked_no_path_scoped_replacement_and_retirement_approval`
requires, before any legacy path can be deleted: a per-path replacement
mapping, a required profile accepted, same-batch drift-gate removal,
release/license/fresh-machine gates, and explicit owner retirement approval.
This audit records the working-tree proposal that advances the same-batch
drift-gate removal and retirement-approval strategy items; it is not yet
committed and does not remove any gate.

## Deliverables

- `docs/baselines/p7-08-drift-gate-retirement-strategy.v1.yaml` — provisional
  strategy (`approval_state: awaiting_owner_approval`, blocker unchanged)
  registering 37 drift gates: 20 legacy M0-M5 migration gates and 17
  historical-evidence drift gates (P3C source drift, TRAN external-compare
  v1-v3, channel matched external-compare v1-v7). It encodes the batch
  rule (deletion and drift-gate removal in the same batch, only AFTER
  new-path acceptance) and a four-step retirement procedure.
- `tools/verify_p7_08_drift_gate_retirement_strategy.py` — mechanical verifier.
  It fails closed if: approval_state drifts from `awaiting_owner_approval`;
  the P7-08 blocker is removed; any entry claims a removal/retirement
  disposition; the retirement procedure or mandatory gate set changes; a
  gate path uses glob characters; a tracked-file count drifts from live
  `git ls-files`; a registered gate path disappears; or the required gate
  set loses coverage.
- `tools/test_verify_p7_08_drift_gate_retirement_strategy.py` — 14 tests,
  including live `git ls-files` count binding for every gate and negative
  probes for approval drift, blocker removal, removal dispositions, claim
  tokens, glob paths, gate dropping, coverage gaps, and procedure drift.

## Verification

`python -B -m unittest tools.test_verify_p7_08_drift_gate_retirement_strategy`
passed 14/14. `python -B tools/verify_p7_08_drift_gate_retirement_strategy.py`
returned `valid: true` for all 37 entries with render SHA-256
`b38a411c639578db4f08d0bab3a79dec894b834013be9f6ce2d29a45c6490889`.

## Artifact Hashes (SHA-256)

Captured after the final test run; regenerate before relying on them:

- strategy: `0B0FE37D29ACAE10D9826CE4CFB6D7981075444E5DDF9DB36B04D6A21DBB05D2`
- verifier: `4518EB8D82A3EC6027940BCC9B769C1037196BD5CD69131C52A0C3D049F23BC4`
- tests: `5A19E07E81F1BF7CFC1E5DEE99EE93976CA8F3461A733857F3B7FC8A8784A7D4`

## Scope and Non-Claims

- This strategy is a proposal only. It does NOT remove any drift gate,
  grant retirement approval, accept any profile, delete any path, or
  unblock P7-08.
- Every registered gate stays `retain_gate_awaiting_approval`; removal in the
  same batch as legacy deletion is permitted only after new-path acceptance
  and explicit owner retirement approval (enforced by the verifier).
- Historical M0-M5 and external-compare evidence remain retained historical
  evidence; they are not rewritten as current acceptance.
- P7-08 stays blocked until the owner approves the map and strategy and the
  remaining mandatory gates pass. No `rc` tag or release promotion is implied.
