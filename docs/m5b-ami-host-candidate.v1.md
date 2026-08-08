# M5B-04 Rust AMI Host Candidate Transport

Status: Windows-only candidate transport. It is not in `engine.lock`, is not
discoverable by a production resolver, and has no default, fallback, GUI,
optimizer, PyBERT, cross-platform, or AMI numerical-parity claim.

## Invocation

```text
agent-spice-sim ami-host-candidate --request <request.json> --output-dir <new-directory>
```

`<new-directory>` must not exist. The command writes all sidecars and
`result.json` to a sibling staging directory, then atomically renames that
directory only after `AMI_Init`, optional `AMI_GetWave`, and `AMI_Close` all
succeed. A nonzero exit leaves no consumable output directory.

## Request Contract

The request schema is `agent-spice.ami-host-request.v1`. Unknown fields are
rejected. It contains:

- `mode`: `init` or `init-get-wave`.
- Explicit, request-relative `model.ibis`, `model.ami`, and `model.dll` file
  identities: `path`, `sha256`, and `byteLength`.
- Pinned parsed host metadata: `amiVersion`, `initReturnsImpulse`, and
  `getWaveExists`.
- Raw `sampleIntervalSeconds`, `bitTimeSeconds`, and `amiParametersIn`.
- `initImpulse`, plus `getWave.waveform` and `getWave.clockCapacity` when the
  mode requires GetWave. Each numeric input is an exact `f64le` little-endian
  sidecar with `path`, `sha256`, `elementCount`, and `byteLength`.

The candidate uses the existing clean-room `sipi-ami` `AmiDll` and `AmiModel`
for the sole Init/GetWave/Close ABI path. It passes the primary column only
and records `primaryColumn: 0`; v1 does not accept multi-column, resampling,
equalization, clock recovery, unit conversion, or sign-conversion controls.

## Result Contract

`result.json` uses `agent-spice.ami-host-result.v1` and records the SHA-256 of
the exact request manifest, candidate build/executable identity, model
identities, parsed metadata, lifecycle outcomes, and raw ABI strings. Init
impulse, GetWave waveform, and returned clock times are separate exact `f64le`
sidecars with hashes and byte lengths. No raw array crosses JSON serialization.

The transport validates schema, metadata agreement, file and sidecar hashes,
byte lengths, sidecar alignment, finite values, mode/capability agreement, and
clock capacity before or at the existing host boundary. Load, Init, GetWave,
or Close failures fail closed and do not publish a result.

## Evidence And Limits

The locked Rust integration test builds a clean-room Windows ABI stub DLL and
proves dynamic loading, Init-only and Init+GetWave transport, raw sidecars and
clocks, hash/unknown-field/non-finite rejection, and no published output when
Close fails. The tracked PyBERT `example_rx.dll` remains subject to the
separate fixture-distribution compliance blocker and is not used as candidate
runtime or parity evidence.

The candidate does not yet provide a promoted bundle or `engine.lock` entry.
A DLL hash alone does not constrain its Windows loader dependency closure; a
future candidate bundle must list and hash that closure. Process timeout,
cancellation, lock contention, and malformed/partial child-process handling
belong to the later PyBERT process adapter, where a non-cooperative vendor DLL
can be killed fail-closed at process scope.
