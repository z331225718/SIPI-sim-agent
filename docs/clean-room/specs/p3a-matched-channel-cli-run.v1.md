# P3A Matched Channel CLI Run v1

`sipi channel run --stdin` accepts one JSON request with schema
`sipi.channel.matched-two-port-kernel-run-request.v1`. Its only source is an
inline UTF-8 text field. The text is subsequently subject to the strict ASCII
Touchstone subset defined by `p3a-touchstone-two-port-parser.v1`; paths, URLs,
base64, asset identifiers, profile identities, termination settings, and FFT
settings are not accepted.

The command executes exactly this chain once:

```text
strict Touchstone parser -> matched two-port admission -> matched S21 kernel resolver
```

The product limits source text to the existing one MiB stdin request limit,
physical lines to 65,536 bytes, and one-sided samples to 201. The returned
kernel therefore contains at most 400 V/V gain samples. No artifact is
created, and no external source, Python process, filesystem path, or oracle is
used.

The response contains only the caller source byte length and SHA-256, admitted
grid metadata, sample interval, bounded V/V gain array, and the fixed scope
`matched_s21_periodic_kernel_only`. Its acceptance state is always
`caller_input_unattested`: it does not assert that the caller text is any
external selected profile.

This route is not full Touchstone support, a general S-parameter solver, a
reflection or termination solver, a causal-FIR conversion, a Link simulation,
or eye/BER/DFE/receiver support. It does not interpolate, pad, window, trim,
fit, renormalize, de-embed, repair passivity or causality, or invoke an
external comparator.
