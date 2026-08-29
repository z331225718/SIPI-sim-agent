# COM FD final-metric source map

Scope: the additive `sipi-com::fd_metrics_v1` library leaf.  This leaf is a
mechanical Rust port of the pinned Agent-COM R4.80 frequency-domain report
functions.  It consumes caller-supplied frequency axes and complex SDD21
traces and publishes the source insertion-loss and raw SDD21 ICN values.  It
does not read touchstone files, perform mixed-mode conversion, make package
selections, or resolve a channel.

The four-term regression is the source `get_ILN`/`fit_insertion_loss` report
metric.  It is not a rational/vector fit or any other S-parameter channel
model fit.  The only channel conversion in this crate remains the existing
FD-to-TD direct interpolation/IFFT leaf.

| Upstream Git path | Ported role | Git blob | Bytes | Raw SHA-256 | License |
| --- | --- | --- | ---: | --- | --- |
| `src/agent_com/metrics/fd.py` | `fit_insertion_loss`, `power_weight_function`, `fd_loss_metrics`, `icn_rms`, `r480_fd_icn_metrics` | `1dd6696ce8580c6ecb534b1d227fbe6c3bfe3660` | 7938 | `201aa0b543c612644ae4b2ddf16fdc5149419266fee64d07ab7c4d89bc3ea578` | MIT |
| `src/agent_com/_orchestration.py` | call-site metric names, controls, signs, and source role dispatch | `5d260a0aab941f1a1955fe3abef36d85a56034c0` | 90877 | `069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69` | MIT |
| `LICENSE` | upstream license text | `55aac2e4f8c36a978d315efb02815972579b8293` | 1067 | `d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2` | MIT |

All rows are fixed to upstream commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`.  There is no upstream
`metrics/fd_icn.py` at this commit; the ICN implementation is in `metrics/fd.py`.

## Port notes

- Frequency integration uses the source `searchsorted` boundaries: the lower
  endpoint is the last point at or below `f1`, and the upper endpoint is the
  first point at or above `f2`, both clamped to the source axis.
- `delta_f` deliberately uses source indices 10 and 9 for axes with at least
  eleven points, otherwise indices 1 and 0.
- `FOM_ILD` uses the locally refit residual `ild_db`, while the public fitted
  trace retains the source's log-magnitude sign.  `fitted_IL_dB_at_Fnq`
  interpolates the negated fitted trace exactly as the orchestration call site.
- ICN combines each role's `(|SDD21| * amplitude)^2` in power.  FEXT and NEXT
  reports are separate square-root integrations; no complex-voltage summation
  is introduced.
- The four-term normal solve and polynomial evaluation retain the source's
  raw Hz basis `[mag, sqrt(f)*mag, f*mag, f^2*mag]`; no conditioning scale or
  alternate basis is introduced.  The Rust elimination follows the source's
  dense real solve contract and fails closed on non-finite or zero pivots.

Focused unit vectors were generated from the pinned Python function and cover
fit signs, power weights, interpolation, ICN role separation, boundary
indices, and fail-closed malformed inputs.  The `tp0v_thru_source_canary`
vector reproduces the pinned synthetic TP0V THRU law and its
`9.8349128449511856 dB` fitted IL at Fnq.  These are deterministic source
cross-checks, not a claim of full original-13 matrix parity.
