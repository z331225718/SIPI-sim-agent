# AS-04 `tune-yparam-tran` direct-port audit

The direct port is bound to Agent-Spice MIT commit
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` and tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402` without copying upstream source.

Reachable upstream entry paths are `src/agent_spice/cli.py`,
`src/agent_spice/sparam/y_tran_tuning.py`, `rfm.py`, `artifacts.py`, and the
HSPICE backend/result paths. The authority depends on NumPy, SciPy optimize,
and scikit-rf plus a caller-owned HSPICE executable; the Rust leaf keeps the
optimizer/runtime boundary explicit.

The portable leaf validates strictly increasing residual poles and band
boundaries, groups response entries for arbitrary bounded n-port models,
requires one exact RFM token in the deck, mutates only declared real-pole
residues, applies static S RMS and spectral-norm gates, renders bounded trial
decks, and runs a real bounded Nelder-Mead simplex (reflection, expansion,
contraction, and shrink). Each objective evaluation invokes the
caller-selected HSPICE executable and parses the requested listing measure;
the selected RFM is written only after a real external trial succeeds.
Missing HSPICE, missing measures, duplicate tokens, and failed trials remain
fail-closed. Actual external execution is additionally fail-closed before
path lookup: this leaf does not execute a caller path until executable custody
is implemented and attested.

The direct leaf does not claim commercial HSPICE runtime identity or
transient numerical parity. The v1 records are unbound preparation
observations and do not bind either temporary tree or source identity. No fake
executable is executed; an additive v2 is reserved for after the preparation
commit.
