"""Verify the owner-approved P7-08 path-scoped replacement map.

The map enumerates per-path replacement and retirement dispositions for legacy
Python platform, adapters, engine, fixtures, and M0-M5 drift evidence. The
owner retirement approval is recorded in the approval record artifact; this
verifier requires approval_state == `owner_approved` AND cross-binds the
signed approval record (same approval state, non-empty signer and signing
time, and this map's exact current hash). Approval does NOT grant deletion or
gate removal: every entry disposition must remain retain/quarantine, every
mandatory pre-deletion gate must remain present, and the P7-08 blocker must
remain. This verifier never removes a path, removes a drift gate, accepts a
profile, or unblocks P7-08.
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
SCHEMA = "sipi.p7-08.path-scoped-replacement-map.v1"
MAP = ROOT / "docs" / "baselines" / "p7-08-path-scoped-replacement-map.v1.yaml"
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

CLASSIFICATIONS = frozenset({
    "migration_only",
    "migration_evidence",
    "quarantine",
    "test_fixture",
    "oracle_only",
})

REPLACEMENT_STATUSES = frozenset({
    "replaced_for_product_surface",
    "superseded_by_rust_contracts",
    "superseded_by_rust_artifacts",
    "superseded_by_rust_runtime",
    "partial_or_none",
    "partial_replaced_native_core",
    "quarantine",
    "retained_test_input",
    "mixed",
    "no_product_replacement",
})

# Approval/retirement/release claim words, matched on word boundaries so they
# cannot be smuggled into free-text fields. They remain forbidden in every map
# field even after owner approval: the approval fact lives ONLY in the signed
# approval record, never in this map's text. "rc" is intentionally absent: as a
# bare substring it collides with ordinary words (archive, rust-candidate);
# "release_candidate" already covers the release-claim surface.
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

# Dispositions that would delete or retire material stay forbidden after owner
# approval: approval does not grant deletion, which remains gated.
DISPOSITIONS = frozenset({
    "retain_migration_evidence",
    "retain_oracle_evidence",
    "retain_external_reference",
    "retain_test_fixture",
    "quarantine",
})
FORBIDDEN_DISPOSITIONS = frozenset({
    "retire_now",
    "delete",
    "remove",
    "deletion_approved",
    "retirement_approved",
})

ENTRY_FIELDS = frozenset({
    "id", "path_prefix", "tracked_file_count", "classification",
    "replacement_owner", "replacement_status", "disposition",
    "approval_required", "required_gates", "notes",
})

REPLACEMENT_OWNER_PREFIXES = ("crates/", "native/crates/")


class MapError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if yaml is not None:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise MapError("invalid_map_document") from error
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MapError("invalid_map_document") from error
    if not isinstance(value, dict):
        raise MapError("invalid_map_document")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def has_forbidden_claim_token(value: str) -> bool:
    lowered = value.lower()
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", lowered) for token in FORBIDDEN_CLAIM_TOKENS)


def git_tracked_count(prefix: str) -> int:
    """Return the number of git-tracked paths under prefix (file or dir).

    Binding is intentionally against the git index (git ls-files), the same
    fact source the release chain uses for tracked paths, not the working tree.
    Working-tree-only deletions are out of scope for this map: the map governs
    tracked material, and actual removal happens through git operations that
    also update the index.
    """
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
        raise MapError("git_ls_files_failed") from error
    if completed.returncode != 0:
        raise MapError("git_ls_files_failed")
    return len([line for line in completed.stdout.splitlines() if line.strip()])


def check_approval_record(root: Path = ROOT) -> None:
    """Cross-bind the signed owner approval record.

    The map is owner-approved only when the approval record is signed for this
    exact map version: same approval state, non-empty signer/signing time, and
    the record's replacement_map binding hash equal to this map's current hash.
    """
    if not RECORD.is_file():
        raise MapError("approval_record_missing")
    record = load_json(RECORD)
    if record.get("schema") != RECORD_SCHEMA:
        raise MapError("approval_record_schema_invalid")
    if record.get("approval_state") != RECORD_APPROVAL_STATE:
        raise MapError("approval_record_not_owner_approved")
    if not isinstance(record.get("approved_by"), str) or not record["approved_by"]:
        raise MapError("approval_record_missing_signer")
    if not isinstance(record.get("approved_at_utc"), str) or not record["approved_at_utc"]:
        raise MapError("approval_record_missing_signing_time")
    binding = record.get("evidence_bindings", {}).get("replacement_map")
    if (
        not isinstance(binding, dict)
        or binding.get("path") != "docs/baselines/p7-08-path-scoped-replacement-map.v1.yaml"
    ):
        raise MapError("approval_record_binding_missing")
    if binding.get("sha256") != sha256_file(root / "docs/baselines/p7-08-path-scoped-replacement-map.v1.yaml"):
        raise MapError("approval_record_binding_hash_mismatch")


def validate(map_document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    check_approval_record(root)
    required = {
        "schema", "status", "approval_state", "blocker", "purpose",
        "binding_refs", "mandatory_pre_deletion_gates", "entries",
    }
    if set(map_document) != required or map_document["schema"] != SCHEMA:
        raise MapError("map_schema_invalid")
    if map_document["status"] != "provisional":
        raise MapError("map_status_invalid")
    if map_document["approval_state"] != APPROVAL_STATE:
        raise MapError("map_approval_state_invalid")
    if map_document["blocker"] != BLOCKER:
        raise MapError("map_blocker_missing")
    if (
        not isinstance(map_document["purpose"], str)
        or not map_document["purpose"]
        or has_forbidden_claim_token(map_document["purpose"])
        or not isinstance(map_document["binding_refs"], list)
        or not map_document["binding_refs"]
    ):
        raise MapError("map_purpose_or_binding_invalid")
    gates = map_document["mandatory_pre_deletion_gates"]
    if len(gates) != len(MANDATORY_GATES) or set(gates) != MANDATORY_GATES:
        raise MapError("map_mandatory_gates_invalid")

    entries = map_document["entries"]
    if not isinstance(entries, list) or not entries:
        raise MapError("map_entries_invalid")
    ids: set[str] = set()
    prefixes: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            raise MapError("map_entry_schema_invalid")
        entry_id = entry["id"]
        prefix = entry["path_prefix"]
        if (
            not isinstance(entry_id, str)
            or not entry_id
            or entry_id in ids
            or not isinstance(prefix, str)
            or not prefix
            or prefix in prefixes
            or any(char in prefix for char in "*?[")
            or not isinstance(entry["tracked_file_count"], int)
            or entry["tracked_file_count"] <= 0
            or entry["classification"] not in CLASSIFICATIONS
            or entry["replacement_status"] not in REPLACEMENT_STATUSES
            or entry["disposition"] not in DISPOSITIONS
            or entry["disposition"] in FORBIDDEN_DISPOSITIONS
            or not isinstance(entry["approval_required"], bool)
            or not isinstance(entry["notes"], str)
            or not entry["notes"]
            or has_forbidden_claim_token(entry["replacement_status"])
            or has_forbidden_claim_token(entry["notes"])
        ):
            raise MapError("map_entry_field_invalid")
        ids.add(entry_id)
        prefixes.add(prefix)

        replacement_owner = entry["replacement_owner"]
        if replacement_owner is not None:
            if (
                not isinstance(replacement_owner, str)
                or not replacement_owner
                or not replacement_owner.startswith(REPLACEMENT_OWNER_PREFIXES)
                or ".." in replacement_owner.split("/")
            ):
                raise MapError("map_replacement_owner_invalid")
            if not (root / replacement_owner).is_dir():
                raise MapError("map_replacement_owner_missing")

        required_gates = entry["required_gates"]
        if not isinstance(required_gates, list):
            raise MapError("map_entry_required_gates_invalid")
        if entry["approval_required"]:
            if len(required_gates) != len(MANDATORY_GATES) or set(required_gates) != MANDATORY_GATES:
                raise MapError("map_entry_required_gates_incomplete")
        elif required_gates:
            raise MapError("map_entry_required_gates_unexpected")

        actual_count = git_tracked_count(prefix)
        if actual_count != entry["tracked_file_count"]:
            raise MapError("map_tracked_count_drift")

    # The map must cover every legacy tree named by the P7-08 blocker with
    # EXACT path matches. A nested prefix (e.g. tests/contract) must not
    # satisfy coverage for its parent (e.g. tests), or a narrower entry could
    # silently replace whole-tree coverage.
    required_prefixes = {
        "apps/sipi-cli",
        "packages/sipi-contracts",
        "packages/sipi-artifacts",
        "packages/sipi-runtime",
        "packages/sipi-adapters",
        "engines/agent-spice",
        "native/crates/sipi-circuit",
        "native/crates/sipi-ami",
        "fixtures/contracts",
        "tests",
        "docs/baselines/migrations",
        "docs/baselines/m5b-ami-authorized-dll-closure-preflight.v1.json",
        "docs/baselines/m5b-ami-candidate-bundle-preflight.v1.json",
        "docs/baselines/m5b-ami-candidate-bundle-preflight.v1.md",
        "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json",
        "docs/baselines/m5b-pybert-history-preflight.v1.json",
    }
    covered = {entry["path_prefix"] for entry in entries}
    missing = {prefix for prefix in required_prefixes if prefix not in covered}
    if missing:
        raise MapError("map_coverage_missing")

    return {"valid": True, "entry_count": len(entries)}


def render(map_document: dict[str, Any]) -> str:
    lines = [
        "# SIPI P7-08 Path-Scoped Replacement Map",
        "",
        "Status: owner retirement approval recorded; deletion and gate removal",
        "remain gated by the mandatory pre-deletion gates. This map does not",
        "retire any path, remove any drift gate, accept any profile, or",
        "unblock P7-08.",
        "",
        "| Path | Classification | Replacement Owner | Replacement Status | Disposition | Approval Required |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in sorted(map_document["entries"], key=lambda item: item["path_prefix"]):
        owner = entry["replacement_owner"] or "—"
        lines.append(
            f"| {entry['path_prefix']} | {entry['classification']} | {owner} | "
            f"{entry['replacement_status']} | {entry['disposition']} | {entry['approval_required']} |"
        )
    lines.extend(["", "## Mandatory Pre-Deletion Gates", ""])
    lines.extend(f"- `{value}`" for value in sorted(map_document["mandatory_pre_deletion_gates"]))
    lines.extend(["", "## Blockers", "", f"- `{map_document['blocker']}` (unchanged)"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=MAP)
    parser.add_argument("--render", type=Path)
    arguments = parser.parse_args()
    try:
        map_document = load_json(arguments.map)
        result = validate(map_document, ROOT)
        rendered = render(map_document)
        if arguments.render is not None:
            arguments.render.write_text(rendered, encoding="utf-8", newline="\n")
        print(json.dumps({
            "schema": SCHEMA,
            "valid": True,
            "entry_count": result["entry_count"],
            "render_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
        }, sort_keys=True))
        return 0
    except MapError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
