"""Validate the immutable, non-formal TP0V v4 acceptance-preparation gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v4.yaml"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_SCHEMA = "sipi.com.tp0v-current-asset-scoped-acceptance-prep.v4"
EXPECTED_ASSET_ROLES = ["THRU", "FEXT", "NEXT"]
EXPECTED_VECTOR_NAMES = ["time_s", "impedance_ohm", "ptdr", "gated"]
EXPECTED_TRANSFORMS = ["alignment", "resampling", "interpolation", "truncation", "delay_correction"]
EXPECTED_REPLAYS = ["matlab-01", "matlab-02", "rust-01", "rust-02"]
EXPECTED_FORMAL_PATHS = [
    "docs/baselines/com-tp0v-current-asset-r2024b-matlab-01.v4.json",
    "docs/baselines/com-tp0v-current-asset-r2024b-matlab-02.v4.json",
    "docs/baselines/com-tp0v-current-asset-r2024b-rust-01.v4.json",
    "docs/baselines/com-tp0v-current-asset-r2024b-rust-02.v4.json",
    "docs/baselines/com-tp0v-current-asset-r2024b-aggregate.v4.json",
]
EXPECTED_TOOLS = {
    "runner": "tools/run_com_tp0v_r2024b_v4_replay.py",
    "aggregate": "tools/aggregate_com_tp0v_r2024b_v4_replay.py",
    "verifier": "tools/verify_com_tp0v_r2024b_v4_prep.py",
    "tests": "tools/test_verify_com_tp0v_r2024b_v4_prep.py",
    "runner_tests": "tools/test_run_com_tp0v_r2024b_v4_replay.py",
    "aggregate_tests": "tools/test_aggregate_com_tp0v_r2024b_v4_replay.py",
    "trace_support": "tools/run_com_normal_erl_trace_diagnostic.py",
    "trace_wrapper": "tools/sipi_com_normal_erl_trace_run_v1.m",
    "trace_sink": "tools/sipi_com_normal_erl_trace_sink_v1.m",
    "audit": "docs/baselines/audits/2026-09-02-com-tp0v-r2024b-v4-prep.md",
}
EXPECTED_CANDIDATE = {
    "commit": "b255967c91898f720a16e5029af09521f94fa7df",
    "tree": "849fc6c1ba682f3302bb4eb1c9c701e8aec6e53e",
    "archive_sha256": "f5a096653d89b79989834fb253438b0a0d63e722638e14ad1e3cd528e61d1930",
    "archive_bytes": 62033920,
}
EXPECTED_CANDIDATE_GATE_PARENT = {
    "commit": "90bf1a92f699a61511a0bf9b34f3f7038f30df8b",
    "tree": "849fc6c1ba682f3302bb4eb1c9c701e8aec6e53e",
}
EXPECTED_UPSTREAM = {
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    "archive_bytes": 43694080,
    "workbook": {
        "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA _TP0V_08_17_2022.xlsx",
        "bytes": 67151,
        "sha256": "54562fa2bbe856f1fb6e96b7c1c873d2b399555b1fb38e50cd6f4ad3ddc69f0a",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_repo_path(value: Any, label: str) -> Path:
    require(isinstance(value, str) and value and "\\" not in value, f"{label}: path")
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts, f"{label}: unsafe path")
    resolved = (ROOT / path).resolve()
    require(resolved == ROOT or ROOT in resolved.parents, f"{label}: path escape")
    return resolved


def _exact_asset_contract(assets: Any) -> None:
    require(isinstance(assets, list) and [item.get("role") for item in assets] == EXPECTED_ASSET_ROLES, "asset role/order")
    for asset in assets:
        require(set(asset) == {"role", "path", "bytes", "sha256", "header", "port_order"}, "asset keyset")
        require(asset["header"] == "# Hz S RI R 50.0" and asset["port_order"] == [1, 2, 3, 4], "asset format contract")
        require(isinstance(asset["bytes"], int) and asset["bytes"] > 0 and SHA_RE.fullmatch(asset["sha256"]), "asset receipt")
        _safe_repo_path(asset["path"], f"asset {asset['role']}")


def _compare_contract(comparison: Any) -> None:
    require(isinstance(comparison, dict), "comparison object")
    require(comparison.get("key") == ["workbook", "case_index", "vector_name", "vector_index"], "comparison key")
    scalar = comparison.get("scalar_surface")
    require(isinstance(scalar, dict), "scalar surface")
    require(scalar.get("names") == ["COM_dB", "CTLE_DC_gain_dB", "ERL", "FOM", "ICN_mV", "IL_dB_channel_only_at_Fnq", "Peak_ISI_XTK_and_Noise_interference_at_BER_mV", "VEC_dB", "VEO_mV", "fitted_IL_dB_at_Fnq", "g_DC_HP", "itick"], "scalar names")
    require(scalar.get("selected_case_index") == 0 and scalar.get("package_testcase_index") == 0 and scalar.get("case_count") == 1, "scalar case scope")
    require(scalar.get("finite_absolute_tolerance") == 1.0e-9 and scalar.get("infinity") == "same_sign_same_position" and scalar.get("nan") == "rejected", "scalar tolerance")
    vectors = comparison.get("vectors")
    require(isinstance(vectors, dict), "vector contract")
    require(vectors.get("names") == EXPECTED_VECTOR_NAMES, "vector names")
    require(vectors.get("selected_case_index") == 0 and vectors.get("package_testcase_index") == 0, "selected package case")
    require(vectors.get("selected_port") == 1, "selected vector port")
    require(vectors.get("source") == "normal_erl_diagnostic_sidecar_or_archive_local_matlab_trace", "vector source")
    require(vectors.get("case_to_port") == [{"case_index": 0, "port": 1, "package_testcase_index": 0}], "case/port mapping")
    for key in ("elementwise", "shape_order_count_strict", "first_sample_strict", "finite_strict", "time_strictly_monotonic"):
        require(vectors.get(key) is True, f"vector gate {key}")
    tolerances = vectors.get("tolerances")
    require(tolerances == {
        "time_s": {"unit": "s", "absolute": 5.0e-24, "relative": 0.0},
        "impedance_ohm": {"unit": "ohm", "absolute": 2.0e-12, "relative": 2.0e-14},
        "ptdr": {"unit": "linear", "absolute": 5.0e-17, "relative": 2.0e-14},
        "gated": {"unit": "linear", "absolute": 5.0e-17, "relative": 2.0e-14},
    }, "vector tolerances")
    require(vectors.get("prohibited_transforms") == EXPECTED_TRANSFORMS, "prohibited transforms")
    require(comparison.get("internal_repeat") == {"exact_f64": True, "count": 2}, "internal repeat")


def validate(document: dict[str, Any], *, require_sources: bool = False, candidate_archive: Path | None = None, upstream_archive: Path | None = None) -> dict[str, Any]:
    expected_top = {"schema", "status", "formal_record_absent", "base_v3_manifest", "upstream", "candidate", "candidate_gate_parent", "matlab", "rust", "replays", "isolation", "comparison", "cache_bridge", "d3_policy", "performance", "formal_paths_absent", "tools"}
    require(set(document) == expected_top, "manifest top-level keyset")
    require(document.get("schema") == EXPECTED_SCHEMA and document.get("status") in {"preparation_bound_candidate_pending_four_replays", "preparation_bound_candidate_formal_successor_recorded"}, "schema/status")
    formal_successor = document.get("status") == "preparation_bound_candidate_formal_successor_recorded"
    require(document.get("formal_record_absent") is (not formal_successor), "formal record status")
    require(document.get("candidate") == EXPECTED_CANDIDATE, "candidate receipt")
    require(document.get("candidate_gate_parent") == EXPECTED_CANDIDATE_GATE_PARENT, "candidate gate parent")
    upstream = document.get("upstream")
    require(isinstance(upstream, dict), "upstream object")
    for key in ("commit", "tree", "archive_sha256", "archive_bytes", "workbook", "assets"):
        require(key in upstream, f"upstream {key}")
    require({key: upstream[key] for key in EXPECTED_UPSTREAM} == EXPECTED_UPSTREAM, "upstream receipt")
    _exact_asset_contract(upstream["assets"])
    _safe_repo_path(upstream["workbook"]["path"], "workbook")
    matlab_expected = {
        "required_release": "R2024b",
        "required_release_raw": "2024b",
        "executable_mode": "explicit_only_no_path_fallback",
        "semantic_run": "uninstrumented",
        "trace_run": "instrumented_diagnostic_only",
        "start_flags": ["-noFigureWindows", "-singleCompThread"],
        "mw_disable_connector": "1",
        "isolated_preference_dir": True,
    }
    require(document.get("matlab") == matlab_expected, "MATLAB runtime contract")
    require(document.get("rust") == {
        "route": "public_root_sipi_com_run",
        "build_feature": "com-direct-integration",
        "diagnostic_sidecar_feature": "normal-erl-diagnostic-sidecar",
        "diagnostic_sidecar_schema": "sipi.com.normal-erl-array-sidecar.v1",
        "executable_mode": "explicit_only_no_path_fallback",
    }, "Rust route contract")
    require(document.get("replays") == EXPECTED_REPLAYS, "replay set")
    require(document.get("isolation") == {"distinct_archive_root": True, "distinct_build_root": True, "distinct_output_root": True, "distinct_nonce": True, "internal_exact_repeat_count": 2}, "isolation contract")
    _compare_contract(document["comparison"])
    require(document.get("cache_bridge") == {"xlsx_to_mat": "exact_shape_row_column_kind_value", "matlab_must_reload_produced_mat": True}, "MAT bridge contract")
    require(document.get("d3_policy") == {"status": "not_evaluated_configuration_disables_tdiln", "selected_configs_compute_tdiln": 0, "global_d3_enabled": True}, "D3 policy")
    require(document.get("performance") == {"required": True, "rule": "each_case_rust_wall_clock_s_strictly_less_than_matlab_wall_clock_s", "instrumented_trace_included": False, "semantic_timing_source": "un-instrumented_semantic_invocation_only", "diagnostic_trace_timing_recorded": True}, "performance contract")
    formal_paths = document.get("formal_paths_absent")
    require(formal_paths == EXPECTED_FORMAL_PATHS, "formal path list")
    for path in formal_paths:
        _safe_repo_path(path, "formal path")
    formal_present = all((ROOT / path).exists() for path in formal_paths)
    require((document["status"] == "preparation_bound_candidate_formal_successor_recorded") == formal_present, "formal successor status")
    tools = document.get("tools")
    require(isinstance(tools, dict) and set(tools) == set(EXPECTED_TOOLS), "tool map")
    for name, expected_path in EXPECTED_TOOLS.items():
        item = tools[name]
        require(set(item) == {"path", "sha256"} and item["path"] == expected_path and SHA_RE.fullmatch(str(item["sha256"])), f"tool receipt: {name}")
        path = _safe_repo_path(item["path"], f"tool {name}")
        require(path.is_file() and _sha256(path) == item["sha256"], f"tool hash: {name}")
    base = document["base_v3_manifest"]
    require(set(base) == {"path", "sha256"} and base["path"] == "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v3.yaml" and SHA_RE.fullmatch(str(base["sha256"])), "v3 base receipt")
    base_path = _safe_repo_path(base["path"], "v3 base")
    require(base_path.is_file() and _sha256(base_path) == base["sha256"], "v3 base hash")
    audit_path = _safe_repo_path(tools["audit"]["path"], "audit")
    require(audit_path.read_text(encoding="utf-8").strip(), "audit is empty")
    if require_sources:
        require(candidate_archive is not None and upstream_archive is not None, "source archives required")
        _verify_archive_receipt(candidate_archive, EXPECTED_CANDIDATE, "candidate")
        _verify_archive_receipt(upstream_archive, upstream, "upstream")
    return {"valid": True, "status": document["status"], "formal_record_absent": document["formal_record_absent"]}


def _verify_archive_receipt(path: Path, receipt: dict[str, Any], label: str) -> None:
    require(all(receipt.get(key) is not None for key in ("commit", "tree", "archive_sha256", "archive_bytes")), f"{label} receipt is not bound")
    require(path.is_file(), f"{label} archive missing")
    raw = path.read_bytes()
    require(len(raw) == receipt["archive_bytes"] and hashlib.sha256(raw).hexdigest() == receipt["archive_sha256"], f"{label} archive receipt")
    if label != "upstream":
        return
    with tarfile.open(path, "r:*") as stream:
        members = stream.getmembers()
        for expected in [receipt["workbook"], *receipt["assets"]]:
            found = next((member for member in members if member.isfile() and (member.name == expected["path"] or member.name.endswith("/" + expected["path"]))), None)
            require(found is not None, f"{label} member missing: {expected['path']}")
            content = stream.extractfile(found).read()
            require(len(content) == expected["bytes"] and hashlib.sha256(content).hexdigest() == expected["sha256"], f"{label} member receipt: {expected['path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--candidate-archive", type=Path)
    parser.add_argument("--upstream-archive", type=Path)
    args = parser.parse_args(argv)
    document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    result = validate(document, require_sources=args.candidate_archive is not None or args.upstream_archive is not None, candidate_archive=args.candidate_archive, upstream_archive=args.upstream_archive)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
