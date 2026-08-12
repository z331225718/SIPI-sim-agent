# P3C Fixed-Pole Rational Identification Core v1

## Purpose

This product-owned core is the first numerical step on the selected scalar
`Hdiff` rational route. It identifies residues for a finite, fixed pole basis.
It is intentionally not a relocating vector-fitting implementation and cannot
produce a state-space model or waveform.

## Exact Algorithm

The input is only `SelectedP3cStaticDifferentialTransferV1` in product-owned
memory. It must have at least 32 points, begin at DC, and end at 40 GHz. The
normalized continuous variable is `s = j*f/40 GHz`. For each allowlisted order
8, 12, and 16, the basis uses conjugate poles logarithmically spanning 10 MHz
to 40 GHz with real part `-0.05*abs(imaginary part)`.

The core fits `H(s) = sum(r_k/(s-p_k))` only: direct, proportional, and delay
terms do not exist. It applies inverse-reference-magnitude weights with a
`1e-15` floor, rejects a thin-SVD relative rank at or below `1e-12`, then uses
single-threaded `faer 0.24.4` column-pivoted QR to identify residues. Poles are
never relocated, reflected, stabilized, or repaired. The first order passing
all three gates is selected: relative complex RMS at most 0.5%, peak absolute
error normalized by the reference peak at most 3%, and DC relative error at
most 0.5%.

## Boundary

The implementation accepts no file, artifact, path, ADS grid, ADS waveform,
caller options, or coefficient output. Its model is a product-owned in-memory
fit only. It does not settle out-of-band continuation, source interpolation
between OSR32 strobes, initial state, strobe ownership, recurrence, or any
receiver/reference/release question.
