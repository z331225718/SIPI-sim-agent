# P3B-03d2 Receiver Semantic Charter Proposal Audit

- Candidate commit: `43a5a5f` (`docs: propose receiver semantic charter`)
- Review request: `msg_d260d92eb053`
- Reviewer conclusion: `msg_45646f379adf`, 0 P1 / 0 P2

## Scope

The pending owner charter now records one profile-scoped proposal: a
data-aided eight-phase, fixed-phase NRZ receiver with 32 training UI, a
five-tap postcursor fixed-training DFE, and 96 measurement UI. The proposal
requires the external comparator to supply hashes for the identical receive
waveform and 128-bit reference vector.

It remains a pending approval record. No receiver crate, CLI route, DFE/CDR/
BER algorithm, RFM input, Python dependency, or capability advertisement was
added.

## Verification

```text
python tools/test_verify_channel_rfm_receiver_semantic_charter.py
python tools/verify_channel_rfm_receiver_semantic_charter.py
python tools/verify_product_boundary.py
python tools/verify_clean_room_register.py
python tools/verify_release_license_preflight.py
python tools/verify_rust_candidate_source_map.py
```

All checks passed. The verifier rejects any proposal field drift or an attempt
to remove `approval_required`; the six owner decisions remain exactly pending.

## Accepted Scope

This accepts only a reviewable, fail-closed proposal for user approval. The
required RFM receiver profile remains blocked until the owner approves the
model and confirms that the external comparator can reproduce the same
reference-bit source and waveform.
