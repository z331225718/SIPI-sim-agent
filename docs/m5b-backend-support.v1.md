# M5B Backend Support Matrix

This matrix records product-facing routing status. It is a gate, not a claim
that every listed candidate has numerical parity.

| Surface | Python reference | Approved native subset | Python-hosted AMI hybrid | Rust AMI host | Optimizer |
| --- | --- | --- | --- | --- | --- |
| Web | Default/reference for unsupported profiles; `auto` may select its approved native candidate | Only the seven approved profiles; strict `rust` fails closed outside them | Explicit `hybrid-ami`; Python owns the vendor DLL and Rust resumes at DFE/CDR | Not routed; clean-room host is contract-only and AMI numerical parity is unverified | Not exposed as a native backend |
| Traits GUI | Default Python path | Explicit P0 candidate snapshot only; it is not a general GUI-native mode | Not routed | Not routed | Python-only; native P0 selection is rejected before optimization |
| CLI | Python/reference and explicit candidate commands remain available | Explicit candidate/strict tier only under its profile gate | Explicit Python-hosted hybrid path | Not routed | No Rust-host optimizer route |
| SIPI platform adapter | Strict process adapters only; no engine-internal auto/compare nesting | S2P external-admission handoff only for its fixed accepted fixture | Not a SIPI AMI host | Clean-room `sipi-ami` Init/GetWave/Close lifecycle exists, but no PyBERT production route or parity claim | Not applicable |

## Required Behavior

- A surface must reject an unsupported requested backend; it must not silently
  substitute Python, native, or either AMI host.
- The Python AMI host remains the retained reference. The Rust AMI host is not
  a fallback and must be selected explicitly only after its M5B-04 process
  route and lifecycle contract are accepted.
- Model-returned GetWave clocks remain external-clock input to the existing
  native receiver; no second CDR/clock recovery is introduced.
- Native GUI and optimizer parity are unverified. This matrix does not certify
  AMI waveform, BER, eye, optimizer, GUI, Linux, or macOS behavior.

## Evidence

- `pybert_web.engine_adapter.create_backend_registry` keeps `python`, strict
  `rust`, `hybrid-ami`, `agent-spice-rfm`, `auto`, and `compare` distinct.
- `pybert.gui.handler.MyHandler._on_optimize` rejects every non-`python` GUI
  engine before starting the optimizer.
- `native/crates/sipi-ami` owns the clean-room Init/GetWave/Close ABI lifecycle;
  M5A acceptance recorded its contract scope without an AMI parity claim.

M5B-05 is accepted only as an explicit support/unsupported gate. It does not
close M5B-01 reliability work, the M5B-03 RFM baseline blocker, M5B-04 AMI
process routing, license review, or history import.
