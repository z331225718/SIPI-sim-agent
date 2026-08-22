# Upstream to Rust Candidate Coverage Audit

Date: 2026-08-22

Evidence: `docs/baselines/upstream-rust-candidate-coverage.v1.yaml`

## Decision

This is a migration coverage audit, not numerical parity acceptance. All fifteen
pinned upstream rows now have both a bounded process-external Rust adapter and a
reachable product CLI route under `sipi upstream ... --stdin`. Those routes
execute the pinned upstream workflow through a caller-selected runtime; they do
not make the upstream numerical implementation a native SIPI capability.

Every row is therefore classified `partial_surface`: transport and artifact
admission exist, while branch-complete Rust replacement and independent
upstream parity remain open. No row is `direct_surface`, complete, accepted, or
release-ready. The adapters do not attest the caller-selected executable or
interpreter as the pinned source object.

Self-tests, fake-runtime integration tests, fixed profiles, bounded kernels,
generic compare routes, and the process-external adapters are useful evidence
only. None of them is an independent upstream oracle or Rust numerical parity.

## Shared Integration Surface

- Agent-Spice rows use `sipi-agent-spice-adapter` and six product CLI routes:
  `fit-sparam`, `fit-sparam-cascade`, `fit-yparam`, `tune-yparam-tran`,
  `run-hspice`, and `run-rfm`.
- PyBERT rows use `sipi-pybert-adapter` and five product CLI routes: `sim`,
  `sim-native`, `sim-rust`, `sim-auto`, and `sim-compare`.
- Agent-COM rows use `sipi-agent-com-adapter` and four product CLI routes:
  `config-validate`, `run`, `compare`, and `public-api`.
- `crates/sipi-cli/src/upstream_migration.rs` owns typed request projection and
  adapter dispatch. `crates/sipi-cli/src/main.rs` publishes all fifteen routes.

All three adapters bound request bytes, arguments, time, stdout/stderr, and
artifacts. Their platform-specific process containment and artifact rules are
defined by their dedicated evidence; this coverage audit does not widen those
claims.

## Row Findings

### Agent-Spice

- `AS-01 fit-sparam`: external transport is integrated. Existing Touchstone and
  rational-fit kernels remain related Rust candidates, but target-order search,
  passivity policy, complete artifact mapping, and independent fit-oracle parity
  are open.
- `AS-02 fit-sparam-cascade`: external transport is integrated. Ordered block
  composition and a branch-complete Rust cascade implementation are open; the
  single-fit kernels are not cascade parity.
- `AS-03 fit-yparam`: external transport is integrated. A native Y-domain fit,
  inversion/export path, passivity policy, and independent parity are open.
- `AS-04 tune-yparam-tran`: external transport is integrated. The Y-RFM
  transient residual loop, backend behavior, tuning search, output RFM, and
  parity are open. The bounded RC measurement profile is not this workflow.
- `AS-05 run-hspice`: external transport is integrated. The bounded RC/PULSE
  profile remains useful local coverage, but generic conversion, include
  staging, backend selection, result parsing, and parity are open.
- `AS-06 run-rfm`: external transport is integrated. Native RFM parsing,
  code-model staging, process/backend replacement, and parity are open.

### PyBERT

- `PB-01 sim`: external transport is integrated. Receiver, PRBS, equalizer, and
  waveform kernels are related candidates; legacy configuration, callbacks,
  exact result artifacts, and numerical parity are open.
- `PB-02 sim-native`: external transport is integrated. The Rust replacement
  still needs exact `SimulationInputV1`, native selection/diagnostics, result
  artifact behavior, and parity.
- `PB-03 sim-rust`: external transport is integrated. Legacy YAML projection,
  Web request/result mapping, native backend behavior, and parity are open.
- `PB-04 sim-auto`: external transport is integrated. Native validation, parity
  gating, explicit Python fallback semantics, diagnostics, and independent
  parity remain open in the Rust replacement.
- `PB-05 sim-compare`: external transport is integrated. Existing aligned-array
  and waveform comparators do not yet replace PyBERT result loading, compare
  artifacts, or Web/GUI-compatible behavior.

### Agent-COM

- `COM-01 config-validate`: external transport is integrated. Bounded XLSX/MAT
  readers and parameter reports are related candidates; profile materialization,
  warnings/capabilities, canonical output, and parity are open.
- `COM-02 run`: external transport is integrated. The bounded product COM chain
  does not yet replace the complete channel/equalization/calibration pipeline,
  progress/reporting behavior, or numerical parity.
- `COM-03 compare`: external transport is integrated. Typed local comparators do
  not yet replace Agent-COM result/golden loading, exact mismatch reporting, or
  independent parity.
- `COM-04 load_config-run_com-write_artifacts`: the external `public-api` route
  is integrated. Native public API equivalence, complete pipeline behavior,
  HTML/result artifacts, and golden parity are open.

## Provenance

The evidence binds all three pinned commits, trees, CLI blobs, and reachable
module paths, plus exact hashes for the three adapter libraries, CLI dispatch
module, CLI route registry, active migration inventory, and every listed local
candidate. A source-root verification checks Git blob IDs and content hashes
without copying upstream source bytes into this repository.

Agent-Spice research commands and RFM exploration, PyBERT Web/GUI/Redis worker
surfaces, and Agent-COM MATLAB/workbook/golden/reporting surfaces remain
explicitly accounted. They do not become numerical migration completion merely
because their CLI workflow is externally reachable.

## Recommended Order

1. Freeze the fifteen external routes as executable upstream baselines and
   capture representative input/output artifacts from the pinned sources.
2. Migrate configuration, input projection, result loading, artifact shape, and
   diagnostics before replacing numerical internals.
3. Replace one upstream branch at a time in Rust, using an independent pinned
   upstream oracle and route-specific tolerances.
4. Promote a row only after branch inventory, numerical parity, artifacts, and
   public reachability pass; transport existence alone can never close a row.

## Integration Warnings

- Do not change the active migration inventory, PLAN, release ledger, P0
  registers, or license/source map as part of this audit.
- Do not identify a caller-selected runtime as the pinned source without runtime
  attestation.
- Do not treat fake-runtime tests, external transport, fixed profiles, generic
  compare, or bounded product kernels as numerical parity.
- Do not stage or redistribute source bytes from the three upstream objects.
- Preserve unrelated worktree changes.
