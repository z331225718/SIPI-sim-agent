"""Machine-verify license-manifest.v1.yaml authorization transitions.

Rules (matching the manifest's own reject policy):
  - any subject with distribution_status other than ``blocked_unknown`` must
    have non-empty evidence_refs, a resolved license_decision_owner, a
    compliance state other than ``blocked``, and an updated status_reason;
  - ``authorized_public`` additionally requires an explicit license
    declaration and an authorized/complete compliance state;
  - evidence file hashes must match the repository files;
  - a subject listed in open_authorizations cannot already be authorized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_STATES = {"authorized_public", "authorized_private", "external_reference_only"}
COMPLIANCE_OK = {"authorized", "complete"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _verify_evidence(refs: list, root: Path, blockers: list[str], subject_id: str) -> None:
    for ref in refs:
        if not isinstance(ref, dict):
            blockers.append(f"{subject_id}: malformed evidence_ref")
            continue
        path = root / str(ref.get("path", ""))
        if not path.is_file():
            blockers.append(f"{subject_id}: evidence file missing: {ref.get('path')}")
            continue
        expected = ref.get("sha256")
        if isinstance(expected, str) and expected.upper() != _sha256(path):
            blockers.append(f"{subject_id}: evidence hash mismatch: {ref.get('path')}")


def verify(manifest_text: str, root: Path) -> dict:
    blockers: list[str] = []
    if yaml is None:
        return {"valid": False, "blockers": ["pyyaml is unavailable"]}
    try:
        document = yaml.safe_load(manifest_text)
    except Exception as error:  # noqa: BLE001
        return {"valid": False, "blockers": [f"manifest unparsable: {error}"]}
    if not isinstance(document, dict) or document.get("schema") != "sipi.license-manifest.v1":
        return {"valid": False, "blockers": ["manifest schema mismatch"]}
    subjects = document.get("subjects")
    if not isinstance(subjects, list):
        return {"valid": False, "blockers": ["manifest missing subjects"]}
    authorized_ids = set()
    for subject in subjects:
        subject_id = subject.get("id", "<unknown>")
        status = subject.get("distribution_status")
        if status == "blocked_unknown":
            continue
        if status not in AUTHORIZED_STATES:
            blockers.append(f"{subject_id}: unknown distribution_status {status!r}")
            continue
        authorized_ids.add(subject_id)
        evidence = subject.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            blockers.append(f"{subject_id}: authorized status requires evidence_refs")
        else:
            _verify_evidence(evidence, root, blockers, subject_id)
        decision_owner = subject.get("owners", {}).get("license_decision_owner")
        if decision_owner in {None, "pending_external_authorization"}:
            blockers.append(f"{subject_id}: license_decision_owner is unresolved")
        compliance = subject.get("compliance") or {}
        if compliance.get("state") == "blocked":
            blockers.append(f"{subject_id}: compliance is blocked")
        reason = subject.get("status_reason")
        if not isinstance(reason, str) or not reason:
            blockers.append(f"{subject_id}: status_reason must be updated")
        if status == "authorized_public":
            declaration = subject.get("license_declaration")
            if declaration in {None, "NOASSERTION"}:
                blockers.append(f"{subject_id}: authorized_public requires a license declaration")
            if compliance.get("state") not in COMPLIANCE_OK:
                blockers.append(f"{subject_id}: authorized_public requires authorized/complete compliance")
    for entry in document.get("open_authorizations", []) or []:
        if isinstance(entry, dict) and entry.get("subject_id") in authorized_ids:
            blockers.append(f"{entry['subject_id']}: listed in open_authorizations but already authorized")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "license-manifest.v1.yaml")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        text = args.manifest.read_text(encoding="utf-8")
    except OSError as error:
        print(f"license manifest unreadable: {error}", file=sys.stderr)
        return 2
    report = verify(text, args.root.resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
