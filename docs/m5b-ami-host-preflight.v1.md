# M5B-04 Rust AMI Host Route Preflight

Status: blocked preflight as of 2026-08-08. This record is a capability and
provenance boundary; it neither changes a numerical algorithm nor makes an AMI
parity claim.

## Fixed Inputs

- Clean PyBERT source candidate: `codex/m5b-source-gates@f6ba031`. The
  user-owned PyBERT main worktree is not evidence or an implementation source.
- A public repository fixture is available for a future Windows runtime test:
  `models/ibisami/example_rx.ibs`, `example_rx.ami`, and `example_rx.dll`.
  Existing PyBERT tests prove only the retained Python-hosted hybrid route.
- The existing `docs/baselines/capability-inventory.yaml` entry
  `py-hybrid-ami` separately records the fixture-distribution compliance
  blocker (`blocked_unknown`, owner `compliance`). This preflight does not
  clear or replace that evidence.
- The SIPI clean-room `sipi-ami` crate already exposes public-ABI
  `AmiDll`/`AmiModel` Init, GetWave, and Close lifecycle methods. That library
  contract is not a process route and has no PyBERT production registration.
- Runtime probe (2026-08-09, before the parser follow-up): `ami-inspect`
  rejected the repository's public `example_rx.ami` with `missing AMI
  parameter AMI_Version`. The follow-up clean-room parser slice now extracts
  the three typed host values only from standard `Reserved_Parameters`, while
  preserving the existing top-level tree API. Its unit fixture also proves
  that a same-named `Model_Specific` value cannot override reserved metadata.
  The real public fixture now passes `ami-inspect`; this verifies metadata
  admission only, not DLL loading, `AMI_Init`/`AMI_GetWave` execution,
  candidate-bundle promotion, or a PyBERT route.

## Blocking Evidence

The currently locked Windows `agent-spice-sim.exe` is the only executable
approved by `native/crates/sipi-circuit/engine.lock`:

- SHA-256: `111ff6e1a1a8f7f39782a355722c56f4d8e7392bff6d389445ba87dee73928dc`
- Size: `4604416` bytes
- Lock protocol CLI subcommands: exactly `build-info` and `rfm-response`.

It has no versioned AMI host request/response subcommand. The SIPI working-tree
binary is not an acceptable substitute: it is neither the locked artifact nor
a promoted bundle. Consequently, a PyBERT process adapter cannot honestly
claim to invoke a lock-constrained Rust DLL host today. Adding a new command
would be a new executable protocol and requires a candidate bundle, hash,
engine-lock promotion, and independent runtime validation; it cannot be
silently smuggled through the existing RFM lock.

The wrapper-layout prerequisite is now covered by the clean-room parser and
the public metadata probe. A future `ami-host` transport may therefore attempt
`AmiDll::load` only under its own candidate-bundle contract. This parser work
does not permit copying PyAMI behavior or inferring AMI numerical parity from a
successful metadata read.

## Required Follow-on Contract

M5B-04 remains open until a separately versioned host process contract exists.
Its minimum request must bind executable and DLL identities, `.ibs`/`.ami`
identities, `dt`, bit time, Init impulse, optional GetWave waveform, clock
capacity, and parameter string. Its response must carry the Init/GetWave
arrays, clocks, lifecycle outcomes, process provenance, and an auditable Close
outcome. The PyBERT-side adapter must select `rust-host` explicitly, use the
locked executable only, fail closed on lock contention, cancellation, timeout,
malformed or partial output, and hand the valid waveform to the existing Rust
DFE/CDR receiver input without calling Python ctypes on that route.

The retained Python host stays an independent `reference` route. Even after a
host process exists, a lifecycle/transport pass is not AMI waveform, BER, or
eye parity and does not authorize a default, GUI, optimizer, Linux, or macOS
claim.
