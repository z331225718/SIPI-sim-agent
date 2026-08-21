"""Verify P1 external source identities and required-profile facts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import verify_p1_04b_legacy_fixture_boundary as legacy_boundary

DOCUMENT = ROOT / "docs/baselines/p1-legacy-fixture-required-profile-facts.v1.yaml"
MANIFEST = ROOT / "fixtures/manifest.v1.json"
SCHEMA = "sipi.p1-legacy-fixture-required-profile-facts.v1"


class FactsError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repository: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise FactsError("git_identity_unavailable") from error


def _archive_identity(repository: Path, commit: str) -> tuple[str, int]:
    try:
        process = subprocess.Popen(
            ["git", "-C", str(repository), "archive", "--format=tar", commit],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:
            process.kill()
            raise FactsError("git_archive_unavailable")
        digest = hashlib.sha256()
        size = 0
        while chunk := process.stdout.read(64 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if process.wait() != 0:
            raise FactsError("git_archive_unavailable")
        return digest.hexdigest(), size
    except OSError as error:
        raise FactsError("git_archive_unavailable") from error


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise FactsError("document_invalid") from error
    if not isinstance(value, dict):
        raise FactsError("document_invalid")
    return value


def validate(document: dict[str, Any], *, external_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    expected = {"schema", "kind", "captured_at_utc", "manifest", "source_snapshots", "profile_facts", "gates", "non_claims", "audit_ref"}
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "external_snapshot_identity_and_required_profile_clue_observation":
        raise FactsError("document_schema_invalid")
    manifest = document["manifest"]
    if manifest != {"path": "fixtures/manifest.v1.json", "sha256": "9601a1755c628bd85da0b4205858fa232687ecd39d1a398f3d26cd6a8a612e79", "bytes": 12904}:
        raise FactsError("manifest_binding_invalid")
    if _sha256(MANIFEST) != manifest["sha256"] or MANIFEST.stat().st_size != manifest["bytes"]:
        raise FactsError("manifest_identity_invalid")

    expected_sources = {
        "agent-spice": ("90f0374bc9987e9197d4dcaa3912432fbd766a5e", "b5db1cb9a1a989459dffe7db885790abeaf47290", "ed28cedfae54baf961c599eedbf8327a47bf6f82314c7752c494bc8b7ae192d4", 124753920),
        "pybert": ("5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "5faef6bdb341d444ad65d82a11c0018b15805e24", "ffe693b13b598e7c365adeda4bb46cc776ffbd8135b3ac0c8f7568ed8b5d6c92", 133396480),
        "agent-com": ("034b21b2f293b2ef97cb8be269b1bf2be38e0086", "dc6e5529612d7272f23547a796b53e1456cc49cb", "6f8eda32959ff15e712f7b0de7c64d45ce1cd44fcdbabc2aee74302eaaa63662", 43939840),
    }
    snapshots = document["source_snapshots"]
    if not isinstance(snapshots, list) or {item.get("root_ref") for item in snapshots if isinstance(item, dict)} != set(expected_sources):
        raise FactsError("source_snapshot_set_invalid")
    for item in snapshots:
        if not isinstance(item, dict) or set(item) != {"root_ref", "commit", "tree", "git_archive_tar_sha256", "git_archive_tar_bytes"}:
            raise FactsError("source_snapshot_schema_invalid")
        root_ref = item["root_ref"]
        if root_ref not in expected_sources:
            raise FactsError("source_snapshot_unknown")
        commit, tree, archive_sha, archive_bytes = expected_sources[root_ref]
        if tuple(item[field] for field in ("commit", "tree", "git_archive_tar_sha256", "git_archive_tar_bytes")) != (commit, tree, archive_sha, archive_bytes):
            raise FactsError("source_snapshot_binding_invalid")
        if external_roots is not None:
            repository = external_roots.get(root_ref)
            if repository is None or _git(repository, "cat-file", "-t", commit) != "commit" or _git(repository, "rev-parse", f"{commit}^{{tree}}") != tree:
                raise FactsError("source_snapshot_git_identity_invalid")
            if _archive_identity(repository, commit) != (archive_sha, archive_bytes):
                raise FactsError("source_archive_identity_invalid")

    try:
        source_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FactsError("fixture_manifest_invalid") from error
    assets = source_manifest.get("assets")
    if not isinstance(assets, list) or len(assets) != 14:
        raise FactsError("asset_count_invalid")
    required_ids = sorted(asset["id"] for asset in assets if any(entry.get("requirement") == "required" for entry in asset.get("required_by", [])))
    expected_ids = sorted(document["profile_facts"]["required_asset_ids"])
    facts = document["profile_facts"]
    if facts.get("asset_count") != 14 or facts.get("distribution_status_counts") != {"blocked_unknown": 14} or facts.get("required_by_required_count") != 9 or required_ids != expected_ids or facts.get("required_profile_fields_present") is not False or facts.get("required_profile_values") != []:
        raise FactsError("profile_facts_invalid")
    if any(asset.get("distribution", {}).get("status") != "blocked_unknown" for asset in assets):
        raise FactsError("distribution_status_invalid")
    if any("required_profile" in asset or "profile" in asset for asset in assets):
        raise FactsError("required_profile_field_present")
    try:
        boundary = legacy_boundary.validate(source_manifest, ROOT)
    except legacy_boundary.LegacyFixtureBoundaryError as error:
        raise FactsError("legacy_fixture_boundary_failed") from error
    if boundary.get("valid") is not True or boundary.get("external_assets") != 14:
        raise FactsError("legacy_fixture_boundary_failed")
    expected_gates = {"source_snapshot_git_objects_observed": True, "source_archive_identities_observed": True, "legacy_fixture_boundary_passed": True, "required_profile_selected": False, "required_profile_accepted": False, "distribution_authorized": False, "owner_decision_required": True}
    if document.get("gates") != expected_gates:
        raise FactsError("gate_state_invalid")
    if document.get("non_claims") != ["required_by_gate_labels_are_not_a_required_profile_selection", "no_legacy_fixture_is_promoted_into_product_or_public_bundle", "source_archive_identity_does_not_grant_distribution_rights", "no_license_or_notice_conclusion_is_made", "no_profile_parity_or_release_acceptance_is_claimed"]:
        raise FactsError("non_claims_invalid")
    if document.get("audit_ref") != "docs/baselines/audits/2026-08-21-p1-legacy-fixture-required-profile-facts.md" or not (ROOT / document["audit_ref"]).is_file():
        raise FactsError("audit_reference_invalid")
    return {"schema": SCHEMA, "valid": True, "assets": len(assets), "required_assets": len(required_ids)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-spice-root", type=Path)
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    arguments = parser.parse_args()
    try:
        roots = {
            "agent-spice": arguments.agent_spice_root,
            "pybert": arguments.pybert_root,
            "agent-com": arguments.agent_com_root,
        }
        if any(value is not None for value in roots.values()) and any(value is None for value in roots.values()):
            raise FactsError("all_external_roots_required")
        print(json.dumps(validate(_load(DOCUMENT), external_roots=roots if all(value is not None for value in roots.values()) else None), sort_keys=True))
        return 0
    except FactsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
