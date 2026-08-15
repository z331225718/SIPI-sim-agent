# P4A Sealed Input/TYP Quasi-static Artifact CLI v1

## Scope

`sipi ibis quasi-static-evaluate-artifact --stdin --artifact-root <root>`
consumes exactly one previously sealed `model.ibs` artifact. The request binds
only its artifact ID and manifest SHA-256 plus an explicit Input/Typical model
selection, two clamp drives, and one `SIG-REF` voltage slope.

The route verifies the exact artifact inventory and payload identity before
decoding the UTF-8 model with the existing bounded Input/Typical quasi-static
constitutive evaluator. It reports the verified payload identity and signed
GND clamp, POWER clamp, `C_comp`, and total shunt currents.

## Required Behavior

- The artifact has exactly one regular payload named `model.ibs`, at most 1 MiB.
- The sealed manifest is at most 64 KiB and must match the request identity.
- The artifact root is an explicit CLI option, never request data.
- `C_comp` current remains `C_comp * d(SIG-REF)/dt`; clamp interpolation remains
  in-domain only with no extrapolation.
- Any custody, UTF-8, parse, selection, probe, slope, or evaluator error
  rejects without a partial response.

## Exclusions

The root uses the existing app-owned, no-hostile-concurrent-writer custody
assumption. This is caller asset identity verification only, not external
profile acceptance. No inline IBIS text, path, URL, payload-hash override,
corner fallback, time integration, state, waveform, package/pin/PVT/V-T/ramp,
channel, AMI, or transient-parity behavior is in scope.
