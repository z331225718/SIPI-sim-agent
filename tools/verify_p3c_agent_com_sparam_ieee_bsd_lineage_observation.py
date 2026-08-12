"""Verify the selective IEEE 802-COM BSD-3-Clause S-parameter lineage record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p3c.agent-com-sparam-ieee-bsd-lineage-observation.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p3c-agent-com-sparam-ieee-bsd-lineage-observation.v1.yaml"
AGENT_ORIGIN = "https://github.com/z331225718/agent-com.git"
AGENT_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
AGENT_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
IEEE_ORIGIN = "https://opensource.ieee.org/802-com/com_code.git"
IEEE_COMMIT = "d4ecd4597a98782887933b5df4c4796da2474195"
IEEE_TREE = "e0f5ccbee1421a06a2e201622cdeb70e3b1d9760"


class LineageError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    if result.returncode:
        raise LineageError("git_object_unavailable")
    return result.stdout


def _text(root: Path, *args: str) -> str:
    return _git(root, *args).decode("utf-8").strip()


def _verify_repo(root: Path, origin: str, commit: str, tree: str) -> None:
    if _text(root, "config", "--get", "remote.origin.url") != origin:
        raise LineageError("canonical_origin_mismatch")
    if _text(root, "rev-parse", "--show-object-format") != "sha1":
        raise LineageError("object_format_mismatch")
    if _text(root, "status", "--porcelain"):
        raise LineageError("source_worktree_not_clean")
    if _text(root, "rev-parse", "HEAD") != commit or _text(root, "rev-parse", f"{commit}^{{tree}}") != tree:
        raise LineageError("source_identity_mismatch")


def _blob(root: Path, commit: str, path: str) -> tuple[str, bytes]:
    return _text(root, "rev-parse", f"{commit}:{path}"), _git(root, "cat-file", "blob", f"{commit}:{path}")


def _expected() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "selective_upstream_bsd3_source_input_observed_direct_port_implementation_pending",
        "authority": {
            "actor": "user",
            "decision_ref": "user-authorized-2026-08-12-ieee8023-gitlab-provenance-and-selective-mixed-license-direct-port",
            "direct_port_implementation_started": False,
            "product_policy_selected": False,
            "release_admitted": False,
        },
        "agent_com_source": {
            "canonical_origin": AGENT_ORIGIN,
            "commit": AGENT_COMMIT,
            "tree": AGENT_TREE,
            "root_license_spdx": "MIT",
        },
        "ieee_802_com_source": {
            "canonical_origin": IEEE_ORIGIN,
            "commit": IEEE_COMMIT,
            "tree": IEEE_TREE,
            "object_format": "sha1",
            "root_license": {
                "path": "LICENSE", "git_blob": "0d136a232fee2359fb9e2fc03c2b86baf99c6b06", "byte_length": 1516,
                "content_sha256": "f5532297b5eeef9ef3236a38ecb5973d6521b542f567db15c4025e1f71d91631",
                "observed_spdx": "BSD-3-Clause", "copyright_marker": "Copyright (c) 2025, 802-COM Authors",
            },
        },
        "paths": [
            {
                "agent_com": {"path": "src/agent_com/signal/interpolation.py", "git_blob": "87898d999ec20ac8f531bba72efbbd83d9e43d43", "content_sha256": "eab64c2f260778f468cef50b102749919704420d22914c1302a22a8b94da5a5b", "lineage_marker": "Port `interp_Sparam` (r4.80 source lines 6319--6515)"},
                "ieee_802_com": {"path": "src/interp_Sparam.m", "git_blob": "85b52ff25dbb5bb91f032a03d7cdd311e33af432", "byte_length": 10085, "content_sha256": "259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27", "required_markers": ["SPDX-License-Identifier: BSD-3-Clause", "Copyright 2025 802-COM Authors", "function [Sout] = interp_Sparam"]},
                "source_input_status": "admitted_bsd3_notice_and_product_policy_pending",
            },
            {
                "agent_com": {"path": "src/agent_com/signal/fd_to_td.py", "git_blob": "6f3af024ea20df0011843ea19a090788f1aabbc9", "content_sha256": "703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687", "lineage_marker": "Port `s21_to_impulse_DC` (r4.80 source lines 10091--10160)"},
                "ieee_802_com": {"path": "src/s21_to_impulse_DC.m", "git_blob": "f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3", "byte_length": 4208, "content_sha256": "b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0", "required_markers": ["SPDX-License-Identifier: BSD-3-Clause", "Copyright 2025 802-COM Authors", "function [voltage, t_base, causality_correction_dB, truncation_dB]"]},
                "source_input_status": "admitted_bsd3_notice_and_product_policy_pending",
            },
            {
                "agent_com": {"path": "src/agent_com/signal/causality.py", "git_blob": "13555c329187385f4c8bc610c1ce62cc89acac6c", "content_sha256": "d9c75b356a053f1e68d81ffd4c979f9f8746a76c509840ff29aac4a759a917f7", "lineage_marker": "Minimum-phase causality correction and delay estimation from r4.80."},
                "ieee_802_com": {"path": "src/calculate_delay_CausalityEnforcement.m", "git_blob": "6b2dcb7d83f0dbf48e749e5200850fffea73791e", "byte_length": 7395, "content_sha256": "a74fcd1724109c9e25b21deb4f6c308994ef21a1422503c2e5c2a755050e8823", "required_markers": ["SPDX-License-Identifier: BSD-3-Clause", "Copyright 2025 802-COM Authors", "function [delay_sec, delay_idx]= calculate_delay_CausalityEnforcement"]},
                "source_input_status": "blocked_named_author_chain_confirmation_pending",
            },
        ],
        "required_before_implementation": ["dedicated_rust_implementation_scope_with_exact_source_binding", "source_specific_spdx_notice_and_sbom_entries", "product_sparameter_policy_selected_independently", "translated_dependency_closure_reviewed", "release_archive_license_admission"],
        "blockers": ["direct_port_implementation_not_started", "product_sparameter_policy_not_selected", "translated_dependency_closure_and_notice_plan_missing", "causality_named_author_chain_confirmation_missing", "p5_authoritative_r480_reference_missing"],
        "non_claims": [
            "IEEE standards, meeting material, and the Agent-COM root MIT license are not used as a code relicensing grant.",
            "The observed path pairing is provenance evidence only and does not claim semantic or output equivalence.",
            "This record admits neither a general Agent-COM import nor PyBERT, PyAMI, MATLAB, workbook, fixture, or oracle material.",
            "No candidate execution, P5 authoritative reference, receiver acceptance, ADS or AMI runtime, source-drift repair, or release promotion is evaluated.",
        ],
    }


def _verify_external(agent_root: Path, ieee_root: Path, expected: dict[str, Any]) -> None:
    _verify_repo(agent_root, AGENT_ORIGIN, AGENT_COMMIT, AGENT_TREE)
    _verify_repo(ieee_root, IEEE_ORIGIN, IEEE_COMMIT, IEEE_TREE)
    license_data = expected["ieee_802_com_source"]["root_license"]
    blob, raw = _blob(ieee_root, IEEE_COMMIT, license_data["path"])
    if blob != license_data["git_blob"] or len(raw) != license_data["byte_length"] or hashlib.sha256(raw).hexdigest() != license_data["content_sha256"] or b"BSD 3-Clause License" not in raw or license_data["copyright_marker"].encode() not in raw:
        raise LineageError("ieee_root_license_identity_mismatch")
    for item in expected["paths"]:
        agent = item["agent_com"]
        blob, raw = _blob(agent_root, AGENT_COMMIT, agent["path"])
        if blob != agent["git_blob"] or hashlib.sha256(raw).hexdigest() != agent["content_sha256"] or agent["lineage_marker"].encode() not in raw:
            raise LineageError("agent_path_identity_or_marker_mismatch")
        upstream = item["ieee_802_com"]
        blob, raw = _blob(ieee_root, IEEE_COMMIT, upstream["path"])
        if blob != upstream["git_blob"] or len(raw) != upstream["byte_length"] or hashlib.sha256(raw).hexdigest() != upstream["content_sha256"] or any(marker.encode() not in raw for marker in upstream["required_markers"]):
            raise LineageError("ieee_path_identity_or_notice_mismatch")


def verify_document(document: object, agent_root: Path | None = None, ieee_root: Path | None = None) -> dict[str, Any]:
    expected = _expected()
    if document != expected:
        raise LineageError("manifest_identity_or_gate_mismatch")
    if (agent_root is None) != (ieee_root is None):
        raise LineageError("both_external_roots_required")
    if agent_root is not None and ieee_root is not None:
        _verify_external(agent_root, ieee_root, expected)
    return {"schema": SCHEMA, "status": expected["status"], "admitted_source_input_count": 2, "blocked_source_input_count": 1, "direct_port_implementation_started": False, "release_admitted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--agent-com-root", type=Path)
    parser.add_argument("--ieee-com-root", type=Path)
    args = parser.parse_args()
    try:
        report = verify_document(yaml.safe_load(args.manifest.read_text(encoding="utf-8")), args.agent_com_root, args.ieee_com_root)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, LineageError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] != "rejected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
