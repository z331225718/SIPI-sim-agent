# P3A Matched S2P CLI Current-Evidence Rebinding v6

The bounded RC/PWL route changed the channel CLI product inputs without
changing the selected matched-S21 comparison contract, external source object,
or frozen tolerances. This additive v6 observation rebuilt `sipi channel run`
from clean archive `fa79434f2b7cea7726125a5efd97a435222a647f` with a locked,
offline release build.

The immutable external `channel_16ghz_3db.s2p` Git object was independently
materialized twice in fresh temporary custody. Both standard-DFT observations
and the bounded CLI comparison passed the pre-existing absolute and relative
tolerances. The hash-only external report is
`3ac235f05bf51557d69375e655a7a3f09f873b03ee75f021de303f3c689b9822`;
the S2P bytes, kernel samples, executable bytes, report bytes, and absolute
paths remain outside the repository.

v1 through v5 remain historical. v5 must reject with the exact
`evidence_product_source_drift` token. v6 restores only the selected
matched-S21 periodic-kernel observed evidence for the current candidate. It
does not attest ordinary caller input, general Touchstone/reflection behavior,
Link/eye/BER, artifacts, external profile acceptance, legal clearance, or
release readiness.
