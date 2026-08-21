# P3 ADS Retained-Workspace Dependency Closure

## Scope

This slice hashes the retained ADS workspace artifacts and verifies the
configuration fields that are actually observable from the retained netlist.
It is a dependency-closure and missing-field audit, not an ADS runtime replay
or product admission.

The retained workspace contains `workspace.ads`, `netlist.log`,
`EyeProbeSummary.xls`, and four dataset artifacts (`original.ds`,
`nojitter.ds`, `txonly.ds`, `rxonly.ds`). Their exact hashes and byte lengths
are recorded in the companion v1 evidence file.

## Observed configuration

The retained netlist declares a 32 Gb/s statistical channel with 32 samples/UI
and `ami_jitter_enable=1`, but the retained TX/RX RJ, DJ, DCD and noise fields
(`Tx_Sj`, `Tx_Sj_Frequency`, `Rx_Sj`, `Rx_DCD`, `Rx_Noise`) are all explicitly
zero. The eye probe explicitly disables `Save_JitterRMS`,
`Save_JitterPP`, `Save_Bathtub`, and `Save_Waveform`; only contour output is
enabled. Receiver capture delay/count/mode are present, but no CDR acquisition,
clock source, lock, reset, or cancel semantics are declared.

Adaptive AMI controls (`adapt_mode`, `gain`, `lfeq`, and `peak`) appear in the
configuration, but there is no product equalizer stage contract or accepted
profile identity. Configuration strings therefore cannot be treated as product
semantics.

## Result

The highest-value legal slice is the exact dependency closure and missing-field
inventory. No jitter observable/reference/tolerance, eye folding/bin rule, CDR
lock contract, equalizer profile, or canonical external runtime identity can be
derived without inventing semantics. The retained `.ds` and `.xls` files are
checked only by byte length and SHA-256; their payloads are not parsed and no
result is inferred from them. They remain external-only and are not product
input.

The verifier is
`tools/verify_p3_ads_retained_workspace_jitter_closure_observation.py`.
It supports document-only validation by default and explicit external custody
verification with `--workspace-root`.
