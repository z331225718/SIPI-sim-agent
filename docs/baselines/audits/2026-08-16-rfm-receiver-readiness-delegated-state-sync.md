# RFM Receiver Readiness Gate: Delegated-Policy State Sync — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3B-04 gate `tools/verify_channel_rfm_receiver_readiness.py` state-machine sync
- Status: resolved; drift was a committed verifier lag, not a working-tree change

## Facts

- `acceptance-profiles.v1.yaml` profile `channel-rfm-block-2-current-drive-v1`
  carries `acceptance.status: required_delegated_policy_agreement_not_lock_accepted`
  (committed, HEAD-clean).
- The delegated state is backed by an owner-approved amendment
  `docs/baselines/channel-rfm-receiver-delegated-phase-amendment.v1.yaml`
  (`status: approved_delegated_policy`, `approved_by: project_owner_delegated_policy`,
  `approval_ref: user-delegated-autonomy-2026-08-11`), and is already accepted by
  the acceptance-profiles verifier (`tools/verify_acceptance_profiles.py`).
- The readiness verifier's allowed-status set had not been synced: it rejected
  the live inventory with `required profile must remain oracle-only and blocked`.

## Resolution (state-machine sync, not tolerance widening)

- `verify_channel_rfm_receiver_readiness.py` now accepts the delegated status
  AND requires a new, stricter binding: when the profile status is
  `required_delegated_policy_agreement_not_lock_accepted`, the amendment must
  exist, carry schema `sipi.channel.receiver-delegated-phase-amendment.v1`,
  `status: approved_delegated_policy`, and the exact profile id; missing or
  unapproved amendments fail closed (`delegated phase amendment missing` /
  `delegated phase amendment binding is invalid`).
- `tolerance_policy_ref` may now be the amendment ref, alongside the two
  historical refs; every other fail-closed check is unchanged (identity,
  external observation pin, 8 missing semantics, required decision,
  evidence anchors, non-claims).
- Tests updated: live delegated inventory must validate; missing/unapproved
  amendment negative cases added (8 tests, all passed).

## Non-claims (unchanged)

The readiness record still pins all 8 receiver semantics as missing owner
selection; the amendment's own non-claims say a policy-selected phase is not a
clock-recovery lock, not external receiver parity, and not required-profile
acceptance. P3B-04 remains open (`owner_decision`; CDR lock semantics still
missing under the approved charter).
