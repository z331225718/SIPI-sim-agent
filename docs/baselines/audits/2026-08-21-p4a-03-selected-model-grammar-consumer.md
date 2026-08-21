# P4A-03 Selected-Model Grammar Consumer Audit

The bounded selected-model consumer is implemented in
`crates/sipi-ibis/src/selected_model_v1.rs` and exported by `sipi-ibis`.
It reuses the complete typed inventory consumer and requires a caller-owned
`SignalPinRoleV1`, `SelectedModelTargetV1`, `CornerPvtV1`, and
`TableFamilyV1`.  Resolution is unique and fail-closed: duplicate roles,
unknown/disconnected models, duplicate selector branches, duplicate table
families, empty tables, malformed completion, and out-of-bound input reject.

The returned `SelectedModelSelectionV1` contains only bounded identity facts
and the required table identity.  It does not return rows or evaluate values;
there is no transient or AMI path.

Synthetic unit tests cover direct and selector-branch resolution, explicit
PVT/table fields, complete-document rejection, role ambiguity, disconnected
targets, duplicate tables, and invalid request fields.  The ignored
`p4a_03bk_selected_model_runner` accepts an operator-supplied request and can
read the complete official object outside the worktree.  Invoking it without a
request reports `missing_required_selected_profile` after bounded inventory;
it never guesses a concrete model, corner, or table family.

This closes only the grammar/consumer implementation scope.  P4A-03's
external profile/oracle status remains blocked on a required selected profile,
and P4A-01 rights remain blocked.
