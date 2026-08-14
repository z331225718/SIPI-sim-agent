# P3C ADS Pre-to-Final Spectrum Grid Observation v1

## Scope

This external-only observation is authorized to temporarily read the numerical
payload layout of the existing `CMP1_S0` and `CMP1_FFT_IMP` structured ADS
dataset surfaces from the unchanged P3C fixed-pulse bench.  It has one
fail-closed question: whether every matching four-port member has the exact
same finite, strictly increasing frequency axis.

The authoritative, hash-bound ADS help identifies `CMP1_S0` as the spectrum
after causality and before passivity correction, and `CMP1_FFT_IMP` as the FFT
of the final impulse response used in convolution.  This does not establish
that their difference is solely a passivity correction: other undocumented
transformations must remain possible unless separately evidenced.

## Exact Rules

- The P3C-04aw netlist changes by zero tokens.  It retains the exact selected
  S4P, PWL pulse, `ImpSaveSpectrum=yes`, and transient controller.
- The observer requires exactly 16 `CMP1_S0(row;column)` and 16
  `CMP1_FFT_IMP(row;column)` members for rows and columns 1 through 4.
- Every surface member must expose exactly one real `freq` independent variable
  and one complex `freqResp` dependent variable.  Axis points must be finite
  and strictly increasing.
- All members inside each named surface must have bit-identical axes.  The
  named surfaces must then have bit-identical point counts and axis values.
- No interpolation, resampling, nearest-bin matching, window, taper, complex
  value adjustment, or product policy change is permitted.
- On mismatch, the only result is a hash-only grid-mismatch observation.  It
  retains summaries and canonical axis digests, never spectrum values or paths.

## Boundary

This is neither an ADS passivity on/off experiment nor a product-spectrum or
waveform execution.  It does not quantify a correction, identify a waveform
mismatch cause, port ADS behavior, or change candidate, receiver, P4B, P5, or
release gates.
