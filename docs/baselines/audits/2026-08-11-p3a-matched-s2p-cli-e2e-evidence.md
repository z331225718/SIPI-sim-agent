# P3A Matched-S2P CLI E2E Evidence

The external-only `channel_16ghz_3db` Git object was materialized in two fresh
temporary custodies. A standard-DFT observer produced identical 400-sample
kernel identities. A clean archive of product commit `ef79aedbf993d5ea4c2d087cd454e98db3799f8a`
was built with `cargo --locked`; its `sipi.exe` received the exact text through
`sipi channel run --stdin`.

The process returned exit 0, one strict JSON stdout line, and empty stderr.
The response preserved the external input SHA-256 and the fixed
201/100 MHz/50 ohm/400/25 ps metadata, retained the runtime
`caller_input_unattested` label, and passed every kernel sample under the
frozen tolerance. The hash-only evidence and verifier retain no S2P text,
kernel array, path, or external runtime output.

This evidence is limited to the selected input through the bounded CLI path.
It does not claim general Touchstone, reflection, termination, Link, eye/BER,
artifact, or release behavior.

One read-only Orca review checked the staged comparator, verifier, evidence,
and runtime claim boundary. It reported no P1 or P2 findings.
