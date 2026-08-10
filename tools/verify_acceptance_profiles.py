"""Verify the oracle-only candidate acceptance-profile inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.acceptance-profiles.v1"
CAPABILITIES = {"tran", "channel", "ibis_ami", "com"}
SHA1_LENGTH = 40
SHA256_LENGTH = 64


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _safe_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\\" not in value
        and not value.startswith("/")
        and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
        and ".." not in value.split("/")
    )


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("acceptance inventory must be a YAML object")
    return document


def _git_blob_bytes(repo: Path, commit: str, path: str) -> tuple[str, bytes]:
    output = subprocess.run(["git", "-C", str(repo), "rev-parse", f"{commit}:{path}"], check=True, capture_output=True, text=True).stdout.strip()
    payload = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", output], check=True, capture_output=True).stdout
    return output, payload


def verify_document(document: object, source_roots: dict[str, Path] | None = None) -> dict:
    blockers: list[str] = []
    if not _exact(document, {"schema", "inventory_status", "repositories", "profiles", "non_claims"}):
        return {"valid": False, "blockers": ["inventory has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA or document["inventory_status"] != "candidate":
        return {"valid": False, "blockers": ["inventory schema or status mismatch"]}
    repositories = document["repositories"]
    repository_map: dict[str, dict] = {}
    if not isinstance(repositories, list):
        blockers.append("repositories must be a list")
    else:
        for repository in repositories:
            if not _exact(repository, {"id", "canonical_origin", "commit", "object_format"}):
                blockers.append("repository has unknown or missing fields")
                continue
            repository_id = repository["id"]
            if not isinstance(repository_id, str) or not repository_id or repository_id in repository_map:
                blockers.append(f"invalid or duplicate repository id: {repository_id!r}")
            elif not isinstance(repository["canonical_origin"], str) or not repository["canonical_origin"] or not _hex(repository["commit"], SHA1_LENGTH) or repository["object_format"] != "sha1":
                blockers.append(f"{repository_id}: invalid immutable repository anchor")
            else:
                repository_map[repository_id] = repository
    profiles = document["profiles"]
    profile_ids: set[str] = set()
    checked_sources = 0
    required_profiles = 0
    if not isinstance(profiles, list) or not profiles:
        blockers.append("profiles must be a non-empty list")
    else:
        for profile in profiles:
            keys = {"id", "capability", "boundary", "source", "assets", "source_license_evidence", "environment", "acceptance", "evidence_refs", "notes"}
            if not _exact(profile, keys):
                blockers.append("profile has unknown or missing fields")
                continue
            profile_id = profile["id"]
            if not isinstance(profile_id, str) or not profile_id or profile_id in profile_ids:
                blockers.append(f"invalid or duplicate profile id: {profile_id!r}")
                continue
            profile_ids.add(profile_id)
            if profile["capability"] not in CAPABILITIES or profile["boundary"] != "oracle_only":
                blockers.append(f"{profile_id}: capability or boundary is invalid")
            source = profile["source"]
            if not _exact(source, {"repository", "path", "git_blob", "content_sha256"}) or source.get("repository") not in repository_map or not _safe_path(source.get("path")) or not _hex(source.get("git_blob"), SHA1_LENGTH) or not _hex(source.get("content_sha256"), SHA256_LENGTH):
                blockers.append(f"{profile_id}: source anchor is invalid")
            assets = profile["assets"]
            if not isinstance(assets, list):
                blockers.append(f"{profile_id}: assets must be a list")
            else:
                for asset in assets:
                    if not _exact(asset, {"path", "git_blob", "content_sha256", "redistribution"}) or not _safe_path(asset.get("path")) or not _hex(asset.get("git_blob"), SHA1_LENGTH) or not _hex(asset.get("content_sha256"), SHA256_LENGTH) or asset.get("redistribution") not in {"external_only", "authorized_test_only", "unknown"}:
                        blockers.append(f"{profile_id}: asset is invalid")
            environment = profile["environment"]
            if not _exact(environment, {"platform", "provenance_status", "provenance_ref"}) or environment.get("platform") != "windows-x86_64" or environment.get("provenance_status") not in {"evidence_incomplete", "verified"} or not _safe_path(environment.get("provenance_ref")):
                blockers.append(f"{profile_id}: environment is invalid")
            acceptance = profile["acceptance"]
            required = {"observable", "comparator_ref", "tolerance_policy_ref", "status", "required_by"}
            if not _exact(acceptance, required) or not all(isinstance(acceptance.get(field), str) and acceptance[field] for field in ("observable", "comparator_ref", "tolerance_policy_ref")):
                blockers.append(f"{profile_id}: acceptance is incomplete")
            elif acceptance.get("status") == "candidate":
                if acceptance.get("required_by") is not None:
                    blockers.append(f"{profile_id}: candidate acceptance cannot carry a required decision")
            elif acceptance.get("status") in {"required_pending_preflight", "required_pending_numerical_compare"}:
                if not isinstance(acceptance.get("required_by"), str) or not acceptance["required_by"]:
                    blockers.append(f"{profile_id}: selected acceptance requires a decision reference")
                else:
                    required_profiles += 1
            else:
                blockers.append(f"{profile_id}: acceptance status is invalid")
            if not isinstance(profile["source_license_evidence"], str) or not profile["source_license_evidence"] or not isinstance(profile["evidence_refs"], list) or not profile["evidence_refs"] or not all(_safe_path(item) for item in profile["evidence_refs"]) or not isinstance(profile["notes"], str) or not profile["notes"]:
                blockers.append(f"{profile_id}: evidence or notes are invalid")
            if source_roots and source.get("repository") in source_roots and _safe_path(source.get("path")):
                repo = source_roots[source["repository"]]
                try:
                    blob, payload = _git_blob_bytes(repo, repository_map[source["repository"]]["commit"], source["path"])
                except (OSError, subprocess.CalledProcessError):
                    blockers.append(f"{profile_id}: source Git object is unavailable")
                else:
                    checked_sources += 1
                    if blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
                        blockers.append(f"{profile_id}: source Git object identity mismatch")
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("non_claims must be a non-empty string list")
    return {"valid": not blockers, "inventory_status": document["inventory_status"], "profile_count": len(profile_ids), "required_profile_count": required_profiles, "git_object_checked_count": checked_sources, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=ROOT / "acceptance-profiles.v1.yaml")
    parser.add_argument("--source-root", action="append", default=[], metavar="ID=PATH")
    args = parser.parse_args()
    roots: dict[str, Path] = {}
    for item in args.source_root:
        if "=" not in item:
            parser.error("--source-root requires ID=PATH")
        key, path = item.split("=", 1)
        roots[key] = Path(path)
    try:
        report = verify_document(_load(args.inventory), roots)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
