"""Validate the fail-closed v0.2 release-license preflight manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.license-manifest.v2"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROLES = {"runtime", "build", "dev", "data", "tool"}
DEPENDENCY_STATUS = {"pending", "approved", "rejected"}
NOTICE_STATUS = {"pending", "approved", "not_required", "rejected"}


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _safe_ref(value: object, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("file:"):
        return False
    return not Path(value).is_absolute() and ".." not in value.split("/")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _owner_action(value: object, *, allow_pending: bool, blockers: list[str], label: str) -> bool:
    if not _exact(value, {"owner", "action", "approval_ref"}):
        blockers.append(f"{label}: owner_action has unknown or missing fields")
        return False
    if not all(isinstance(value[field], str) and value[field] for field in ("owner", "action")):
        blockers.append(f"{label}: owner_action requires owner and action")
        return False
    if not _safe_ref(value["approval_ref"], nullable=allow_pending):
        blockers.append(f"{label}: owner_action approval_ref is unsafe")
        return False
    return value["approval_ref"] is not None


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("release license manifest must be a YAML object")
    return value


def verify_document(document: object, root: Path = ROOT, *, release: bool = False) -> dict:
    blockers: list[str] = []
    if not _exact(document, {"schema", "status", "release_boundary", "legacy_evidence", "release_inputs", "blocking_actions", "non_claims"}):
        return {"valid": False, "release_ready": False, "blockers": ["manifest has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA or document["status"] not in {"provisional", "strict"}:
        return {"valid": False, "release_ready": False, "blockers": ["manifest schema or status mismatch"]}
    boundary = document["release_boundary"]
    if not _exact(boundary, {"path", "sha256", "status"}) or not _safe_ref(boundary.get("path")):
        blockers.append("release_boundary is incomplete or unsafe")
    else:
        boundary_path = root / boundary["path"]
        if not boundary_path.is_file() or not isinstance(boundary["sha256"], str) or not SHA256.fullmatch(boundary["sha256"]):
            blockers.append("release_boundary path or hash is invalid")
        elif _hash(boundary_path) != boundary["sha256"]:
            blockers.append("release_boundary hash mismatch")
        if boundary.get("status") not in {"provisional", "final"}:
            blockers.append("release_boundary status is invalid")
        else:
            try:
                boundary_document = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
            except OSError:
                boundary_document = None
            if not isinstance(boundary_document, dict) or boundary_document.get("status") != boundary["status"]:
                blockers.append("release_boundary status does not match referenced manifest")
    legacy = document["legacy_evidence"]
    legacy_ids: set[str] = set()
    if not isinstance(legacy, list):
        blockers.append("legacy_evidence must be a list")
    else:
        for item in legacy:
            if not _exact(item, {"id", "source_ref", "content_sha256", "observed_license", "use"}):
                blockers.append("legacy evidence has unknown or missing fields")
                continue
            item_id = item["id"]
            if not isinstance(item_id, str) or not item_id or item_id in legacy_ids:
                blockers.append(f"invalid or duplicate legacy evidence id: {item_id!r}")
                continue
            legacy_ids.add(item_id)
            path = root / item["source_ref"] if _safe_ref(item["source_ref"]) else None
            if path is None or not path.is_file() or not isinstance(item["content_sha256"], str) or not SHA256.fullmatch(item["content_sha256"]):
                blockers.append(f"{item_id}: legacy evidence source or hash is invalid")
            elif _hash(path) != item["content_sha256"]:
                blockers.append(f"{item_id}: legacy evidence hash mismatch")
            if not isinstance(item["observed_license"], str) or not item["observed_license"]:
                blockers.append(f"{item_id}: observed_license is required")
            if item["use"] != "migration_oracle_only":
                blockers.append(f"{item_id}: legacy evidence cannot be a release input")
    inputs = document["release_inputs"]
    required_inputs = {"first_party", "dependency_snapshot", "dependencies", "notices"}
    if not _exact(inputs, required_inputs):
        blockers.append("release_inputs has unknown or missing fields")
        inputs = {}
    first_party_approved = False
    snapshot_ready = False
    dependencies_ready = False
    notices_ready = False
    if inputs:
        first_party = inputs["first_party"]
        if not _exact(first_party, {"intended_license", "owner_action"}) or first_party.get("intended_license") != "MIT":
            blockers.append("first_party must declare intended MIT license")
        else:
            first_party_approved = _owner_action(first_party["owner_action"], allow_pending=True, blockers=blockers, label="first_party")
        snapshot = inputs["dependency_snapshot"]
        if not _exact(snapshot, {"status", "source_ref", "sha256"}) or snapshot.get("status") not in {"pending", "ready"}:
            blockers.append("dependency_snapshot is invalid")
        elif snapshot["status"] == "ready":
            if not _safe_ref(snapshot["source_ref"]) or not isinstance(snapshot["sha256"], str) or not SHA256.fullmatch(snapshot["sha256"]):
                blockers.append("ready dependency_snapshot requires safe source_ref and SHA-256")
            else:
                snapshot_ready = True
        elif snapshot["source_ref"] is not None or snapshot["sha256"] is not None:
            blockers.append("pending dependency_snapshot must not claim an artifact")
        dependencies = inputs["dependencies"]
        dependency_ids: set[str] = set()
        notice_ids: set[str] = set()
        approved_dependencies = True
        if not isinstance(dependencies, list):
            blockers.append("dependencies must be a list")
            dependencies = []
        for dependency in dependencies:
            keys = {"id", "component", "role", "source", "requested_version", "resolved_artifact", "declared_spdx", "license_evidence_ref", "notice_requirement", "sbom_component_id", "status", "owner_action"}
            if not _exact(dependency, keys):
                blockers.append("dependency has unknown or missing fields")
                continue
            dep_id = dependency["id"]
            if not isinstance(dep_id, str) or not dep_id or dep_id in dependency_ids or dep_id in legacy_ids:
                blockers.append(f"invalid, duplicate, or legacy dependency id: {dep_id!r}")
                continue
            dependency_ids.add(dep_id)
            if dependency["role"] not in ROLES or not all(_safe_ref(dependency[field]) for field in ("source", "license_evidence_ref", "sbom_component_id")):
                blockers.append(f"{dep_id}: dependency role or reference is unsafe")
            if not all(isinstance(dependency[field], str) and dependency[field] for field in ("component", "requested_version", "declared_spdx")):
                blockers.append(f"{dep_id}: dependency identity is incomplete")
            artifact = dependency["resolved_artifact"]
            if not _exact(artifact, {"version", "sha256"}):
                blockers.append(f"{dep_id}: resolved_artifact is invalid")
            elif dependency["status"] == "approved" and (not isinstance(artifact["version"], str) or not SHA256.fullmatch(str(artifact["sha256"]))):
                blockers.append(f"{dep_id}: approved dependency requires resolved artifact")
            elif dependency["status"] == "pending" and (artifact["version"] is not None or artifact["sha256"] is not None):
                blockers.append(f"{dep_id}: pending dependency cannot claim resolved artifact")
            if dependency["status"] not in DEPENDENCY_STATUS or dependency["notice_requirement"] not in {"required", "none", "pending"}:
                blockers.append(f"{dep_id}: dependency status or notice requirement is invalid")
            owner_approved = _owner_action(dependency["owner_action"], allow_pending=True, blockers=blockers, label=dep_id)
            approved_dependencies &= (
                dependency["status"] == "approved"
                and isinstance(artifact, dict)
                and isinstance(artifact.get("version"), str)
                and isinstance(artifact.get("sha256"), str)
                and SHA256.fullmatch(artifact["sha256"]) is not None
                and owner_approved
            )
            notice_ids.add(dep_id)
        dependencies_ready = approved_dependencies
        notices = inputs["notices"]
        if not isinstance(notices, list):
            blockers.append("notices must be a list")
            notices = []
        notice_dependencies = set()
        approved_notices = True
        for notice in notices:
            if not _exact(notice, {"dependency", "status", "source_evidence_ref", "output_notice_id"}):
                blockers.append("notice has unknown or missing fields")
                continue
            dependency = notice["dependency"]
            if dependency not in notice_ids or dependency in notice_dependencies or notice["status"] not in NOTICE_STATUS:
                blockers.append("notice dependency or status is invalid")
            notice_dependencies.add(dependency)
            if not all(_safe_ref(notice[field]) for field in ("source_evidence_ref", "output_notice_id")):
                blockers.append("notice references are unsafe")
            approved_notices &= notice["status"] in {"approved", "not_required"}
        if notice_dependencies != notice_ids:
            blockers.append("every dependency requires exactly one NOTICE decision")
            approved_notices = False
        notices_ready = approved_notices
    actions = document["blocking_actions"]
    action_pending = False
    if not isinstance(actions, list) or not actions:
        blockers.append("blocking_actions must be a non-empty list")
    else:
        seen_actions: set[str] = set()
        for action in actions:
            if not _exact(action, {"id", "owner", "action", "approval_ref"}):
                blockers.append("blocking action has unknown or missing fields")
                continue
            if not isinstance(action["id"], str) or not action["id"] or action["id"] in seen_actions:
                blockers.append("blocking action id is invalid or duplicate")
            seen_actions.add(action["id"])
            approved = _owner_action({"owner": action["owner"], "action": action["action"], "approval_ref": action["approval_ref"]}, allow_pending=True, blockers=blockers, label=action["id"])
            action_pending |= not approved
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("non_claims must be a non-empty string list")
    release_ready = (
        not blockers
        and document["status"] == "strict"
        and boundary.get("status") == "final"
        and first_party_approved
        and snapshot_ready
        and dependencies_ready
        and notices_ready
        and not action_pending
    )
    if release:
        blockers.append("release-license preflight v2 cannot authorize a release without an external resolved snapshot and release verifier")
        if not release_ready:
            blockers.append("release inputs are not approved and final")
    return {"valid": not blockers, "release_ready": release_ready, "status": document["status"], "dependency_count": len(inputs.get("dependencies", [])), "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "license-manifest.v2.yaml")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.manifest), release=args.release)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "release_ready": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
