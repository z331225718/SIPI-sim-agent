# AS-06 Agent-Spice Attribution Successor

This additive notice records the explicit-custody boundary for the existing
Agent-Spice native `run-rfm` dispatch. It does not port the native engine or
claim solver correctness, numeric parity, or release promotion. Native
execution is fail-closed unless the caller supplies an absolute regular
executable and its exact SHA-256; the AS-06 native-specific bounded process
helper provides bounded pipes, timeout, fresh user-init roots, and clears the
documented .NET/native-loader injection variables without changing the
ordinary ngspice/AS-05 helper environment. The AS-06 route records
the executable pre/post SHA and rejects drift after the process exits. A
caller-attested dotnet host is required for the existing managed-engine
branch. Native result JSON and waveform CSV are regular non-symlink files,
bounded and receipt-checked; waveform rows must match `waveformRows` and the
unique nonzero `v(out)` observation. The ngspice/code-model branch remains
covered by the v2 notice.

Upstream project: `agent-spice`
Commit: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
Tree: `b6bde97128030d6cea0d68b2f0a35d807be8c402`
License: MIT (`LICENSE`, Git blob `55aac2e4f8c36a978d315efb02815972579b8293`,
1067 bytes, raw-byte SHA-256
`d0807e4df7340fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`)

The pinned native backend dispatch source is:

* `src/agent_spice/backend/native.py`: Git blob
  `4e2f327a9a10b8de876e83df1fb31c359ba063f4`, 4146 bytes, raw-byte SHA-256
  `79b20cb1d172fe778be9fab260a9989f186159fd191b767bce8d9337466ddabc`.
  Its role is retained external native-engine dispatch, not a portable
  implementation of the engine.

The pinned native output contracts are also inventory-bound:

* `native/AgentSpice.Engine/Program.cs`: Git blob
  `ca7c89a48a7f812227f09c673c69ecafa67490e4`, 4195 bytes, raw-byte SHA-256
  `22f1908f78a0a379e1373f5cb122594fa1a4d3e599333525d4d66a24ae322887`.
* `native/AgentSpice.Engine/WaveformWriter.cs`: Git blob
  `2153477801f86bbcc86a555284b67a4925122ba8`, 1950 bytes, raw-byte SHA-256
  `76369f3ba255e82c94b3bb1ba300bd436191cabe1ae8ec211ac396ef2c5966fd`.
* `native/agent-spice-sim/src/main.rs`: Git blob
  `a333857287fc093f2f1fa515b135fe31a2bc9eb1`, 21371 bytes, raw-byte SHA-256
  `3c04cafa75cfa9ffee60da09331ac007d82a0fd44a451775b6e193375d55f427`.
* `native/agent-spice-sim/src/output.rs`: Git blob
  `c4df009459c34a24eafbc45183fa228076ff5d40`, 9143 bytes, raw-byte SHA-256
  `b2ab10ddf8e6f349c660e28108115617a56f70e25b0b112fbe29db541b025771`.

These native source files are output-contract authorities only; no native
binary E2E or solver parity is claimed in this Rust crate.

Rust custody is implemented in
`crates/sipi-agent-spice-direct/src/as06_run_rfm.rs` as the additive
`RfmNativeCustody`/`run_rfm_with_native_custody` entry point and uses the
bounded helper in `src/lib.rs`. The request executable and caller custody
identity must resolve to the same path; pre/post identity drift is rejected.

The v2 candidate-local RFM grammar adaptation remains in force: the pinned
Python writer emits `CONST`, `C`, and `DELAY`, while the caller-attested
runtime accepts the existing `Const`-only form. This is not byte-exact source
parity and does not imply a portable code-model implementation.

Scope: `retained_external_runtime`, with native workflow execution
available only when the caller supplies and attests the external runtime.
External-solver correctness, numeric parity, SI S-parameter fitting, and
release promotion are not claimed. The receipt checks are bounded ordinary
drift checks; hostile-writer and complete TOCTOU defense are not claimed for
caller-owned roots.
