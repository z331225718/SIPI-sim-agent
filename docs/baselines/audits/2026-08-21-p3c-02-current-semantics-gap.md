# P3C-02 Current Semantics Boundary

## Result

P3C-02 remains open, but its blocker is now separated from the already
implemented product-owned strict-grid metric core. The current owner
reconciliation selects the exact selected-highloss profile with no receiver
and waveform-only scope, explicitly excluding eye, TIE, and bathtub
observables. The existing PRBS9 metric contract does contain deterministic
sampled-eye rules, but it is a caller-supplied strict-grid metric surface and
does not select a COM bathtub input, PDF/bin policy, receiver stage, external
reference, or acceptance gate.

The pinned PyBERT and Agent-COM observation records phase/bin and contour
surfaces only as source observations. They do not select SIPI semantics and
therefore cannot justify a direct implementation in this slice. No source
code was copied, no external runtime was invoked, and no alignment, gain,
polarity, fitting, or tolerance relaxation was used.

## Exact blocker

The next legal implementation requires a current owner amendment that selects
the generic COM eye folding/bin representation and bathtub input/folding,
estimator, tolerance, receiver, and reference semantics. Until that exists,
the narrow current action is a fail-closed gap record rather than a guessed
eye or bathtub API. The selected waveform-only route remains unchanged.

## Non-claims

This record is not a receiver implementation, bathtub acceptance, COM parity,
external-oracle evidence, or release evidence.
