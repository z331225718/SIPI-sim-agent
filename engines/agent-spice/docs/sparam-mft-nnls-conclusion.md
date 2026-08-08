# MFT-NNLS Port Conclusion

## Decision

**Do not promote or select the MFT-NNLS backend. Keep `native` unchanged as
the only production backend.**

The decisive S19 Gate B result is `FIT_FAILURE`: no tested order in
`{8, 10, 12, 14, 16}` met the full-grid RMS target of `0.001`. The best fit
was order 12 at `0.021848`, roughly 22 times the target, before passivity
enforcement. This independently prevents a promotion claim even if every
remaining RPdriver parity limitation were resolved.

## Evidence

| Boundary | Result |
| --- | --- |
| MATLAB-style one-step VF response parity | Passed on the well-conditioned fixture |
| Test16 91-port relocation collapse | Reproduced, not avoided |
| QR-NNLS scalar / 2-port S/Y one-step fixtures | Passed |
| S19 bounded full-input-grid diagnostic | `FIT_FAILURE` |
| Promotion benchmark | Not run; Gate B failure stops it |

The detailed S19 trial table and local artifact command are in
[sparam-mft-nnls-s19-gate-b.md](sparam-mft-nnls-s19-gate-b.md). The collapse
trajectory evidence is in
[sparam-mft-nnls-test16-collapse.md](sparam-mft-nnls-test16-collapse.md).

## RP-NNLS Finding

The port now includes QR-compressed homogeneous NNLS, weight-mode-1 auxiliary
sample weighting, D/E coordinates and asymptotic constraints, bandwidth and
pole-subset control, and an outer/inner perturbation loop. On S19 it can
reduce passivity excess for some orders, but it does not repair the preceding
fit-quality failure and did not reach the passivity bound in the tested gate.

There are still strict-parity limitations: local extrema selection is
band-global rather than the MATLAB per-eigenbranch local-minimum procedure;
the bounded passivity fallback is not a high-Q authoritative oracle; and S
multi-inner semantics lack an end-to-end MATLAB fixture. These limitations
mean the S19 passivity figures are diagnostic, not evidence for a production
passivity guarantee. They do not weaken the RMS failure, which is measured
directly on all 826 input samples.

## Follow-up

Any future revival should first add per-mode local-extrema fixtures and an
authoritative full-band passivity oracle, then rerun Gate B from a clean
artifact. It should not proceed to corpus promotion unless Gate B reports
`PASS` under the frozen auto-mode contract.
