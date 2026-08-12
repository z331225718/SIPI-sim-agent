"""Fail-closed validation for declared clean-room material boundaries."""

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
SCHEMA = "sipi.clean-room-register.v1"
ROLES = {"observer", "spec_author", "implementer", "comparator", "auditor", "release_approver"}
MATERIAL_KINDS = {
    "public_standard",
    "mit_source",
    "bsd3_source",
    "independent_spec",
    "non_mit_source",
    "pybert_source",
    "oracle_fixture",
    "prohibited_implementation_input",
}
IMPLEMENTATION_KINDS = {"public_standard", "mit_source", "bsd3_source", "independent_spec"}
STATES = {
    "planned": 0,
    "observation_sealed": 1,
    "spec_sealed": 2,
    "implementation_attested": 3,
    "comparison_attested": 4,
    "audit_accepted": 5,
    "release_eligible": 6,
}
PHASES = {
    "observation_sealed": ("observer", "observation_materials_sealed"),
    "spec_sealed": ("spec_author", "independent_spec_sealed"),
    "implementation_attested": ("implementer", "implementation_allowlist_attested"),
    "comparison_attested": ("comparator", "comparison_boundary_attested"),
    "audit_accepted": ("auditor", "clean_room_audit_accepted"),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _has_exact_keys(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _safe_ref(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("file:"):
        return False
    candidate = Path(value)
    return not candidate.is_absolute() and ".." not in value.split("/")


def _safe_glob(value: object) -> bool:
    return _safe_ref(value) and not str(value).startswith("/")


def _hash_material_ids(ids: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode("utf-8")).hexdigest()


def _load_document(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("clean-room register must be a YAML object")
    return document


def _material_closure(material_id: str, materials: dict[str, dict], visiting: set[str], blockers: list[str]) -> set[str]:
    if material_id in visiting:
        blockers.append(f"material derivation cycle at {material_id}")
        return set()
    material = materials.get(material_id)
    if material is None:
        blockers.append(f"unknown material: {material_id}")
        return set()
    ancestors: set[str] = {material_id}
    for parent in material["derived_from"]:
        ancestors |= _material_closure(parent, materials, visiting | {material_id}, blockers)
    return ancestors


def _verify_materials(value: object, root: Path, blockers: list[str]) -> dict[str, dict]:
    if not isinstance(value, list):
        blockers.append("materials must be a list")
        return {}
    materials: dict[str, dict] = {}
    for material in value:
        keys = {"id", "kind", "content_sha256", "provenance", "allowed_roles", "derived_from"}
        if not _has_exact_keys(material, keys):
            blockers.append("material has unknown or missing fields")
            continue
        material_id = material["id"]
        if not isinstance(material_id, str) or not material_id or material_id in materials:
            blockers.append(f"invalid or duplicate material id: {material_id!r}")
            continue
        if material["kind"] not in MATERIAL_KINDS:
            blockers.append(f"{material_id}: invalid material kind")
        if not isinstance(material["content_sha256"], str) or not SHA256.fullmatch(material["content_sha256"]):
            blockers.append(f"{material_id}: content_sha256 must be lowercase SHA-256")
        provenance = material["provenance"]
        if not _has_exact_keys(provenance, {"source_ref", "license_evidence"}) or not all(
            _safe_ref(provenance.get(field)) for field in ("source_ref", "license_evidence")
        ):
            blockers.append(f"{material_id}: unsafe or incomplete provenance")
        elif material["kind"] == "independent_spec":
            source = root / provenance["source_ref"]
            if not source.is_file():
                blockers.append(f"{material_id}: independent_spec source is missing")
            elif hashlib.sha256(source.read_bytes()).hexdigest() != material["content_sha256"]:
                blockers.append(f"{material_id}: independent_spec content hash mismatch")
        roles = material["allowed_roles"]
        if not isinstance(roles, list) or not roles or len(set(roles)) != len(roles) or not set(roles) <= ROLES:
            blockers.append(f"{material_id}: invalid allowed_roles")
        parents = material["derived_from"]
        if not isinstance(parents, list) or len(set(parents)) != len(parents) or not all(
            isinstance(parent, str) and parent for parent in parents
        ):
            blockers.append(f"{material_id}: invalid derived_from")
        materials[material_id] = material
    for material_id, material in materials.items():
        _material_closure(material_id, materials, set(), blockers)
    return materials


def _verify_principals(value: object, blockers: list[str]) -> dict[str, dict]:
    if not isinstance(value, list):
        blockers.append("principals must be a list")
        return {}
    principals: dict[str, dict] = {}
    for principal in value:
        if not _has_exact_keys(principal, {"id", "roles", "identity_ref", "status"}):
            blockers.append("principal has unknown or missing fields")
            continue
        principal_id = principal["id"]
        if not isinstance(principal_id, str) or not principal_id or principal_id in principals:
            blockers.append(f"invalid or duplicate principal id: {principal_id!r}")
            continue
        roles = principal["roles"]
        if not isinstance(roles, list) or not roles or len(set(roles)) != len(roles) or not set(roles) <= ROLES:
            blockers.append(f"{principal_id}: invalid roles")
        if not _safe_ref(principal["identity_ref"]):
            blockers.append(f"{principal_id}: unsafe identity_ref")
        if principal["status"] not in {"active", "placeholder"}:
            blockers.append(f"{principal_id}: invalid principal status")
        principals[principal_id] = principal
    return principals


def _verify_attestations(
    value: object,
    scopes: dict[str, dict],
    principals: dict[str, dict],
    materials: dict[str, dict],
    strict: bool,
    blockers: list[str],
) -> dict[str, set[str]]:
    if not isinstance(value, list):
        blockers.append("attestations must be a list")
        return {}
    phases_by_scope: dict[str, set[str]] = {scope_id: set() for scope_id in scopes}
    seen: set[str] = set()
    for attestation in value:
        required = {
            "id", "scope", "phase", "principal", "role", "subject_sha256", "material_set_sha256",
            "statement", "evidence_refs", "created_at", "signature_ref",
        }
        if not _has_exact_keys(attestation, required):
            blockers.append("attestation has unknown or missing fields")
            continue
        attestation_id = attestation["id"]
        if not isinstance(attestation_id, str) or not attestation_id or attestation_id in seen:
            blockers.append(f"invalid or duplicate attestation id: {attestation_id!r}")
            continue
        seen.add(attestation_id)
        scope = scopes.get(attestation["scope"])
        phase = attestation["phase"]
        principal = principals.get(attestation["principal"])
        expected = PHASES.get(phase)
        if scope is None or expected is None or principal is None:
            blockers.append(f"{attestation_id}: unknown scope, phase, or principal")
            continue
        expected_role, expected_statement = expected
        if attestation["role"] != expected_role or attestation["statement"] != expected_statement:
            blockers.append(f"{attestation_id}: phase role or statement mismatch")
        if expected_role not in principal["roles"] or principal["status"] != "active":
            blockers.append(f"{attestation_id}: principal is not an active {expected_role}")
        if not isinstance(attestation["subject_sha256"], str) or not SHA256.fullmatch(attestation["subject_sha256"]):
            blockers.append(f"{attestation_id}: invalid subject_sha256")
        role_ids = scope["role_material_allowlists"].get(expected_role, [])
        closure: set[str] = set()
        for material_id in role_ids:
            closure |= _material_closure(material_id, materials, set(), blockers)
        if attestation["material_set_sha256"] != _hash_material_ids(closure):
            blockers.append(f"{attestation_id}: material_set_sha256 mismatch")
        evidence = attestation["evidence_refs"]
        if not isinstance(evidence, list) or not evidence or not all(_safe_ref(item) for item in evidence):
            blockers.append(f"{attestation_id}: invalid evidence_refs")
        if not isinstance(attestation["created_at"], str) or not RFC3339.fullmatch(attestation["created_at"]):
            blockers.append(f"{attestation_id}: invalid created_at")
        if strict and not _safe_ref(attestation["signature_ref"]):
            blockers.append(f"{attestation_id}: strict mode requires signature_ref")
        if not strict and attestation["signature_ref"] is not None and not _safe_ref(attestation["signature_ref"]):
            blockers.append(f"{attestation_id}: invalid signature_ref")
        phases_by_scope[attestation["scope"]].add(phase)
    return phases_by_scope


def verify_document(document: object, *, release: bool = False, root: Path = ROOT) -> dict:
    blockers: list[str] = []
    if not _has_exact_keys(document, {"schema", "status", "policy", "principals", "materials", "scopes", "attestations"}):
        return {"valid": False, "blockers": ["register has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA or document["status"] not in {"provisional", "strict"}:
        return {"valid": False, "blockers": ["clean-room register schema or status mismatch"]}
    strict = document["status"] == "strict"
    policy = document["policy"]
    if not _has_exact_keys(policy, {"implementation_allowed", "implementation_forbidden"}):
        blockers.append("policy has unknown or missing fields")
        allowed: set[str] = set()
        forbidden: set[str] = set()
    else:
        allowed, forbidden = set(policy["implementation_allowed"]), set(policy["implementation_forbidden"])
        if allowed != IMPLEMENTATION_KINDS or not forbidden or allowed & forbidden or not (allowed | forbidden) <= MATERIAL_KINDS:
            blockers.append("policy implementation kinds are invalid")
    principals = _verify_principals(document["principals"], blockers)
    materials = _verify_materials(document["materials"], root, blockers)
    scopes_value = document["scopes"]
    scopes: dict[str, dict] = {}
    if not isinstance(scopes_value, list):
        blockers.append("scopes must be a list")
    else:
        for scope in scopes_value:
            if not _has_exact_keys(scope, {"id", "paths", "state", "role_material_allowlists"}):
                blockers.append("scope has unknown or missing fields")
                continue
            scope_id = scope["id"]
            if not isinstance(scope_id, str) or not scope_id or scope_id in scopes:
                blockers.append(f"invalid or duplicate scope id: {scope_id!r}")
                continue
            if not isinstance(scope["paths"], list) or not scope["paths"] or not all(_safe_glob(path) for path in scope["paths"]):
                blockers.append(f"{scope_id}: invalid scope paths")
            if scope["state"] not in STATES:
                blockers.append(f"{scope_id}: invalid scope state")
            allowlists = scope["role_material_allowlists"]
            if not isinstance(allowlists, dict) or set(allowlists) != {"observer", "spec_author", "implementer", "comparator", "auditor"}:
                blockers.append(f"{scope_id}: invalid role_material_allowlists")
            else:
                for role, ids in allowlists.items():
                    if not isinstance(ids, list) or len(set(ids)) != len(ids) or not all(material_id in materials for material_id in ids):
                        blockers.append(f"{scope_id}: invalid {role} allowlist")
                    for material_id in ids:
                        material = materials.get(material_id)
                        if material is not None and role not in material["allowed_roles"]:
                            blockers.append(f"{scope_id}: {role} cannot consume {material_id}")
                for material_id in allowlists.get("implementer", []):
                    for ancestor in _material_closure(material_id, materials, set(), blockers):
                        if materials[ancestor]["kind"] not in allowed:
                            blockers.append(f"{scope_id}: implementer allowlist contains forbidden ancestor {ancestor}")
            scopes[scope_id] = scope
    phases_by_scope = _verify_attestations(document["attestations"], scopes, principals, materials, strict, blockers)
    for scope_id, scope in scopes.items():
        required_phases = {phase for phase in PHASES if STATES[phase] <= STATES.get(scope["state"], -1)}
        missing = required_phases - phases_by_scope.get(scope_id, set())
        if missing:
            blockers.append(f"{scope_id}: missing required attestations {sorted(missing)}")
    if strict:
        observer_ids = {principal_id for principal_id, principal in principals.items() if "observer" in principal["roles"]}
        implementer_ids = {principal_id for principal_id, principal in principals.items() if "implementer" in principal["roles"]}
        if observer_ids & implementer_ids:
            blockers.append("strict mode requires observer and implementer principal separation")
    if release:
        blockers.append("clean-room register v1 cannot authorize a release")
        if document["status"] != "strict":
            blockers.append("release requires strict clean-room registry")
        if any(scope["state"] != "release_eligible" for scope in scopes.values()):
            blockers.append("release requires every scope to be release_eligible")
    return {
        "valid": not blockers,
        "status": document["status"],
        "scope_count": len(scopes),
        "material_count": len(materials),
        "attestation_count": len(document["attestations"]) if isinstance(document["attestations"], list) else 0,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=ROOT / "clean-room-register.v1.yaml")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        report = verify_document(_load_document(args.registry), release=args.release)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
