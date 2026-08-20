"""Verify the owner-approved P7-08 same-batch drift-gate retirement strategy.

The strategy registers legacy migration gates and historical-evidence drift
gates, and encodes the batch rule: a gate may be removed in the same batch as
its legacy surface deletion, but only AFTER new-path acceptance. The owner
retirement approval is recorded in the approval record artifact; this verifier
requires approval_state == `owner_approved` AND cross-binds the signed
approval record (same approval state, non-empty signer and signing time, and
this strategy's exact current hash). Approval does NOT grant gate removal:
every entry disposition must remain retain, every mandatory pre-removal gate
must remain present, and the P7-08 blocker must remain. This verifier never
removes a gate, accepts a profile, or unblocks P7-08.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p7-08.drift-gate-retirement-strategy.v1"
STRATEGY = ROOT / "docs" / "baselines" / "p7-08-drift-gate-retirement-strategy.v1.yaml"
RECORD = ROOT / "docs" / "baselines" / "p7-08-retirement-approval-record.v1.yaml"
RECORD_SCHEMA = "sipi.p7-08.retirement-approval-record.v1"
BLOCKER = "blocked_no_path_scoped_replacement_and_retirement_approval"
APPROVAL_STATE = "owner_approved"
RECORD_APPROVAL_STATE = "owner_approved"

MANDATORY_GATES = frozenset({
    "per_path_replacement_mapping",
    "required_profile_accepted",
    "same_batch_drift_gate_removal",
    "release_license_fresh_machine_gates",
    "owner_retirement_approval",
})

GATE_KINDS = frozenset({"legacy_migration_gate", "historical_evidence_drift_gate"})

DISPOSITIONS = frozenset({"retain_gate_awaiting_approval"})
# Removal dispositions stay forbidden after owner approval: approval does not
# grant gate removal, which remains gated and same-batch.
FORBIDDEN_DISPOSITIONS = frozenset({
    "retire_now",
    "remove",
    "delete",
    "removal_approved",
    "retirement_approved",
    "gate_removed",
})

# Approval/retirement/release claim words stay forbidden in every strategy
# field even after owner approval: the approval fact lives ONLY in the signed
# approval record, never in this strategy's text.
FORBIDDEN_CLAIM_TOKENS = (
    "approved",
    "approved_by",
    "deletion_approved",
    "retirement_approved",
    "granted",
    "granted_by",
    "release_ready",
    "release_candidate",
)

ENTRY_FIELDS = frozenset({
    "id", "gate_path", "tracked_file_count", "gate_kind", "bound_surface",
    "disposition", "approval_required", "required_gates", "notes",
})

TOP_FIELDS = frozenset({
    "schema", "status", "approval_state", "blocker", "purpose", "batch_rule",
    "retirement_procedure", "mandatory_pre_removal_gates", "entries",
})

REQUIRED_GATE_PATHS = frozenset({
    "tools/verify_m0_capability_inventory.py",
    "tools/verify_m0_platform_support.py",
    "tools/verify_m1_artifacts.py",
    "tools/verify_m1_backend_execution_envelopes.py",
    "tools/verify_m1_capabilities_baseline.py",
    "tools/verify_m1_conformance.py",
    "tools/verify_m1_rule_ledger.py",
    "tools/verify_m1_run_envelopes.py",
    "tools/verify_m1_runtime_validation.py",
    "tools/verify_m2_capabilities_certified.py",
    "tools/verify_m4_conformance.py",
    "tools/verify_m5a_agent_spice_move.py",
    "tools/verify_m5a_agent_spice_preflight.py",
    "tools/verify_m5a_agent_spice_wheel.py",
    "tools/verify_m5b_ami_authorized_dll_closure.py",
    "tools/verify_m5b_ami_candidate_assurance.py",
    "tools/verify_m5b_ami_candidate_bundle.py",
    "tools/verify_m5b_ami_vendor_fixture_preflight.py",
    "tools/verify_m5b_pybert_history_preflight.py",
    "tools/verify_m5b_s2p_link_parity.py",
    "tools/verify_p3c_external_ads_selected_highloss_waveform_only_historical_source_drift.py",
    "tools/verify_p3c_selected_s4p_historical_observation_source_drift.py",
    "tools/verify_p3c_selected_sensitivity_historical_source_drift.py",
    "tools/verify_tran_rc_pulse_external_compare_evidence.py",
    "tools/verify_tran_rc_pulse_current_external_compare_evidence.py",
    "tools/verify_tran_rc_pulse_current_external_compare_evidence_v2.py",
    "tools/verify_tran_rc_pulse_current_external_compare_evidence_v3.py",
    "tools/verify_channel_s2p_matched_external_compare_evidence.py",
    "tools/verify_channel_s2p_matched_external_compare_evidence_v2.py",
    "tools/verify_channel_s2p_matched_cli_external_compare_evidence.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v2.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v3.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v4.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v5.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v6.py",
    "tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v7.py",
})


class StrategyError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if yaml is not None:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise StrategyError("invalid_strategy_document") from error
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StrategyError("invalid_strategy_document") from error
    if not isinstance(value, dict):
        raise StrategyError("invalid_strategy_document")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def has_forbidden_claim_token(value: str) -> bool:
    lowered = value.lower()
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", lowered) for token in FORBIDDEN_CLAIM_TOKENS)


def git_tracked_count(prefix: str) -> int:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", prefix],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired) as error:
        raise StrategyError("git_ls_files_failed") from error
    if completed.returncode != 0:
        raise StrategyError("git_ls_files_failed")
    return len([line for line in completed.stdout.splitlines() if line.strip()])


def check_approval_record(root: Path = ROOT) -> None:
    """Cross-bind the signed owner approval record.

    The strategy is owner-approved only when the approval record is signed for
    this exact strategy version: same approval state, non-empty
    signer/signing time, and the record's drift_gate_strategy binding hash
    equal to this strategy's current hash.
    """
    if not RECORD.is_file():
        raise StrategyError("approval_record_missing")
    record = load_json(RECORD)
    if record.get("schema") != RECORD_SCHEMA:
        raise StrategyError("approval_record_schema_invalid")
    if record.get("approval_state") != RECORD_APPROVAL_STATE:
        raise StrategyError("approval_record_not_owner_approved")
    if not isinstance(record.get("approved_by"), str) or not record["approved_by"]:
        raise StrategyError("approval_record_missing_signer")
    if not isinstance(record.get("approved_at_utc"), str) or not record["approved_at_utc"]:
        raise StrategyError("approval_record_missing_signing_time")
    binding = record.get("evidence_bindings", {}).get("drift_gate_strategy")
    if (
        not isinstance(binding, dict)
        or binding.get("path") != "docs/baselines/p7-08-drift-gate-retirement-strategy.v1.yaml"
    ):
        raise StrategyError("approval_record_binding_missing")
    if binding.get("sha256") != sha256_file(root / "docs/baselines/p7-08-drift-gate-retirement-strategy.v1.yaml"):
        raise StrategyError("approval_record_binding_hash_mismatch")


def validate(strategy: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    check_approval_record(root)
    if set(strategy) != TOP_FIELDS or strategy["schema"] != SCHEMA:
        raise StrategyError("strategy_schema_invalid")
    if strategy["status"] != "provisional":
        raise StrategyError("strategy_status_invalid")
    if strategy["approval_state"] != APPROVAL_STATE:
        raise StrategyError("strategy_approval_state_invalid")
    if strategy["blocker"] != BLOCKER:
        raise StrategyError("strategy_blocker_missing")
    if (
        not isinstance(strategy["purpose"], str)
        or not strategy["purpose"]
        or has_forbidden_claim_token(strategy["purpose"])
    ):
        raise StrategyError("strategy_purpose_invalid")
    if not isinstance(strategy["batch_rule"], str) or not strategy["batch_rule"]:
        raise StrategyError("strategy_batch_rule_invalid")
    procedure = strategy["retirement_procedure"]
    expected_procedure = [
        "owner_reviews_path_scoped_replacement_map",
        "owner_records_retirement_approval_in_audit",
        "same_batch_gate_removal_after_acceptance",
        "verifier_updated_before_any_removal",
    ]
    if procedure != expected_procedure:
        raise StrategyError("strategy_retirement_procedure_invalid")
    gates = strategy["mandatory_pre_removal_gates"]
    if len(gates) != len(MANDATORY_GATES) or set(gates) != MANDATORY_GATES:
        raise StrategyError("strategy_mandatory_gates_invalid")

    entries = strategy["entries"]
    if not isinstance(entries, list) or not entries:
        raise StrategyError("strategy_entries_invalid")
    ids: set[str] = set()
    gate_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            raise StrategyError("strategy_entry_schema_invalid")
        entry_id = entry["id"]
        gate_path = entry["gate_path"]
        if (
            not isinstance(entry_id, str)
            or not entry_id
            or entry_id in ids
            or not isinstance(gate_path, str)
            or not gate_path
            or gate_path in gate_paths
            or any(char in gate_path for char in "*?[")
            or not isinstance(entry["tracked_file_count"], int)
            or entry["tracked_file_count"] <= 0
            or entry["gate_kind"] not in GATE_KINDS
            or entry["disposition"] not in DISPOSITIONS
            or entry["disposition"] in FORBIDDEN_DISPOSITIONS
            or not isinstance(entry["approval_required"], bool)
            or not entry["approval_required"]
            or not isinstance(entry["notes"], str)
            or not entry["notes"]
            or has_forbidden_claim_token(entry["notes"])
        ):
            raise StrategyError("strategy_entry_field_invalid")
        ids.add(entry_id)
        gate_paths.add(gate_path)
        required_gates = entry["required_gates"]
        if len(required_gates) != len(MANDATORY_GATES) or set(required_gates) != MANDATORY_GATES:
            raise StrategyError("strategy_entry_required_gates_incomplete")
        actual_count = git_tracked_count(gate_path)
        if actual_count != entry["tracked_file_count"]:
            raise StrategyError("strategy_tracked_count_drift")

    missing = REQUIRED_GATE_PATHS - gate_paths
    if missing:
        raise StrategyError("strategy_coverage_missing")

    return {"valid": True, "entry_count": len(entries)}


def render(strategy: dict[str, Any]) -> str:
    lines = [
        "# SIPI P7-08 Same-Batch Drift-Gate Retirement Strategy",
        "",
        "Status: owner retirement approval recorded; gate removal remains gated",
        "by the same-batch rule and the mandatory pre-removal gates. This",
        "strategy does not remove any gate, accept any profile, or unblock",
        "P7-08.",
        "",
        "| Gate | Kind | Surface | Disposition |",
        "| --- | --- | --- | --- |",
    ]
    for entry in sorted(strategy["entries"], key=lambda item: item["gate_path"]):
        lines.append(
            f"| {entry['gate_path']} | {entry['gate_kind']} | "
            f"{entry['bound_surface']} | {entry['disposition']} |"
        )
    lines.extend(["", "## Batch Rule", "", strategy["batch_rule"], ""])
    lines.extend(["## Retirement Procedure", ""])
    lines.extend(f"{index}. `{step}`" for index, step in enumerate(strategy["retirement_procedure"], start=1))
    lines.extend(["", "## Mandatory Pre-Removal Gates", ""])
    lines.extend(f"- `{value}`" for value in sorted(strategy["mandatory_pre_removal_gates"]))
    lines.extend(["", "## Blockers", "", f"- `{strategy['blocker']}` (unchanged)"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=Path, default=STRATEGY)
    parser.add_argument("--render", type=Path)
    arguments = parser.parse_args()
    try:
        strategy = load_json(arguments.strategy)
        result = validate(strategy, ROOT)
        rendered = render(strategy)
        if arguments.render is not None:
            arguments.render.write_text(rendered, encoding="utf-8", newline="\n")
        print(json.dumps({
            "schema": SCHEMA,
            "valid": True,
            "entry_count": result["entry_count"],
            "render_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
        }, sort_keys=True))
        return 0
    except StrategyError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
