# P3A-14 Matched S2P CLI Current-Evidence Rebinding v4

P3A-14 replays the selected external-only
`channel_16ghz_3db.s2p` profile against product commit
`63405500408266e2e664ec405701ada9e33d8afa`. This is an evidence rebinding
only: it does not change the parser, resolver, CLI semantics, accepted scope,
or capability state.

The oracle-only comparator used a clean Git archive of that product commit,
an isolated release target with `--locked` and offline Cargo resolution, and
two fresh temporary materializations of the exact external Git object. The
external report is retained outside this repository; its SHA-256 is
`f229b0d1e7958b1278747ff33a009c80f2dba5822909ea64f570b438f8a9196c`.
It records the exact S2P source identity, product executable identity, two-run
observer identity, and aggregate tolerance metrics without retaining source
bytes or kernel samples.

Both observer runs had the same kernel hash. The bounded `sipi channel run`
result passed the frozen pointwise gate with maximum absolute error
`9.792141327392284e-15` and normalized error ratio
`7.789698985496182e-6`. The v4 verifier binds the report and the five current
product crate trees plus `Cargo.lock`; v1, v2, and v3 remain historical
source-drift records. The acceptance remains only the selected matched-S21
periodic V/V kernel: ordinary caller input is unattested, and this is not
general Touchstone, reflection, Link/eye/BER, artifact, or release evidence.
