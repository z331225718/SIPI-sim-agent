"""Verify the deliberately local-scoped COM TDMODE observation."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

try:
    from verify_com_td_crosstalk_stage_replay_v1 import verify_aggregate, verify_manifest, verify_report_file
except ModuleNotFoundError:
    from tools.verify_com_td_crosstalk_stage_replay_v1 import verify_aggregate, verify_manifest, verify_report_file


class ScopeVerificationError(ValueError):
    pass


SCHEMA = "sipi.com.td-crosstalk-stage-replay.v1.scope-audit"
NON_CLAIMS = [
    "no portable or reproducible environment claim",
    "no full toolchain or full COM parity claim",
    "no release or promotion claim",
    "SciPy and complete Python environment are not bound",
]
SHIMS = {
    "cargo": ("cargo-wrap.exe", "cc24c1ed35681765b3d4823cc2e5d2e9c5d9214d38fc6ec62931af8b7db12d4d", "cargo.exe", "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7"),
    "linker": ("lld-wrap.exe", "6579a15ad16a23a5cc6217503041bd1b369f468f203e0aaa4337b895a115713c", "rust-lld.exe", "55bd23cee94c73c87de51106f60b63ad8981390aa7079c435c27fb5b04e283ad"),
    "uv": ("uv-wrap.exe", "3dcc13ab1c9ce13208f4d5ae03d8074e367a0437325a7f7ccb2a2c6af665691b", "uv.exe", "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68"),
}
SCOPE_GATE = {
    "verifier": ("tools/verify_com_td_crosstalk_stage_scope_v1.py",),
    "tests": ("tools/test_verify_com_td_crosstalk_stage_scope_v1.py",),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ScopeVerificationError("sha256")


def verify_scope(manifest: dict[str, Any], audit: dict[str, Any], reports: list[dict[str, Any]], aggregate: dict[str, Any]) -> None:
    if set(audit) != {"schema", "mode", "launcher_shims", "python_environment", "claims", "non_claims", "scope_gate"}:
        raise ScopeVerificationError("audit keys")
    if audit.get("schema") != SCHEMA or audit.get("mode") != "environment_local_scoped_observation":
        raise ScopeVerificationError("scope mode")
    if audit.get("non_claims") != NON_CLAIMS:
        raise ScopeVerificationError("non-claims")
    shims = audit.get("launcher_shims")
    if set(shims or {}) != set(SHIMS):
        raise ScopeVerificationError("shim roles")
    gate = audit.get("scope_gate")
    if set(gate or {}) != set(SCOPE_GATE):
        raise ScopeVerificationError("scope gate roles")
    for role, (path,) in SCOPE_GATE.items():
        item = gate[role]
        if set(item) != {"path", "sha256"} or item["path"] != path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ScopeVerificationError("scope gate path")
        _sha256(item["sha256"])
        if not Path(path).is_file() or _sha(Path(path)) != item["sha256"]:
            raise ScopeVerificationError("scope gate custody")
    for role, (basename, file_sha, delegated_basename, delegated_sha) in SHIMS.items():
        item = shims[role]
        if set(item) != {"wrapper_basename", "wrapper_sha256", "delegated_basename", "delegated_sha256", "receipt_managed"}:
            raise ScopeVerificationError("shim fields")
        if item["wrapper_basename"] != basename or item["wrapper_sha256"] != file_sha or item["delegated_basename"] != delegated_basename or item["delegated_sha256"] != delegated_sha or item["receipt_managed"] is not False:
            raise ScopeVerificationError("shim binding")
        _sha256(item["wrapper_sha256"])
        _sha256(item["delegated_sha256"])
    env = audit.get("python_environment")
    if env != {"venv_injected": True, "venv_path_policy": "external caller-supplied", "scipy_bound": False, "complete_environment_bound": False}:
        raise ScopeVerificationError("python environment")
    if audit.get("claims") != {"numeric_scope": "TDMODE crosstalk stage only", "status": "matched", "promotion": False}:
        raise ScopeVerificationError("claims")
    if set(manifest.get("audit", {})) != {"path", "sha256"}:
        raise ScopeVerificationError("manifest audit")
    audit_path = Path(manifest["audit"]["path"])
    _sha256(manifest["audit"]["sha256"])
    if not audit_path.is_file() or _sha(audit_path) != manifest["audit"]["sha256"]:
        raise ScopeVerificationError("audit custody")
    if len(reports) != 2 or aggregate.get("status") != "matched" or aggregate.get("matched") is not True:
        raise ScopeVerificationError("numeric observation")
    for report in reports:
        if report.get("status") != "matched" or report.get("parity", {}).get("matched") is not True or report.get("parity", {}).get("differences"):
            raise ScopeVerificationError("report parity")
        for role, (basename, file_sha, delegated_basename, delegated_sha) in SHIMS.items():
            tool = report.get("toolchain", {}).get(role, {})
            if tool.get("basename") != basename or tool.get("file_sha256") != file_sha:
                raise ScopeVerificationError("report shim binding")
        if report.get("execution", {}).get("uv_actual_execution") is not True:
            raise ScopeVerificationError("uv execution")


def verify_paths(manifest_path: Path, audit_path: Path, aggregate_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if audit_path.is_absolute() or ".." in audit_path.parts or audit_path.as_posix() != manifest.get("audit", {}).get("path"):
        raise ScopeVerificationError("audit path identity")
    if aggregate_path.is_absolute() or ".." in aggregate_path.parts or aggregate_path.as_posix() != manifest.get("aggregate", {}).get("path"):
        raise ScopeVerificationError("aggregate path identity")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    paths = [Path(path) for path in manifest["reports"]]
    reports = [verify_report_file(path, manifest) for path in paths]
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    verify_aggregate(aggregate, paths, reports, manifest, aggregate_path)
    verify_scope(manifest, audit, reports, aggregate)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    args = parser.parse_args()
    verify_paths(args.manifest, args.audit, args.aggregate)
    print(json.dumps({"verified": "environment_local_scoped_observation"}, sort_keys=True))
