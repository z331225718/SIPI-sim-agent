# P3B-05a Causal-FIR Request Rejection Surface Gate

P3B-05a requires `sipi.link.causal-fir-request.v1` to fail closed on
seed, PRBS, noise, jitter, DFE/CDR/BER, and non-bypass stages. This
audit records the mechanical gate that freezes that rejection surface
in `sipi-contracts`; the real deterministic seed, noise/jitter profile,
and receiver-stage semantics remain pending owner decisions (P3B-05).

## Delivered Gate

- `tools/verify_p3b_05a_causal_fir_request_rejection.py` — verifier for
  schema `sipi.p3b-05a.causal-fir-request-rejection.v1`. It fails closed
  if: the schema id constant stops naming `sipi.link.causal-fir-request.v1`;
  any of the three stage enums (`WireTxStageV1`, `WireCtleStageV1`,
  `WireFfeStageV1`) gains a variant outside {DirectLaunch, Bypass}; any of
  the 8 wire types loses `deny_unknown_fields`; or a forbidden feature
  token (seed, prbs, noise, jitter, dfe, cdr, ber, training, equalizer,
  ctle_taps, ffe_taps) appears as a request field.
- `tools/test_verify_p3b_05a_causal_fir_request_rejection.py` — 7 tests:
  live validity, schema id, stage-enum variant sets, deny_unknown_fields
  on all wire types, forbidden-field absence, and negative probes for
  variant and seed-field addition.

## Verification

`python -B tools/verify_p3b_05a_causal_fir_request_rejection.py` returned
`{"stage_variants": 2, "schema": "sipi.p3b-05a.causal-fir-request-rejection.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p3b_05a_causal_fir_request_rejection`
passed 7/7. All 8 wire types were independently probed to carry
`deny_unknown_fields` within their attribute window.

## Artifact Hashes (SHA-256)

- verifier: `7B67ED0D5C37E1724F20012A40E31B38E5A14D8D846B429F2295AA19C60B7413`
- tests: `89B5B48740EEA67750F65BFE5D280A7746B0FAF60977A0AB44AE378949E8DDC0`

## Scope and Non-Claims

- This gate records the rejection surface only. It does not implement
  deterministic seed, noise/jitter injection, or receiver-stage semantics;
  those remain owner-blocked (P3B-05: required profile, injection
  location, units, random/time-warp model, seed replay, observables, and
  tolerance decisions).
- The gate does not certify link simulation, CDR lock, BER, or release
  readiness, and it does not change the fixed receiver ledger status
  (library-only / profile-blocked).
