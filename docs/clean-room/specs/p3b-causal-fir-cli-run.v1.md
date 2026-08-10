# P3B Causal-FIR CLI Run v1

This product-owned contract exposes one narrow Link execution path:

```text
sipi link run --stdin --artifact-root <external-root> --artifact-id <id>
```

The stdin document is `sipi.link.causal-fir-request.v1`. It contains a
`sipi.link-plan.v1` with `direct_launch`, a uniform zero-origin voltage
stimulus, a same-interval causal FIR gain vector, and bypass CTLE/FFE stages.
It also contains explicit nonzero output-sample and multiply-accumulate
limits. Unknown fields, non-bypass stages, non-finite values, interval
mismatches, and invalid limits are rejected.

The sole numerical operation is `causal-fir-convolution.v1`: deterministic
linear causal convolution with its complete tail. It neither accepts nor
derives periodic DFT kernels, Touchstone/S-parameter input, RFM/current input,
termination/reflection input, equalizer parameters, receiver stages, legacy
DTOs, or file paths.

On success the application-owned external artifact root receives an immutable
artifact containing canonical `request.json`, `received-waveform.json`, and
`provenance.json`; the success manifest is the only completion signal.
Provenance records product contract and digest identities only, never external
oracle/Python/RFM material. A duplicate artifact id, resource/numeric failure,
or publication failure produces no consumable success artifact.

This is a causal-FIR Link execution primitive. It does not claim selected S2P
Link integration, RFM receiver/DFE/CDR/BER behavior, CTLE/FFE support,
reflection/termination behavior, general Link/eye/BER parity, default routing,
or release readiness.
