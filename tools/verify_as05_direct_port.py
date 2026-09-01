"""Verify the AS-05 exact-source and direct-port admission record."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "as-05-run-hspice-direct-port.v1.yaml"
EXPECTED_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXPECTED_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
AUDIT_PATH = ROOT / "docs" / "baselines" / "audits" / "2026-08-22-as-05-run-hspice-direct-port.md"
EXPECTED_AUDIT_SHA256 = "3bbca46818ce9eb459cc261a7ee2a0f92ca60a1868731f49bd2b5f50223344de"
CRATE = ROOT / "crates" / "sipi-agent-spice-direct"
UPSTREAM_COMMIT_DECLARATION = re.compile(
    r'(?m)^pub const UPSTREAM_COMMIT: &str = "([0-9a-f]{40})";$'
)
EXPECTED_DIRECT_PORT_STATUS = "partial_admission_candidate"
EXPECTED_CORPUS = {
    "quoted_include_lib": "shlex_split_posix_false_path_tokens",
    "valid_current_pwl_repeat": "exact_ngspice_behavioral_rewrite_and_multiplicity",
    "invalid_current_pwl_repeat_point": "blocked_current_pwl_repeat_point_not_found",
    "invalid_current_pwl_repeat_window": "blocked_invalid_current_pwl_repeat_window",
    "four_backends_alter_missing_end": "all_backend_plans_ordered_alter_and_missing_end_preserved",
}
EXPECTED_MISSING_SEMANTICS = {
    "file_read_source_hash_stable_source_path_and_case_artifact_writes",
    "recursive_dependency_staging_and_missing_dependency_errors",
    "compat_report_json_deck_case_output_measure_and_summary_schema",
    "native_ngspice_xyce_and_xdm_process_execution_and_result_extraction",
    "backend_failure_exit_codes_and_two_stage_xdm_artifact_lifecycle",
    "included_netlist_current_pwl_rewrite_and_touchstone_preflight",
    "runtime_source_attestation_and_external_solver_identity",
}
SOURCE_PATHS = {
    "cli": ("src/agent_spice/cli.py", "321a32b860f969f0be74f883bedbbae3f67d6284", "908489c8c3a4826d49175c66b3d533413db4624b10fc3c797795b723b62262e1"),
    "hspice_alter": ("src/agent_spice/hspice/alter.py", "d162dc2a6c5a779625ae9fd736c35147b49fbebf", "5a18f537615b3276bb7c8b4d751e65e7dd21e17b1f5d3ab43d1fa732eb065bf4"),
    "hspice_audit": ("src/agent_spice/hspice/audit.py", "0651fe8a6ebc11423ceb9a55305b0cdf9dae2641", "47424952b248e7fadb64f8ad9f863f0213b484ae2ac87cc56798fa251c4aed82"),
    "hspice_converter": ("src/agent_spice/hspice/converter.py", "1bae09abf2cd52bff7c173311da9fee1458f3ca3", "b33596007cbaa435cc1527677661d6e94a3779c20fd84d8c7f2640e84723e7dd"),
    "hspice_manifest": ("src/agent_spice/hspice/manifest.py", "35d594ba7e5db9ab87f70abf562004b5ef876e51", "503fe6884614c5f0c5009535bad1e2f50642a15b398cf38ef667acf4a2458073"),
    "hspice_measure": ("src/agent_spice/hspice/measure.py", "215790e18f5cc013fbe51791086e3bce362a889a", "cbb851db87c951e1d3a76cc99f6d1bb9fc31a3c4c20234d25507cd85d71695f4"),
    "hspice_results": ("src/agent_spice/hspice/results.py", "360b48be3accf8ae455ad9542ad1fc0dcd782779", "e9d472e81de5083ba2ffe4631e5ee64114c42fbceda179b6eb686c58394e1cfe"),
    "backend_base": ("src/agent_spice/backend/base.py", "0faf79c29d4f65529de408ee7dd757e28bba7de0", "eada7c38a7a7700882582e5fd0746e1e1f7736c6ba038e4b6027932199136201"),
    "backend_native": ("src/agent_spice/backend/native.py", "4e2f327a9a10b8de876e83df1fb31c359ba063f4", "79b20cb1d172fe778be9fab260a9989f186159fd191b767bce8d9337466ddabc"),
    "backend_ngspice": ("src/agent_spice/backend/ngspice.py", "e9d1952bf1b43ad9a89bae95f1724b893e8db6b8", "eca6a855df25f44169d13f576f2c169596cfc6de29ef45c4829150d20b740672"),
    "backend_xyce": ("src/agent_spice/backend/xyce.py", "2e6af5fbaca426c47c677bd73175601914c9becc", "74809883b9a54eb0a6265bae054861b1a0b4f90a57609f22e2d660eb79efd53c"),
    "project": ("src/agent_spice/project.py", "ab3f36b0428f6f7a7b590e8907b7c0058a71c24c", "f145f204678bd5ffb283fe0261f99987e5a80499fb5f9d4369abb3272233d972"),
    "deck_builder": ("src/agent_spice/deck/builder.py", "52e41800c37ae3ce232a1ca65d331850c50930cf", "34e0b7c5ded6f1515b606083c138f7bd2571241eb84bbd5f2484c6a7e9fc3b91"),
    "native_engine_manifest": ("native/agent-spice-sim/Cargo.toml", "b56d29811d0293c878b22485523f03ea06dc2d91", "72c7296fdfee4627d65dc5cb5ba35ec09a4ecff47a34b16af034cd7d5817cf74"),
    "python_dependency_manifest": ("pyproject.toml", "29006b652445c770df4a01027357117adf9c95ad", "c0f8264a2de1375a4f40a8834173d49859dd9c4717d718fc5f622f1ea4f68c88"),
    "license": ("LICENSE", "55aac2e4f8c36a978d315efb02815972579b8293", "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"),
}
EXPECTED_BACKENDS = {"native", "ngspice", "xyce", "xyce_xdm"}
WORKFLOW_NAME = "run-hspice"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_blob(source: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(["git", "-C", str(source), "cat-file", "blob", f"{commit}:{path}"], check=True, capture_output=True)
    return result.stdout


def _is_root_workspace_member(crate: Path, root: Path) -> bool:
    """Accept the current root-workspace integration without claiming lane locality."""
    try:
        root_path = root.resolve(strict=True)
        crate_path = crate.resolve(strict=True)
        crate_path.relative_to(root_path)
        cargo = tomllib.loads((root_path / "Cargo.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return False
    workspace = cargo.get("workspace")
    if not isinstance(workspace, dict):
        return False
    members = workspace.get("members", [])
    if not isinstance(members, list):
        return False
    for member in members:
        if not isinstance(member, str):
            continue
        try:
            if (root_path / member).resolve(strict=True) == crate_path:
                return True
        except OSError:
            continue
    return False


def verify(document: dict[str, Any], source: Path | None = None, root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    crate_integration: str | None = None
    if document.get("schema") != "sipi.as-05-run-hspice-direct-port.v1":
        blockers.append("schema mismatch")
    if document.get("status") != EXPECTED_DIRECT_PORT_STATUS:
        blockers.append("partial admission status drift")
    source_data = document.get("source")
    if not isinstance(source_data, dict):
        blockers.append("source record missing")
    else:
        if source_data.get("repository") != "agent-spice":
            blockers.append("source repository mismatch")
        if source_data.get("commit") != EXPECTED_COMMIT:
            blockers.append("source commit drift")
        if source_data.get("tree") != EXPECTED_TREE:
            blockers.append("source tree drift")
        if source_data.get("license") != "MIT":
            blockers.append("source license is not MIT")
        if source_data.get("source_payload_copied_into_sipi") is not False:
            blockers.append("source payload copy policy drift")

    paths = document.get("source_paths")
    if not isinstance(paths, list) or {item.get("id") for item in paths if isinstance(item, dict)} != set(SOURCE_PATHS):
        blockers.append("source path inventory identity drift")
    else:
        for item in paths:
            expected = SOURCE_PATHS[item["id"]]
            if (item.get("path"), item.get("blob_oid"), item.get("sha256")) != expected:
                blockers.append(f"source binding drift: {item.get('id')}")
            if item.get("license") != "upstream_repo_mit" and item["id"] != "license":
                blockers.append(f"path license drift: {item.get('id')}")
            if item.get("copied") is not False:
                blockers.append(f"path copy policy drift: {item.get('id')}")

    direct = document.get("direct_port")
    if not isinstance(direct, dict) or direct.get("crate") != "crates/sipi-agent-spice-direct":
        blockers.append("direct-port crate identity drift")
    else:
        if direct.get("upstream_commit_constant") != EXPECTED_COMMIT:
            blockers.append("direct-port upstream commit evidence binding drift")
        if direct.get("copied_upstream_source") is not False:
            blockers.append("direct-port source copy policy drift")
        if direct.get("invokes_external_solver") is not False:
            blockers.append("admission model must not invoke external solver")
        if direct.get("numerical_implementation") != "absent_by_design":
            blockers.append("numerical implementation claim drift")
        if direct.get("covered_semantics") != [
            "bounded_deck_string_admission_and_ordered_alter_split",
            "quote_aware_shlex_posix_false_include_and_library_tokens",
            "ngspice_current_pwl_repeat_rewrite_and_rejection_reasons",
            "explicit_four_backend_prepare_and_execute_stage_plan",
        ]:
            blockers.append("covered semantic inventory drift")
        if set(direct.get("missing_semantics", [])) != EXPECTED_MISSING_SEMANTICS:
            blockers.append("missing semantic inventory drift")

    branch = document.get("branch_graph")
    backends = branch.get("backends") if isinstance(branch, dict) else None
    if not isinstance(backends, dict) or set(backends) != EXPECTED_BACKENDS:
        blockers.append("backend branch set drift")
    else:
        for name, record in backends.items():
            if not isinstance(record, dict) or not record.get("execute_false") or not record.get("execute_true"):
                blockers.append(f"backend branch is incomplete: {name}")
    preparation = branch.get("preparation") if isinstance(branch, dict) else None
    if not isinstance(preparation, dict) or preparation.get("required_case_artifacts") != ["case.cir", "case.source.sp", "compat_report.json"]:
        blockers.append("preparation artifact contract drift")

    oracle = document.get("oracle_replay")
    if not isinstance(oracle, dict):
        blockers.append("oracle replay record missing")
    else:
        if oracle.get("archive_commit") != EXPECTED_COMMIT:
            blockers.append("oracle archive commit drift")
        focused = oracle.get("focused_upstream_tests")
        if not isinstance(focused, dict) or focused.get("passed") != 52 or focused.get("failed") != 0:
            blockers.append("focused upstream test replay drift")
        prepare = oracle.get("prepare_only")
        if not isinstance(prepare, dict) or set(prepare) != EXPECTED_BACKENDS:
            blockers.append("prepare replay backend set drift")
        else:
            for backend, result in prepare.items():
                if result.get("exit") != 0 or result.get("cases") != 3:
                    blockers.append(f"prepare replay drift: {backend}")
        execute = oracle.get("execute")
        expected_exit = {"native": 0, "ngspice": 0, "xyce": 0, "xyce_xdm": 1}
        if not isinstance(execute, dict) or set(execute) != EXPECTED_BACKENDS:
            blockers.append("execute replay backend set drift")
        else:
            for backend, code in expected_exit.items():
                if execute[backend].get("exit") != code:
                    blockers.append(f"execute replay exit drift: {backend}")
        tolerance = oracle.get("replay_tolerance")
        if not isinstance(tolerance, dict) or tolerance.get("prepared_case_text") != "byte_exact" or tolerance.get("compat_report") != "byte_exact_for_frozen_fixture" or tolerance.get("numeric_waveforms") != "not_frozen_until_rust_solver_port":
            blockers.append("replay tolerance policy drift")

    corpus = document.get("differential_corpus")
    if not isinstance(corpus, dict) or corpus.get("status") != "pinned_rust_unit_corpus":
        blockers.append("differential corpus status drift")
    else:
        cases = corpus.get("cases")
        actual_corpus = {
            item.get("id"): item.get("expectation")
            for item in cases
            if isinstance(item, dict)
        } if isinstance(cases, list) else {}
        if actual_corpus != EXPECTED_CORPUS:
            blockers.append("differential corpus inventory drift")

    audit = document.get("audit")
    audit_relative_path = AUDIT_PATH.relative_to(root).as_posix()
    if not isinstance(audit, dict) or audit.get("path") != audit_relative_path or audit.get("sha256") != EXPECTED_AUDIT_SHA256:
        blockers.append("audit binding drift")
    elif not AUDIT_PATH.is_file() or _sha256(AUDIT_PATH.read_bytes()) != EXPECTED_AUDIT_SHA256:
        blockers.append("audit content hash drift")

    cargo_path = CRATE / "Cargo.toml"
    source_path = CRATE / "src" / "lib.rs"
    if not cargo_path.is_file() or not source_path.is_file():
        blockers.append("direct-port crate files missing")
    else:
        try:
            cargo = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            cargo = {}
            blockers.append("direct-port Cargo.toml is invalid")
        package = cargo.get("package", {})
        if package.get("name") != "sipi-agent-spice-direct" or package.get("license") != "MIT":
            blockers.append("direct-port package identity/license drift")
        # This record predates root-workspace integration.  Accept either the
        # historical nested workspace or the current explicit root member, but
        # never turn that packaging fact into a solver/parity claim.
        if "workspace" in cargo:
            crate_integration = "lane_local_workspace"
        elif _is_root_workspace_member(CRATE, root):
            crate_integration = "root_workspace_member"
        else:
            blockers.append("direct-port crate is neither lane-local nor a root-workspace member")
        code = source_path.read_text(encoding="utf-8")
        commit_match = UPSTREAM_COMMIT_DECLARATION.search(code)
        if commit_match is None or commit_match.group(1) != EXPECTED_COMMIT:
            blockers.append("direct-port Rust upstream commit constant drift")
        elif isinstance(direct, dict) and commit_match.group(1) != direct.get("upstream_commit_constant"):
            blockers.append("direct-port Rust/evidence commit binding drift")
        for marker in (
            "admit_run_hspice",
            "split_alter_cases",
            "audit_deck",
            "rewrite_current_pwl_repeats_for_ngspice",
            "UnsupportedIssue",
            "ExecutionStage",
            "Backend::XyceXdm",
            "ParityStatus::NotEvaluated",
        ):
            if marker not in code:
                blockers.append(f"direct-port marker missing: {marker}")
        if "alter_label" in code:
            blockers.append("non-upstream alter_label field remains")
        notice_path = CRATE / "NOTICE-AGENT-SPICE-MIT.md"
        if not notice_path.is_file():
            blockers.append("direct-port MIT notice missing")
        else:
            notice = notice_path.read_text(encoding="utf-8")
            for marker in (EXPECTED_COMMIT, EXPECTED_TREE, "Copyright (c) 2026 z331225718", "MIT"):
                if marker not in notice:
                    blockers.append(f"direct-port MIT notice marker missing: {marker}")

    source_checked = False
    if source is not None:
        try:
            commit = _git(source, "rev-parse", "HEAD")
            tree = _git(source, "rev-parse", f"{commit}^{{tree}}")
            if commit != EXPECTED_COMMIT:
                blockers.append("source checkout commit drift")
            if tree != EXPECTED_TREE:
                blockers.append("source checkout tree drift")
            for path, blob_oid, sha256 in SOURCE_PATHS.values():
                actual_oid = _git(source, "rev-parse", f"{commit}:{path}")
                actual_sha = _sha256(_git_blob(source, commit, path))
                if actual_oid != blob_oid or actual_sha != sha256:
                    blockers.append(f"Git object drift: {path}")
            source_checked = True
        except (OSError, subprocess.CalledProcessError):
            blockers.append("explicit source Git object cannot be checked")

    return {
        "valid": not blockers,
        "status": document.get("status"),
        "workflow": WORKFLOW_NAME,
        "crate_integration": crate_integration,
        "source_git_objects_checked": source_checked,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
    result = verify(document, source=args.source)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("valid" if result["valid"] else "blocked")
        for blocker in result["blockers"]:
            print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
