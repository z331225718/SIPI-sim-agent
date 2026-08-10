# P3B-03a Receiver Candidate Readiness

Commits `3ecd626` and `0d21320` add an oracle-side, fail-closed readiness
preflight for the unselected `channel-rfm-block-2-current-drive-v1` candidate.
It binds the external Git-object RFM identity and the previously observed
Windows current-drive boundary: locked engine hash, ports 1 to 2, 1024 samples,
`dt = 1e-12 s`, samples-per-UI 8, and current-to-voltage sign `-1`.

The preflight deliberately keeps `required_by: null` and requires the
inventory profile to remain `oracle_only/candidate`. It enumerates eight
unresolved owner decisions before any receiver API can exist: product causal
waveform, P3A causalization, CTLE, FFE, DFE, CDR, BER, and external reference
scope. Each must remain `missing_owner_selection`.

The verifier now requires all RFM receiver evidence references to use the
exact existing Markdown anchor for the Git-object same-config receiver parity
section, checks that the document file exists, and verifies that its heading
fragment resolves. This prevents the former ambiguous/invalid evidence link
from silently passing.

Verification: readiness tests 5/5, acceptance-profile tests 4/4, the
readiness verifier, and all four P0 verifiers passed. No Rust receiver crate,
DFE/CDR/CTLE/FFE/BER API, product CLI route, oracle execution, legacy adapter,
or numerical algorithm was added.

OpenCode initial audit `msg_e5cc6b33156c` found one P2 evidence-anchor gap.
The fix was reviewed by `msg_e6a1c6adc383`: **0 P1 / 0 P2**.

## Non-Claims

This is candidate admission evidence only. It is not a required-profile
decision, receiver implementation, RFM Link parity result, causalization
policy, or production capability.
