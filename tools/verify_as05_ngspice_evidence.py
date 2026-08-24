"""Verifier for the additive AS-05 bounded external-runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_as05_ngspice_bound as single  # noqa: E402

MANIFEST_KEYS = {"schema", "status", "candidate", "upstream", "runner", "solver", "scope", "path_policy", "reports", "aggregate", "audit"}
AGGREGATE_KEYS = {"schema", "status", "scope", "path_policy", "candidate", "upstream", "runner", "solver", "toolchain", "build", "reports"}
AUDIT_KEYS = {"schema", "status", "candidate", "upstream", "aggregate", "reports", "scope", "non_claims"}
LINK_KEYS = {"path", "sha256"}
REPORT_KEYS = {"path", "sha256", "run_id", "fresh_run_nonce"}

# These are evidence-specific custody anchors, not caller-supplied policy.
# Keeping them here prevents a manifest from coordinating the verifier and
# artifacts around a different candidate or replay set.
EXPECTED_CANDIDATE = {
    "commit": "d10a136ded035fbcbeebf075fd68f0f9ab197652",
    "tree": "d8e2cded5ddd2ef1dc60b95764d7d08d88ba593c",
    "archive_sha256": "abcb30a71d9821356c317e04c8f7e72331a1081be7e6386a92cd5bb6edd47e73",
}
EXPECTED_UPSTREAM = {
    "commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
    "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402",
    "archive_sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144",
}
EXPECTED_RUNNER = {
    "path": "tools/run_as05_ngspice_bound.py",
    "sha256": "daae5b749c87d5a072c4ed7fec7fe91d27620fd09e7a57189c8448c474ac68f1",
}
EXPECTED_SOLVER_SHA256 = "86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453"
EXPECTED_REPORTS = [
    {
        "path": "docs\\baselines\\as-05-ngspice-scoped-observation-v2-run-1.json",
        "sha256": "fa38359bfc251cd91052e850a809f0c4dbedbdbf7c433aeb78147a82e11cbc77",
        "run_id": "as05-ngspice-v2-20260824-01",
        "fresh_run_nonce": "c3fa8e883f276bbf521f6189a46f079f69710a2098d6960bf504ebce390608d9",
    },
    {
        "path": "docs\\baselines\\as-05-ngspice-scoped-observation-v2-run-2.json",
        "sha256": "973f77b861125c75191e8fe7f0cd90bf58316bc9128a5df124ee04995d8142ac",
        "run_id": "as05-ngspice-v2-20260824-02",
        "fresh_run_nonce": "402f74bd2cd39fce92d475c8903a1bc6fba37b0eeaeb9c439ab165163a16984f",
    },
]
EXPECTED_AGGREGATE = {
    "path": "docs\\baselines\\as-05-ngspice-scoped-observation-v2-aggregate.json",
    "sha256": "8a62adfe8cd95477af980686e4abc3c845fff5248de97c0afd9315a8d0d66100",
}
EXPECTED_AUDIT = {
    "path": "docs\\baselines\\audits\\2026-08-24-as-05-ngspice-scoped-observation-v2.json",
    "sha256": "5a3cce0be10920eee9cc5312803c0118ed41ad2f868df6569a089b64668a2c67",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value or value.startswith("/") or value.startswith("\\") or ".." in value.replace("\\", "/").split("/"):
        return None
    path = ROOT / value.replace("\\", "/")
    return path if path.is_file() else None


def exact(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def verify_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    blockers: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "blockers": ["manifest type"]}
    if not exact(manifest, MANIFEST_KEYS) or manifest.get("schema") != "sipi.as-05-ngspice-scoped-observation.v2-manifest" or manifest.get("status") != "valid_scoped_external_runtime_observation_open":
        blockers.append("manifest schema/keys")
    if manifest.get("candidate") != EXPECTED_CANDIDATE:
        blockers.append("candidate custody anchor")
    if manifest.get("upstream") != EXPECTED_UPSTREAM:
        blockers.append("upstream custody anchor")
    if manifest.get("runner") != EXPECTED_RUNNER:
        blockers.append("runner custody anchor")
    solver = manifest.get("solver")
    if not isinstance(solver, dict) or solver.get("caller_sha256") != EXPECTED_SOLVER_SHA256:
        blockers.append("solver custody anchor")
    reports = manifest.get("reports")
    if not isinstance(reports, list) or len(reports) != 2 or any(not exact(item, REPORT_KEYS) for item in reports):
        blockers.append("report links")
        reports = []
    elif reports != EXPECTED_REPORTS:
        blockers.append("report custody anchors")
    report_docs: list[dict[str, Any]] = []
    report_paths: list[Path] = []
    for link in reports:
        path = repo_path(link.get("path")) if isinstance(link, dict) else None
        try:
            actual_digest = digest(path) if path is not None else None
        except OSError:
            actual_digest = None
        if path is None or actual_digest != link.get("sha256"):
            blockers.append("report path/hash")
            continue
        report = load_json(path)
        if not isinstance(report, dict):
            blockers.append("report JSON/type")
            continue
        report_paths.append(path)
        report_docs.append(report)
        if link.get("run_id") != report.get("run_id") or link.get("fresh_run_nonce") != report.get("fresh_run_nonce"):
            blockers.append("report freshness binding")
    if len({item.get("sha256") for item in reports}) != 2 or len({item.get("run_id") for item in reports}) != 2 or len({item.get("fresh_run_nonce") for item in reports}) != 2:
        blockers.append("fresh run distinctness")
    if len({item.get("run_id") for item in report_docs}) != len(report_docs) or len({item.get("fresh_run_nonce") for item in report_docs}) != len(report_docs):
        blockers.append("internal report freshness distinctness")
    if not report_docs:
        return {"valid": False, "blockers": blockers}
    first = report_docs[0]
    for report, path in zip(report_docs, report_paths):
        try:
            result = single.verify(report, candidate_commit=EXPECTED_CANDIDATE["commit"], candidate_tree=EXPECTED_CANDIDATE["tree"], candidate_archive_sha256=EXPECTED_CANDIDATE["archive_sha256"], upstream_archive_sha256=EXPECTED_UPSTREAM["archive_sha256"], solver_sha256=EXPECTED_SOLVER_SHA256, expected_runner_sha256=EXPECTED_RUNNER["sha256"], expected_report_sha256=digest(path), report_path=path)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, OSError):
            result = {"valid": False, "blockers": ["single report malformed"]}
        if not result["valid"]:
            blockers.extend(f"single report: {item}" for item in result["blockers"])
        # Fresh clean roots may produce different binary bytes (for example
        # linker metadata can contain the isolated build location).  The
        # replay binding requires identical tool/runtime provenance, while
        # each report independently attests its own execution binary.
        for key in ("candidate", "upstream", "runner", "solver", "toolchain", "scope", "path_policy"):
            if report.get(key) != first.get(key):
                blockers.append(f"cross-run {key}")
    aggregate_link = manifest.get("aggregate")
    audit_link = manifest.get("audit")
    if not exact(aggregate_link, LINK_KEYS) or not exact(audit_link, LINK_KEYS):
        blockers.append("aggregate/audit link keys")
        return {"valid": False, "blockers": blockers}
    if aggregate_link != EXPECTED_AGGREGATE or audit_link != EXPECTED_AUDIT:
        blockers.append("aggregate/audit custody anchors")
    aggregate_path = repo_path(aggregate_link.get("path"))
    audit_path = repo_path(audit_link.get("path"))
    try:
        aggregate_digest = digest(aggregate_path) if aggregate_path is not None else None
        audit_digest = digest(audit_path) if audit_path is not None else None
    except OSError:
        aggregate_digest = audit_digest = None
    if aggregate_path is None or aggregate_digest != aggregate_link.get("sha256"):
        blockers.append("aggregate path/hash")
    if audit_path is None or audit_digest != audit_link.get("sha256"):
        blockers.append("audit path/hash")
    if aggregate_path is not None:
        aggregate = load_json(aggregate_path)
        expected_aggregate = {key: first.get(key) for key in ("scope", "path_policy", "candidate", "upstream", "runner", "solver", "toolchain", "build")}
        if (
            not exact(aggregate, AGGREGATE_KEYS)
            or aggregate.get("schema") != "sipi.as-05-ngspice-scoped-observation.v2-aggregate"
            or aggregate.get("status") != "scoped_external_runtime_observation_open"
            or any(aggregate.get(key) != value for key, value in expected_aggregate.items())
        ):
            blockers.append("aggregate binding")
        if isinstance(aggregate, dict) and aggregate.get("reports") != reports:
            blockers.append("aggregate reports")
    if audit_path is not None:
        audit = load_json(audit_path)
        if (
            not exact(audit, AUDIT_KEYS)
            or audit.get("schema") != "sipi.as-05-ngspice-scoped-observation.v2-audit"
            or audit.get("status") != "scoped_external_runtime_observation_open"
            or audit.get("non_claims") != [
                "external_solver_not_verified",
                "numeric_parity_false",
                "no_as05_row_closure",
                "no_release_promotion",
                "environment_injection_not_fully_excluded",
            ]
            or audit.get("aggregate") != aggregate_link
            or audit.get("reports") != reports
            or audit.get("candidate") != first.get("candidate")
            or audit.get("upstream") != first.get("upstream")
            or audit.get("scope") != first.get("scope")
        ):
            blockers.append("audit binding")
    if manifest.get("candidate") != first.get("candidate") or manifest.get("upstream") != first.get("upstream") or manifest.get("runner") != first.get("runner") or manifest.get("solver") != first.get("solver") or manifest.get("scope") != first.get("scope") or manifest.get("path_policy") != first.get("path_policy"):
        blockers.append("manifest provenance")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    result = verify_manifest(load_json(path), path)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
