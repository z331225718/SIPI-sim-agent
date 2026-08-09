# P1 Contracts Foundation Specification v1

## Scope

This specification covers `crates/sipi-contracts/**` for P1-03. It maps only
the construction-time values already defined in `sipi-types` to versioned JSON
wire structures. It contains no domain request, numerical algorithm, parser,
resolver, external asset, or profile choice.

## Allowed Materials

The implementation may use this independently authored specification, the
P1 types specification, and the declared Rust serialization dependencies. It
must not consume external engines, oracle outputs, legacy source, legacy wire
format, or a legacy fixture shape.

## Observable Behavior

The capability catalog lists all planned domains as `unsupported`. Wire
structures reject unknown fields and require `sipi.contract.v1` where a
version discriminator is present. Conversion from wire data into core values
uses the core fallible constructors, preserving their finite, port, axis,
tensor, and matching-length invariants.

The contract crate exposes a rule ledger and a deterministic serialization
profile for its fixed structs and lists. The profile is not cross-language
canonical JSON. Generated JSON Schema expresses structure only; cross-field
rules remain in the ledger and conversion path.

## Non-Claims

This specification does not define JSON files, stdin behavior, CLI exits,
artifact hashes, provenance, domain inputs, S parameters, reference impedance,
sampling, FFT, AMI, COM, TRAN, comparison tolerance, or release schema.
It does not certify a profile, platform, release, or strict clean-room process.
