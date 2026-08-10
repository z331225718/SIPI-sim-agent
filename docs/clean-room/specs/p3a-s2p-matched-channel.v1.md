# P3A S2P Matched Channel Specification v1

## Scope

This independently authored product contract defines only
`sipi.channel.s2p-matched.v1`, the future clean-room Rust input/output behavior
for one matched two-port S-parameter path. It does not define Touchstone file
ingestion, a legacy DTO, a Python bridge, or a CLI route.

The implementation may use this specification and applicable public
Touchstone/scattering-wave standards. The selected `channel_16ghz_3db.s2p`
asset, its source repository, external engines, and all observer reports are
comparator-only materials and must not enter product source or tests.

## Electrical Convention

- Exactly two single-ended ports are ordered `1 = source`, `2 = receiver`.
  Port current is positive into the network; each port voltage is relative to
  the shared reference.
- The data are complex S parameters under a real-reference power-wave
  convention: `a = (V + Z0 I) / (2 sqrt(Z0))`,
  `b = (V - Z0 I) / (2 sqrt(Z0))`, and `b = S a`.
- Both ports, source, and load use the same finite positive real scalar `Z0`.
  The launched voltage is the source-port voltage after matched-source
  division. Under this exact matched condition, the positive receiver transfer
  is `Vreceiver / Vlaunch = S21`.
- Only the `S21` forward path produces the output. `S11`, `S12`, and `S22`
  may be structurally present but do not enable reflections or crosstalk.

## Spectrum and Impulse Contract

The input is a finite `2 x 2` complex S matrix at a strictly increasing,
uniform, one-sided frequency grid in Hz. It includes DC and its final bin is
Nyquist. The product fixes `N = 2 * (positive_bin_count - 1)`,
`dt = 1 / (N * df)`, and rejects incompatible values.

The completed spectrum is Hermitian:
`H[N-k] = conj(H[k])` for the positive interior bins. DC and Nyquist imaginary
residue must be within the separately declared numerical tolerance. The inverse
transform is `h[n] = (1/N) sum(H[k] exp(+j 2 pi k n / N))`; the corresponding
forward sign is negative. No window, time shift, causal repair, zero padding,
interpolation, extrapolation, fitting, normalization, or unit conversion is
implicit.

## Explicit Rejections

Reject non-S data, anything other than two single-ended ports, differential or
mixed mode, complex/unequal reference impedance, nonmatched source/load,
missing DC, nonuniform/reordered grids, renormalization, de-embedding,
reflections, multiport/crosstalk, legacy schemas, and Python/auto fallback.
IBIS, AMI, COM, network fitting, and Link receiver behavior are outside this
contract.

## Acceptance Boundary

The selected external profile first requires a structural preflight with pinned
source object, port order, real `Z0`, grid, and FFT identity. Numerical
comparison remains blocked until a separate observer-side stimulus, launch
definition, external resolver identity, output alignment, and tolerance policy
are frozen. Passing structural preflight is not S2P parsing, impulse, Link, or
general channel parity.
