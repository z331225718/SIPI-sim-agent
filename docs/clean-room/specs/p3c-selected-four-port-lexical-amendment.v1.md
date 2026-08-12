# P3C Selected Four-Port Lexical Amendment v1

## Trigger

The exact selected external S4P has the option line `# Hz S RI R 50`. The
historical v1 parser admits only the separate byte spelling `# Hz S RI R 50.0`.
Its clean-archive sealed-admission observation therefore rejected at the option
line before any static transfer, fit, or waveform operation. That rejected
observation remains historical evidence and is never reclassified as success.

## Amendment

The original v1 entry point remains frozen. A new v2 entry point accepts
exactly two already-observed ASCII option-line contents: `# Hz S RI R 50` and
`# Hz S RI R 50.0`. It compares the content after the existing comment and
edge-whitespace handling; it does not parse, rewrite, or numerically normalize
the impedance token. Spellings such as `50.00`, `50.`, `5e1`, `+50`, and `050`
remain rejects. Units, parameter, data representation, case, internal spacing,
keywords, record grammar, port map, source identity, and static reduction are
unchanged.

The sealed-admission v2 entry point has the same opaque artifact-id/manifest
surface and fixed source identity, but calls only the v2 lexical parser. It
cannot silently change v1 semantics or accept caller-selectable parser policy.

## Boundary

This is an implementation amendment, not external success. A new clean archive
must still materialize, seal, and admit the exact source in two fresh temporary
roots before external static custody can be observed. It does not invoke fit or
direct stepping, generate a candidate waveform, bind the ADS reference, or
change receiver, AMI, IBIS, DLL, product-runtime, or release gates.
