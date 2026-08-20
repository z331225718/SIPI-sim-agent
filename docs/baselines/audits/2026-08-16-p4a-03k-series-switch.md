# P4A-03k Typed IBIS Series Switch Groups Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03k (typed IBIS [Series Switch Groups] core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_switch_groups_v1.rs` in `sipi-ibis`: `TypedSeriesSwitchGroupV1`
holds a validated ASCII group name (`[A-Za-z0-9_.-]+`), ON-state model list (`on_state_models`),
and OFF-state model list (`off_state_models`).
`lift_series_switch_group_v1` validates inputs and returns `Result<TypedSeriesSwitchGroupV1, SeriesSwitchGroupsErrorV1>`.
Fail-closed: empty group name (`EmptyGroupName`), non-ASCII characters (`NonAsciiGroupName`), invalid name
spellings (`InvalidGroupName`), empty state model lists (`EmptyStateModels`), or duplicate models within a state list
(`DuplicateModelInGroup`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full switch group; valid ON-only switch group;
  empty group name rejection; empty state models rejection; duplicate model in group rejection).
- Cross-check: 3 test cases (full switch group, ON-only switch group, empty state models)
  driven through product runner `p4a_03k_series_switch_runner`; independent Python reference
  matches 100% on valid flags, group names, state model lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03k_series_switch.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03k-series-switch-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03k-series-switch-stage.v1.yaml`; source map
  `p4a-03k-mit-source-map.v1.yaml`.
- PLAN **P4A-03k**; ledger note/gate P4A-03; coverage gates 124 -> 125.

## Scope / Non-Claims

- Not a full IBIS file parser; no dynamic series switch simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
