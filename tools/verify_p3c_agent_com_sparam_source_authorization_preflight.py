"""Verify the fail-closed, per-path Agent-COM S-parameter source review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p3c.agent-com-sparam-source-authorization-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p3c-agent-com-sparam-source-authorization-preflight.v1.yaml"
ORIGIN = "https://github.com/z331225718/agent-com.git"
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
ROOT_LICENSE = {
    "path": "LICENSE",
    "git_blob": "55aac2e4f8c36a978d315efb02815972579b8293",
    "content_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2",
    "observed_spdx": "MIT",
}
CANDIDATES = (
    {
        "path": "src/agent_com/signal/interpolation.py",
        "git_blob": "87898d999ec20ac8f531bba72efbbd83d9e43d43",
        "byte_length": 8693,
        "content_sha256": "eab64c2f260778f468cef50b102749919704420d22914c1302a22a8b94da5a5b",
        "declared_lineage_markers": ("Port `interp_Sparam` (r4.80 source lines 6319--6515)",),
        "direct_imports": ("numpy", "agent_com.compat", "agent_com.errors"),
    },
    {
        "path": "src/agent_com/signal/fd_to_td.py",
        "git_blob": "6f3af024ea20df0011843ea19a090788f1aabbc9",
        "byte_length": 5831,
        "content_sha256": "703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687",
        "declared_lineage_markers": ("Port `s21_to_impulse_DC` (r4.80 source lines 10091--10160)",),
        "direct_imports": ("numpy", "agent_com.errors", "agent_com.runtime", "agent_com.signal.interpolation"),
    },
    {
        "path": "src/agent_com/signal/causality.py",
        "git_blob": "13555c329187385f4c8bc610c1ce62cc89acac6c",
        "byte_length": 3809,
        "content_sha256": "d9c75b356a053f1e68d81ffd4c979f9f8746a76c509840ff29aac4a759a917f7",
        "declared_lineage_markers": (
            "Minimum-phase causality correction and delay estimation from r4.80.",
            "Preserve the source's self-difference bug for the R480 profile.",
        ),
        "direct_imports": ("numpy", "agent_com.errors", "agent_com.signal.fd_to_td", "agent_com.signal.interpolation"),
    },
)
BLOCKERS = (
    "upstream_provenance_and_relicensing_rights_not_independently_confirmed",
    "per_path_notice_and_attribution_decisions_missing",
    "translated_dependency_closure_and_notice_plan_missing",
    "product_sparameter_policy_not_selected",
    "p5_authoritative_r480_reference_missing",
)


class PreflightError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    if completed.returncode:
        raise PreflightError("git_object_unavailable")
    return completed.stdout


def _git_text(root: Path, *args: str) -> str:
    return _git(root, *args).decode("utf-8").strip()


def _source_identity(root: Path) -> None:
    if _git_text(root, "config", "--get", "remote.origin.url") != ORIGIN:
        raise PreflightError("canonical_origin_mismatch")
    if _git_text(root, "rev-parse", "--show-object-format") != "sha1":
        raise PreflightError("object_format_mismatch")
    if _git_text(root, "status", "--porcelain"):
        raise PreflightError("source_worktree_not_clean")
    if _git_text(root, "rev-parse", "HEAD") != COMMIT or _git_text(root, "rev-parse", f"{COMMIT}^{{tree}}") != TREE:
        raise PreflightError("source_identity_mismatch")


def _blob(root: Path, path: str) -> tuple[str, bytes]:
    blob = _git_text(root, "rev-parse", f"{COMMIT}:{path}")
    return blob, _git(root, "cat-file", "blob", f"{COMMIT}:{path}")


def materialize_preflight(source_root: Path) -> dict[str, Any]:
    _source_identity(source_root)
    license_blob, license_bytes = _blob(source_root, ROOT_LICENSE["path"])
    if license_blob != ROOT_LICENSE["git_blob"] or hashlib.sha256(license_bytes).hexdigest() != ROOT_LICENSE["content_sha256"] or b"MIT License" not in license_bytes:
        raise PreflightError("root_license_identity_mismatch")
    candidates: list[dict[str, Any]] = []
    for expected in CANDIDATES:
        blob, content = _blob(source_root, expected["path"])
        if blob != expected["git_blob"] or len(content) != expected["byte_length"] or hashlib.sha256(content).hexdigest() != expected["content_sha256"]:
            raise PreflightError("candidate_identity_mismatch")
        text = content.decode("utf-8")
        if any(marker not in text for marker in expected["declared_lineage_markers"]):
            raise PreflightError("candidate_lineage_marker_missing")
        candidates.append({
            **expected,
            "declared_lineage_markers": list(expected["declared_lineage_markers"]),
            "direct_imports": list(expected["direct_imports"]),
            "review_status": "blocked_declared_r480_lineage_requires_upstream_provenance",
        })
    return {
        "schema": SCHEMA,
        "status": "per_path_static_review_observed_direct_port_blocked",
        "authority": {
            "actor": "user",
            "decision_ref": "user-authorized-2026-08-12-agent-com-sparam-per-path-audit",
            "conditional_mode": "direct_licensed_port_mixed_license_after_admission",
            "direct_port_admitted": False,
        },
        "source": {"canonical_origin": ORIGIN, "commit": COMMIT, "tree": TREE, "object_format": "sha1", "root_license": ROOT_LICENSE},
        "candidates": candidates,
        "review_requirements": {
            "per_path": ["upstream_provenance", "copyright_holder", "relicensing_right", "exact_spdx", "notice_attribution", "dependency_closure", "distribution_scope"],
            "product_policy": ["complex_interpolation", "dc_policy", "out_of_band_policy", "hermitian_ifft_scaling", "delay_policy", "causality_policy", "passivity_policy", "impulse_truncation", "linear_convolution"],
            "excluded_material": ["matlab_src", "workbooks", "fixtures", "benchmarks", "oracle_outputs", "matlab_runtime"],
        },
        "blockers": list(BLOCKERS),
        "non_claims": [
            "Root MIT evidence and the owner authorization do not by themselves admit a direct port or a release input.",
            "This static review does not execute agent-com, MATLAB, PyBERT, PyAMI, ADS, or any oracle.",
            "This record does not choose interpolation, DC, out-of-band, delay, causality, passivity, IFFT, truncation, or convolution semantics.",
            "Historical rational rejection, source drift, P5 reference blocking, and release fail-closed gates remain unchanged.",
        ],
    }


def verify_document(document: object, source_root: Path | None = None) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {"schema", "status", "authority", "source", "candidates", "review_requirements", "blockers", "non_claims"}:
        raise PreflightError("manifest_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "per_path_static_review_observed_direct_port_blocked":
        raise PreflightError("manifest_status_invalid")
    if source_root is not None:
        expected = materialize_preflight(source_root)
    else:
        expected = materialize_preflight_fields()
    if document != expected:
        raise PreflightError("manifest_identity_or_gate_mismatch")
    return {"schema": SCHEMA, "status": "per_path_static_review_observed_direct_port_blocked", "candidate_count": len(CANDIDATES), "direct_port_admitted": False, "blocker_count": len(BLOCKERS)}


def materialize_preflight_fields() -> dict[str, Any]:
    candidates = []
    for expected in CANDIDATES:
        candidates.append({**expected, "declared_lineage_markers": list(expected["declared_lineage_markers"]), "direct_imports": list(expected["direct_imports"]), "review_status": "blocked_declared_r480_lineage_requires_upstream_provenance"})
    return {
        "schema": SCHEMA,
        "status": "per_path_static_review_observed_direct_port_blocked",
        "authority": {"actor": "user", "decision_ref": "user-authorized-2026-08-12-agent-com-sparam-per-path-audit", "conditional_mode": "direct_licensed_port_mixed_license_after_admission", "direct_port_admitted": False},
        "source": {"canonical_origin": ORIGIN, "commit": COMMIT, "tree": TREE, "object_format": "sha1", "root_license": ROOT_LICENSE},
        "candidates": candidates,
        "review_requirements": {
            "per_path": ["upstream_provenance", "copyright_holder", "relicensing_right", "exact_spdx", "notice_attribution", "dependency_closure", "distribution_scope"],
            "product_policy": ["complex_interpolation", "dc_policy", "out_of_band_policy", "hermitian_ifft_scaling", "delay_policy", "causality_policy", "passivity_policy", "impulse_truncation", "linear_convolution"],
            "excluded_material": ["matlab_src", "workbooks", "fixtures", "benchmarks", "oracle_outputs", "matlab_runtime"],
        },
        "blockers": list(BLOCKERS),
        "non_claims": [
            "Root MIT evidence and the owner authorization do not by themselves admit a direct port or a release input.",
            "This static review does not execute agent-com, MATLAB, PyBERT, PyAMI, ADS, or any oracle.",
            "This record does not choose interpolation, DC, out-of-band, delay, causality, passivity, IFFT, truncation, or convolution semantics.",
            "Historical rational rejection, source drift, P5 reference blocking, and release fail-closed gates remain unchanged.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path)
    arguments = parser.parse_args()
    try:
        document = yaml.safe_load(arguments.manifest.read_text(encoding="utf-8"))
        report = verify_document(document, arguments.source_root)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, PreflightError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
