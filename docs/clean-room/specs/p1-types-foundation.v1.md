# P1 Types Foundation Specification v1

## Scope

This specification covers `crates/sipi-types/**` for P1-02. It defines
construction-time data validity only. It does not define arithmetic,
conversion, parsing, transform, network, file-format, or simulation behavior.

## Allowed Materials

The implementation may use this independently authored specification and the
Rust standard library. It must not consume external engines, external assets,
oracle outputs, legacy source, or a legacy data-model shape.

## Observable Behavior

Finite SI wrappers reject NaN and infinities. Port identifiers are non-empty
and contain no NUL or control character. A port list is non-empty, unique, and
preserves declaration order. Complex values have two finite components.

An axis is either a non-empty explicit sequence or a uniform start, non-zero
step, and non-zero count. Explicit axes have no monotonicity or spacing rule.
A complex tensor has a non-empty shape, every dimension is non-zero, checked
shape multiplication, and an exact value count. A waveform pairs a seconds
axis with voltage samples of the same length. A spectrum pairs a hertz axis
with raw complex bins of the same length.

## Non-Claims

This specification does not define timebase, sampling rate, axis direction,
frequency normalization, FFT, dB, transfer-function, impedance, port intent,
reference impedance, tensor layout, JSON representation, or numerical
algorithm. It does not certify any profile, domain capability, platform,
release, or strict clean-room process.
