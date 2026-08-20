# P7-08 Path-Scoped Replacement Map (Provisional Proposal)

The P7-08 blocker `blocked_no_path_scoped_replacement_and_retirement_approval`
requires, before any legacy path can be deleted: a per-path replacement
mapping, a required profile accepted, same-batch drift-gate removal,
release/license/fresh-machine gates, and explicit owner retirement approval.
This audit records the working-tree proposal that advances the first item only; it is not yet committed.

## Deliverables

- `docs/baselines/p7-08-path-scoped-replacement-map.v1.yaml` — provisional
  map (`approval_state: awaiting_owner_approval`, blocker unchanged) with 24
  entries covering the legacy Python platform, adapters, engine, fixtures,
  native quarantine crates, M0-M5 drift evidence (each of the five m5b-
  prefixed preflight records bound by exact path under docs/baselines), and
  audits.
- `tools/verify_p7_08_path_scoped_replacement_map.py` — mechanical verifier.
  It fails closed if: the map loses `awaiting_owner_approval` or the P7-08
  blocker; any entry claims a deletion/retirement disposition; any approval-
  required entry drops a mandatory pre-deletion gate; a replacement owner names
  a missing crate; a recorded tracked-file count drifts from live `git
  ls-files`; or the map stops covering the P7-08 legacy surface.
- `tools/test_verify_p7_08_path_scoped_replacement_map.py` — 15 tests,
  including live `git ls-files` count binding for every entry.

## Verification

`python -B -m unittest tools.test_verify_p7_08_path_scoped_replacement_map`
passed 15/15. `python -B tools/verify_p7_08_path_scoped_replacement_map.py`
returned `valid: true` for all 24 entries with render SHA-256
`f7a6f4d1d05bc93ecc06f1054ae1d67ec2588e9da411ecc8210d0b9d906e14f2`.
An independent adversarial review ran bypass probes against the verifier;
it found no bypass of the machine-checked constants and its two medium
findings (subset-satisfiable coverage predicate, unguarded glob prefixes)
were fixed: coverage now requires exact path matches, glob characters in
path_prefix are rejected, replacement_status is a closed vocabulary, and
free-text fields cannot carry approval/retirement/release claim words.

## Artifact Hashes (SHA-256)

Captured after the adversarial-review fixes; regenerate before relying on them:

- map: `CB1E60FD42AB612BD12F09B8267DD6B4C1CA4C86F1A57F999F87977B7D40FD70`
- verifier: `BFE444A99389EDCB537B57574546972C24CA795E35ADE7BE10157D854119123B`
- tests: `25C91A91116DBC85F37D821777AD6784559A93BB5BB2C0E08553B6C50CEB93EA`

## Scope and Non-Claims

- This map is a proposal only. It does NOT grant retirement approval, remove
  any drift gate, accept any profile, delete any path, or unblock P7-08.
- The map's dispositions are all retain/quarantine; no entry may claim a
  deletion or retirement disposition while `approval_state` is
  `awaiting_owner_approval` (enforced by the verifier).
- Historical M0-M5 evidence and audits are recorded as retained migration
  evidence; they are not rewritten as current acceptance.
- P7-08 stays blocked until the owner approves the map and the remaining
  mandatory gates pass. No `rc` tag or release promotion is implied.