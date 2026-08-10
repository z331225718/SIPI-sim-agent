# P4A-04a IBIS Input Typical Static Profile Audit

## Scope

Reviewed commit `73ffa6d`, which selects the first required pure-IBIS profile
under the user's authorization to make the profile decisions. The profile is
external-only and identifies the official sample1 asset and selected input
model only by URL and cryptographic digests.

The declared execution scope is a single-ended `SIG/REF`, typical-corner,
static clamp-current comparison. It fixes probe order, linear interpolation,
out-of-domain rejection, and an absolute-plus-relative tolerance. It excludes
package, pin, V-T, ramp, differential, AMI, and runtime behavior.

## Result

Orca reviewer message `msg_bc5c727d7893` reported **0 P1 / 0 P2**.

The reviewer confirmed that the charter cannot promote the asset, add a
redistribution claim, or drift its terminal, stimulus, observable, or
comparison policy. The profile remains `required_pending_i_v_compare`.

## Verification

```
.venv\Scripts\python.exe -B tools\verify_p4a_ibis_input_typ_static_acceptance.py
.venv\Scripts\python.exe -B -m unittest tools.test_verify_p4a_ibis_input_typ_static_acceptance
.venv\Scripts\python.exe -B tools\verify_product_boundary.py
.venv\Scripts\python.exe -B tools\verify_clean_room_register.py
.venv\Scripts\python.exe -B tools\verify_release_license_preflight.py
.venv\Scripts\python.exe -B tools\verify_rust_candidate_source_map.py
.venv\Scripts\python.exe -B tools\verify_acceptance_profiles.py
```

All checks passed. This accepts a profile charter, not an IBIS electrical
implementation, an external oracle compare, product compatibility, or a
release capability.
