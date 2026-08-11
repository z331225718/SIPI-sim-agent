# P3A Matched Channel CLI Run Audit

`sipi channel run --stdin` is a bounded product route for the exact inline
`# Hz S RI R 50.0` two-port subset. It calls only the strict Touchstone parser,
matched-spectrum admission, and the existing `S21` periodic-kernel resolver.

The request rejects files, URLs, base64, asset/profile identities, alternate
Touchstone forms, non-uniform grids, endpoint residues, termination settings,
and FFT overrides. The route has no artifact publication or external process.
Its output is limited to 201 one-sided samples and at most 400 V/V kernel
values, and always labels caller input as unattested rather than as an accepted
external profile.

Verification: `cargo test --workspace --all-targets`, `cargo clippy --workspace
--all-targets -- -D warnings`, `verify_clean_room_register.py`, and
`verify_product_boundary.py` pass. The read-only Orca review found one P2
protocol inconsistency: `sipi channel run` without `--stdin` fell through to a
generic usage error. The route now rejects that incomplete command shape with
the same structured `unsupported` response and exit code as its peer routes;
the process test covers the regression. The review's remaining observations
were P3-level and align with existing CLI conventions.

This audit does not claim Link simulation, causal-FIR conversion, external
profile parity, general S-parameter support, or release readiness.
