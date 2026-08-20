# P3B-03g Receiver Diagnostic Route Contract Gate

P3B-03g wires a strict caller-supplied `sipi link receiver run --stdin`
diagnostic artifact route. This audit records the mechanical gate that
keeps the route a product-owned diagnostic: result and provenance must
stay `policy_selected_not_locked`, external RFM false, acceptance false,
with the fixed profile id and the data-aided delegated-ambiguity algorithm.
It does not change the CDR phase-acquisition semantics that remain
owner-blocked for P3B-03/04/05 completion.

## Delivered Gate

- `tools/verify_p3b_03g_receiver_diagnostic_contract.py` — verifier for
  schema `sipi.p3b-03g.receiver-diagnostic-contract.v1`. It fails closed
  if: the `link.receiver.run` route or its handler disappears from the
  CLI; any of the 5 markers (`product_owned_diagnostic`,
  `policy_selected_not_locked`, `external_rfm\\":false`,
  `acceptance\\":false`, `data_aided_fixed_training_receiver_delegated_ambiguity_v2`)
  is missing from the CLI emission; any of the 4 diagnostic schemas loses
  its binding; the fixed profile id disappears; or the result claims a
  non-`policy_selected_not_locked` clock policy, `external_rfm:true`, or
  `acceptance:true`.
- `tools/test_verify_p3b_03g_receiver_diagnostic_contract.py` — 6 tests:
  live validity, route wiring, marker presence against real CLI source,
  schema binding, profile binding, and no-promotion assertions.

## Verification

`python -B tools/verify_p3b_03g_receiver_diagnostic_contract.py` returned
`{"markers": 5, "schema": "sipi.p3b-03g.receiver-diagnostic-contract.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p3b_03g_receiver_diagnostic_contract`
passed 6/6.

## Artifact Hashes (SHA-256)

- verifier: `B4D1D7AF2702AAE974C4F3E21711AFDB6CEC24C56992A56F3233DE43A433254C`
- tests: `A5DEC0E131B67AD0A0DE089C9C61E5E5FBE50C52D3DFA25F8F6D52B703A4F69B`

## Scope and Non-Claims

- This gate records the diagnostic route contract only. It is not a CDR
  lock, RFM receiver parity, required-profile acceptance, or release
  claim. P3B-03/04/05 completion still requires the owner amendment of
  phase-acquisition semantics (currently `blocked_cdr_ambiguous_under_
  approved_charter` per P3B-04).
- The route remains caller-supplied diagnostic only, with the result
  always marked `policy_selected_not_locked` and non-acceptance.
