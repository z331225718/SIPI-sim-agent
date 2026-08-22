# PyBERT upstream-first migration audit

## Scope

This audit covers the five stable numeric CLI workflows at the exact PyBERT
Git revision 5bf6d7ea0ace261891aaeb611ffc1c267e160afe. The source tree is
5faef6bdb341d444ad65d82a11c0018b15805e24; the CLI blob is
4c1116007d31bcebf8db3252363eed7774c7b349 and its content SHA-256 is
3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9.
The audit uses Git objects only. No PyBERT source bytes, fixture, array,
payload, DLL, or local source path is stored in this repository.

The implementation is intentionally a process-external adapter in
crates/sipi-pybert-adapter. It is transport and provenance work, not a new
simulation feature and not a Rust numerical replacement. Existing SIPI Rust
algorithms remain candidates until independent parity evidence is supplied.

## License and runtime boundary

The new adapter crate is project-owned MIT code. The external PyBERT source
and its BSD-3-Clause license remain outside the repository. The adapter
contract is derived from the pinned Git identity, but the launched executable
is caller supplied and its runtime bytes are not attested; results therefore
record `contract_source` separately from an unauthenticated runtime identity.
No PyBERT source bytes were copied or translated into the adapter. NumPy, SciPy,
scikit-rf, pyibis-ami, optional pybert-native, optional IBIS-AMI DLL/SO files,
and other runtime assets remain external dependencies; this slice does not
grant redistribution or release rights for them.

On Windows the adapter uses process-wrap 9.1.0 with its std and job-object
features. That dependency is offered under MIT OR Apache-2.0 and is linked
only on the Windows target. The child is created suspended, placed in a Job
Object, and only then resumed. A wrapper inside the Job Object setup kills
the still-suspended child if Job creation or assignment fails, so the adapter
does not silently fall back to an uncontained process. Timeout, cancellation,
output overflow, and post-parent stream drain all terminate the Job Object.
After assignment, an outer kill-on-drop guard also attempts Job termination
on unexpected polling or child-I/O early returns; it is distinct from the
inner suspended-child guard used while Job setup is incomplete.
On non-Windows targets the adapter honestly claims only direct-child kill,
not descendant-tree containment.

## Reachable workflow inventory

### PB-01: sim

The pinned CLI constructs PyBERT, loads PyBertCfg, and runs
PythonSimulationBackend, which delegates to PyBERT.simulate. Depending on
configuration, that path reaches the default analytic channel or imported
S-parameter channel, source/load termination and normalization, impulse/step/
pulse construction, TX FFE and noise, RX CTLE/FFE/DFE, CDR, jitter, eye/BER,
statistical-eye/bathtub, optional Viterbi/FEC, and optional IBIS-AMI
Init/GetWave paths. It writes the legacy PyBertData pickle result. When
--results is absent, the upstream default is the configuration basename with
a .pybert_data suffix. The adapter preserves that optional argument while
resolving the same default path and including its published bytes in the
artifact SHA-256 inventory.

### PB-02: sim-native

The CLI reads a strict NativeSimulationRequest JSON object and invokes
RustSimulationBackend. The optional pybert-native extension owns the native
numerical entrypoint. The request explicitly distinguishes typed native JSON
from legacy configuration and does not coerce unsupported fields. The command
publishes meta.json and arrays.npz under the required output directory. The
adapter requires both names to be regular, non-link files after a successful
run and does not decode either numeric payload.

### PB-03: sim-rust

The CLI loads the legacy configuration, projects it through
legacy_pybert_to_web_request, and invokes the web/native backend. The
projection can expose channel selection and impulse controls, TX taps and
optional TX IBIS-AMI, RX CTLE/FFE and optional RX IBIS-AMI, DFE/CDR/FEC,
jitter, sampled/statistical eye, and BER branches. Unsupported legacy
controls are errors at the upstream projection boundary rather than adapter
defaults. The optional statistical-eye point count is passed through exactly.

### PB-04: sim-auto

The CLI first builds and validates the native projection and evaluates the
native auto-parity gate. A validation or parity-gate failure selects the
Python reference engine and records the reason. A native runtime failure
after native validation is surfaced as an error; it is not converted into a
successful Python result. Successful artifacts must therefore contain
diagnostics.engine_selection, including requested backend, selected backend,
fallback reason, and parity-gate observation when present. The adapter
requires and records this selection instead of inventing one.

### PB-05: sim-compare

The CLI always runs the Python reference first. It then projects and runs the
native candidate and calls compare_backend_results. Candidate mapping,
validation, or runtime errors become an explicit passed: false comparison
report while the reference artifact remains available. The adapter forwards
the command and inventories the output; it does not reinterpret numerical
comparison, tolerances, alignment, or acceptance.

For PB-03, PB-04, and PB-05 the same pinned `_write_native_artifacts` helper
publishes `meta.json` and `arrays.npz`; both are therefore minimum regular
artifacts for every successful directory route. An empty directory or
unrelated file cannot substitute for either one. PB-01 instead requires the
resolved explicit or default `.pybert_data` regular file. Extra files remain
bounded inventory entries and do not change these minimums.

The resolved result file or output directory must be absent before spawn.
This prevents a successful zero-output child from satisfying the contract
with stale files from a prior run. Recursive inventory rejects symlinks and
Windows junction/reparse entries at every depth, and each canonical regular
file must remain beneath the canonical output root. The target is caller
owned for the duration of the run; custody against a concurrent hostile
writer is not claimed.

## Dependency and branch boundary

The exact source object reaches the following reusable numerical families:

- channel: pybert.pybert.calc_chnl_h, utility.channel, utility.sparam,
  and utility.sigproc;
- TX/RX/equalization: models.bert, models.dfe, models.tx_tap,
  utility.sigproc, and optional utility.ibisami;
- jitter and eye/BER: utility.jitter, utility.sigproc,
  utility.statistical_eye, and result extraction in the backend adapters;
- external runtime: NumPy, SciPy, scikit-rf, pyibis-ami, optional
  IBIS-AMI DLL/SO files, optional pybert-native, and PyChOpMarg where the
  source configuration requests it.

The adapter is deliberately ignorant of these dependencies. It supplies the
caller executable and input paths, invokes one named command, captures bounded
stdout/stderr, polls a deadline and cancellation marker, and records a
symlink-free SHA-256 inventory of published files. It never changes input
units, defaults, sample alignment, resampling, tolerance, or algorithm.

## Verification

The standalone crate tests use a fake executable only to test transport:
command shape, auto-selection reporting, artifact inventory, output bounds,
timeout, minimum-artifact rejection, parent-exited descendant termination on
Windows, stale-output rejection, nested-junction rejection, and missing
selection. The exact-source smoke verifier accepts an
explicit external PyBERT root and verifies the pinned commit, tree, CLI blob
identity, and CLI SHA-256; it does not copy or vendor that source.

This slice is therefore adapter_implemented_parity_unbound for PB-01 through
PB-05. It does not close Rust parity, source licensing, native wheel custody,
AMI/DLL rights, oracle corpus, or release gates.
