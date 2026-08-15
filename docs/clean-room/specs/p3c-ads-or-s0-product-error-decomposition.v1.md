# P3C Same-Axis Complex Error Decomposition v1

The diagnostic reuses only the exact, same-axis `O`, `S`, `R`, and `B` values
already authorized for the OR/S0 paired transition observation. It records
`Dpre=O-R`, `Dpost=S-B`, `E=(S-O)-(B-R)`, and the exact algebraic closure
`Dpost=Dpre+E`. It also records the fixed cross term
`2*Re(sum(Dpre*conj(E)))` and the unthresholded finite-precision closure
residual.

All vectors use the existing 1,024-node S0 axis and the frozen full finite
DTFT. The node sums are not continuous-band physical energy or root-cause
shares. The diagnostic neither names an ADS algorithm nor alters a product
policy, candidate waveform, or acceptance gate.
