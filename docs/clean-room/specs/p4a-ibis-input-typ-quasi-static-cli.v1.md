# P4A Input/TYP Quasi-static CLI v1

## Scope

`sipi ibis quasi-static-evaluate --stdin` accepts caller-provided UTF-8 IBIS
text, one explicit Input/Typical model selection, two static clamp drives, and
one explicit `SIG-REF` voltage slope in volts per second.

The route runs the bounded structural parser, typed semantic envelope, selected
Input/Typical decoder, and existing quasi-static constitutive evaluator. It
reports signed GND clamp, POWER clamp, `C_comp`, and total shunt current.

## Required Behavior

- `C_comp` current is `C_comp * d(SIG-REF)/dt`.
- The two I-V clamp drives remain independent and use existing in-domain linear
  interpolation with no extrapolation.
- Every source, selection, probe, slope, parse, profile, and constitutive error
  rejects the request without returning a partial evaluation.

## Exclusions

No time step, waveform, history, state, integration, supply inference, PVT
fallback, V-T/ramp/package/pin handling, differential R-C composition, channel,
AMI, artifact, file, URL, asset identity, or external acceptance behavior is in
scope. Caller-provided text is not an attested external profile.
