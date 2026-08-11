# P7-04a Same-Host Isolated Install Admission

P7-04a is deliberately narrower than the PLAN's fresh-machine requirement. It
re-admits a P7-03a archive, streams the accepted product bytes into a new
external prefix, and invokes the prefix-local executable with a minimal loader
environment.

Its output must say `fresh_machine: false`, `fresh_user: not_assessed`, and
`promotion_status: blocked`. A fresh VM or machine remains required to close
P7-04.

## Observed Chain

On commit `b19306dccf9abfa153e3951254a5d39f303e6991` (tree
`6281afc62dbea1082ea1e86e43eae97eca2339bc`), P7-01a produced two identical
Windows x86_64 builds. The executable identity was
`cf36303e8997124c8bc1f9d53ea410eb09a6b17431453ef1dd2fb0cca73adfd8` at
691712 bytes. The P7-02a composition report, P7-03a archive report, and
P7-04a isolated-install report had SHA-256 identities
`62a52fc9b14269eeeff13a0321f9cabae27cea914ed0130f39ebde6c08d4a966`,
`72c03d8b595fd9f4de45c37038e416d6282edc061e88a780d661962e2e96e854`, and
`9a0ea5e40a667cdb2eddbe77e407ba90820be8c46baac51acd6fe97a45dac309`.

The isolated prefix directly ran version/capabilities/protocol discovery, a
product-owned TRAN artifact plus report inspection, and the recognized
unavailable Channel rejection. Observe mode passed. The default release-gate
mode intentionally returned exit code 2 after recording the same blocked
result.
