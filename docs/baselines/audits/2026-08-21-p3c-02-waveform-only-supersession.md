# P3C-02 Waveform-Only Supersession

## Result

The current owner-selected `selected_highloss_exact` route has no receiver and
is waveform-only. Eye, TIE, and bathtub observables are explicitly excluded.
Consequently, P3C-02 eye folding, binning, receiver, and bathtub semantics are
not current-route requirements and need no guessed implementation.

This is an additive scope reconciliation. The generic eye, TIE, Q/BER,
bathtub, horizontal-margin, curve-fit, and statistical-contour cores remain in
the repository for generic or future receiver profiles. No historical record
is deleted or rewritten.

## Boundary

This record closes only the P3C-02 obligation on the selected waveform-only
route. It does not accept a waveform, bind an external reference, select a
receiver, generalize closed-eye handling, or promote release state. Any future
profile that requires eye or bathtub behavior needs a new owner selection and
additive contract.
