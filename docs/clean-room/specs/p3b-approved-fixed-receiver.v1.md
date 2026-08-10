# P3B Approved Fixed Receiver v1

This is the owner-approved, product-owned behavior for the required
`channel-rfm-block-2-current-drive-v1` receiver boundary. It consumes exactly
1024 finite single-ended voltage samples at `t0=0`, `dt=1 ps`, with 8 samples
per UI. It consumes exactly 128 caller-supplied reference bits. CTLE and FFE
are identity-only.

## Acquisition and Normalization

For each phase `p` in `0..7`, sample `r[p + 8m]` for `m=0..127`. For the first
32 symbols, map bit one to `+1` and bit zero to `-1`; both classes are
required. Compute `center=(mean_one+mean_zero)/2` and
`amplitude=(mean_one-mean_zero)/2`. Reject `abs(amplitude) < 1e-6 V`.
Score a phase by `abs(mean_one-mean_zero)`. The best score must be nonzero,
unique, and at least 1 percent above the second best score. The selected phase
is locked for the complete run; tracking is not supported. Normalize every
selected sample as `u=(r-center)/amplitude`.

## Fixed-Training DFE

The receiver has five postcursor taps at delays 1 through 5 UI. All weights
start at zero. During the first 32 symbols, use reference symbols for feedback,
with indices below zero equal to zero:

```text
z = u - sum(w[i] * s[m-i])
e = s[m] - z
w[i] = w[i] - 0.25 * e * s[m-i]
```

After training, coefficients are frozen. For measurement symbols 32 through
127, feedback uses the known training reference for indices below 32 and prior
hard decisions for indices at or above 32. `z > 0` decides `+1`; `z < 0`
decides `-1`; `z == 0` is an erasure and an error.

## BER and Outputs

BER covers only the 96 measurement symbols. The result records phase, lock,
center, amplitude, frozen taps, 96 decisions, error count, denominator 96, and
the derived BER. Phase, lock, decisions, error count, and BER are discrete
observables and compare exactly. A continuous observable may compare only when
the oracle exposes the same stage, using `1e-9 V + 1e-6 relative`.

The product never reads RFM, Python, external engine, port, current, or oracle
configuration inputs. An external comparator must establish matching receive
waveform and reference-bit hashes. Without an authorized reference-bit source,
external required-profile acceptance remains blocked.
