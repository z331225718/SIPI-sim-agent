# P4B AMI Standard ABI Host v1

## Scope

This product-owned specification defines Windows x64 mechanics for an explicitly
selected dynamic library. It is not AMI parameter validation, IBIS binding,
vendor-model behavior, or a default runtime route.

The host accepts only an absolute caller-supplied DLL path, a caller-supplied
SHA-256 identity, and an exact `AmiTextBindingV1` revalidated under caller
supplied parse limits. It rejects platform, PE-machine, hash, loader, and
required-export failures without searching PATH or applying a fallback.

## ABI Boundary

The external functions use the C ABI on Windows x64. `long` is represented as
the four-byte Windows C `long`, and a successful lifecycle status is exactly
`1`; every other status fails closed. The required exports are `AMI_Init` and
`AMI_Close`; `AMI_GetWave` is optional and cannot be called when absent.

`AMI_Init` receives a mutable f64 matrix, row/aggressor counts, sample interval,
bit time, exact parameter bytes, and opaque output/handle/message pointers.
`AMI_GetWave` receives a caller-owned mutable waveform buffer, its length,
caller-owned clock buffer, opaque parameter output, and the opaque handle.
`AMI_Close` receives that opaque handle. This slice neither dereferences nor
assigns ownership to the parameter/message outputs.

The safe boundary validates finite values, bounded `long` conversions, matrix
shape, nonempty bounded waveform buffers, and a nonzero clock capacity. Clock
storage begins with `-1.0` sentinels; results end at the first sentinel and
reject non-finite or negative pre-sentinel values.

After a successful Init, every host error path attempts exactly one Close. An
explicit Close consumes the active lifecycle; Drop only performs best-effort
cleanup. Cancellation, timeout isolation, dependency closure, artifact output,
and real vendor interoperability are explicitly out of scope.

## Nonclaims

This slice does not claim AMI semantic validity, IBIS+AMI composition, numeric
parity, DLL security, Linux/macOS support, or any CLI/default routing.
