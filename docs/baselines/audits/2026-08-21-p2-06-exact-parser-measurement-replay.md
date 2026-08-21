# P2-06 exact parser and measurement replay

The previous comparison observed Agent-Spice waveform points but derived its
reference MAX value in the comparator. This additive replay removes that gap.

One first-party, strict seven-line deck was supplied byte-for-byte to both the
pinned Agent-Spice executable and the product harness. Agent-Spice parsed the
deck's `.measure TRAN vmax MAX V(out)`, evaluated it, and published the value in
`SimulationResult.measurements[0]`; the comparator did not derive the oracle
measurement from waveform samples. Both executables ran twice in fresh process
and working-directory custody, with deterministic outputs.

The engine-produced measurement and product measurement differ by
`9.963737488231927e-7 V`, inside the frozen `2e-6 V + 5e-4 relative` tolerance.
The complete external report remains outside the repository and is bound here by
SHA-256. Only source-object hashes, product hashes and scalar metrics are kept.

This supports scoped closure of the exact profile only. It does not admit OP,
AC, generic SPICE/MNA, new devices, statement reordering, or general measurement
syntax.
