"""Verify the additive PB-01 executable legacy leaf evidence."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pickle
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/pb-01-legacy-leaf.v1.yaml"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ABSOLUTE = re.compile(r"(?:[A-Za-z]:[\\/]|/Users/|/home/|/tmp/|\\\\)")
EXPECTED_SOURCE = {
    "repository": "pybert",
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
}
EXPECTED_ARRAYS = [
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
]
EXPECTED_ITEM_NAMES = [
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_s",
    "ctle_s",
    "dfe_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
    "chnl_H",
    "tx_H",
    "ctle_H",
    "dfe_H",
    "tx_out_H",
    "ctle_out_H",
    "dfe_out_H",
    "tx_out",
]


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        raise pickle.UnpicklingError(f"global {module}.{name} is forbidden")


def _resolve_cargo() -> str:
    configured = os.environ.get("CARGO")
    if configured and Path(configured).is_file():
        return configured
    discovered = shutil.which("cargo")
    if discovered:
        return discovered
    fallback = Path.home() / ".cargo" / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
    if fallback.is_file():
        return str(fallback)
    raise OSError("cargo executable was not found")


def _read_pickle_schema(path: Path) -> dict[str, Any]:
    payload = _RestrictedUnpickler(io.BytesIO(path.read_bytes())).load()
    if not isinstance(payload, dict):
        raise ValueError("generated pickle payload is not a mapping")
    item_names = payload.get("item_names")
    arrays = payload.get("arrays")
    if not isinstance(item_names, list) or not all(isinstance(name, str) for name in item_names):
        raise ValueError("generated pickle item_names is not a string list")
    if not isinstance(arrays, dict) or not all(isinstance(name, str) for name in arrays):
        raise ValueError("generated pickle arrays is not a string-keyed mapping")
    return {
        "schema": payload.get("schema"),
        "item_names": item_names,
        "array_keys": sorted(arrays),
    }


def generate_pickle_schema(root: Path = ROOT) -> dict[str, Any]:
    manifest = root / "crates/sipi-pybert-direct/Cargo.toml"
    fixture = root / "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml"
    with tempfile.TemporaryDirectory(prefix="sipi-pb01-schema-") as temporary:
        artifact = Path(temporary) / "fixture.pybert_data"
        subprocess.run(
            [
                _resolve_cargo(),
                "run",
                "--quiet",
                "--manifest-path",
                str(manifest),
                "--bin",
                "sipi-pybert-direct",
                "--",
                "sim",
                str(fixture),
                "--results",
                str(artifact),
            ],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=120,
        )
        return _read_pickle_schema(artifact)


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def verify(
    document: dict[str, Any],
    root: Path = ROOT,
    artifact_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if artifact_schema is None:
        artifact_schema = generate_pickle_schema(root)
    _check(blockers, document.get("schema") == "sipi.pb-01-legacy-leaf.v1", "schema drift")
    _check(
        blockers,
        document.get("status") == "implemented_scoped_leaf_pending_immutable_bound_replay",
        "status drift",
    )
    source = document.get("source")
    _check(blockers, isinstance(source, dict), "source missing")
    if isinstance(source, dict):
        for key, expected in EXPECTED_SOURCE.items():
            _check(blockers, source.get(key) == expected, f"source.{key} drift")
        for path_key in ("source_map", "notice"):
            path = source.get(path_key)
            _check(blockers, isinstance(path, str) and (root / path).is_file(), f"source {path_key} missing")
            if isinstance(path, str):
                _check(
                    blockers,
                    source.get(f"{path_key}_sha256") == _sha256_file(root / path),
                    f"source {path_key} hash drift",
                )
    relationship = document.get("relationship")
    _check(
        blockers,
        relationship
        == {
            "predecessor_evidence": "docs/baselines/pb-01-direct-port.v1.yaml",
            "predecessor_role": "full_branch_default_error_artifact_inventory",
            "supersedes": "boundary_only_candidate_status_for_scoped_leaf",
            "preserves_predecessor_open_branch_inventory": True,
        },
        "predecessor relationship drift",
    )
    candidate = document.get("candidate")
    _check(blockers, isinstance(candidate, dict), "candidate missing")
    if isinstance(candidate, dict):
        _check(blockers, candidate.get("source_mode") == "working_tree_until_owner_commit", "candidate source mode drift")
        candidate_paths = {
            "runtime_module_sha256": "crates/sipi-pybert-direct/src/legacy_runtime.rs",
            "cli_module_sha256": "crates/sipi-pybert-direct/src/bin/sipi-pybert-direct.rs",
            "boundary_module_sha256": "crates/sipi-pybert-direct/src/legacy_sim.rs",
        }
        for key, path in candidate_paths.items():
            value = candidate.get(key)
            _check(blockers, isinstance(value, str) and HEX64.fullmatch(value) is not None, f"candidate {key} malformed")
            _check(blockers, value == _sha256_file(root / path), f"candidate {key} drift")
        _check(
            blockers,
            candidate.get("parser") == "yaml_rust2_exact_tag_policy_then_serde_yaml_projection",
            "candidate parser drift",
        )
        _check(blockers, candidate.get("runtime_python_dependency") is False, "runtime Python dependency claim drift")
    safety = document.get("safety")
    _check(
        blockers,
        safety
        == {
            "config_bytes_max": 1048576,
            "yaml_depth_max": 64,
            "allowed_root_tag": "!!python/object:pybert.configuration.PyBertCfg",
            "allowed_nested_tags": ["!!python/tuple"],
            "unclassified_tags_fail_closed": True,
            "rx_n_taps_max": 256,
            "dfe_tap_tuners_max": 64,
            "total_samples_max": 50000000,
            "result_bytes_max": 536870912,
            "checked_arithmetic_before_native_allocation": True,
            "result_path_alias_config_rejected": True,
        },
        "safety boundary drift",
    )
    fixture = document.get("fixture")
    _check(blockers, isinstance(fixture, dict), "fixture missing")
    if isinstance(fixture, dict):
        fixture_path = fixture.get("path")
        _check(blockers, fixture_path == "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml", "fixture path drift")
        _check(blockers, fixture.get("sha256") == _sha256_file(root / fixture_path), "fixture hash drift")
        profile = fixture.get("profile")
        _check(
            blockers,
            isinstance(profile, dict)
            and profile.get("modulation") == "NRZ"
            and profile.get("channel") == "analytic_metallic_line"
            and profile.get("ctle") == "bypass"
            and profile.get("dfe") == "bypass",
            "fixture profile drift",
        )
    artifact = document.get("artifact")
    _check(blockers, isinstance(artifact, dict), "artifact missing")
    if isinstance(artifact, dict):
        _check(blockers, artifact.get("suffix") == ".pybert_data", "artifact suffix drift")
        _check(blockers, artifact.get("rust_codec") == "python_pickle_dict_sipi.pybert_data.v1", "Rust codec drift")
        _check(blockers, artifact.get("upstream_codec") == "PyBertData_pickle", "upstream codec drift")
        _check(blockers, artifact.get("canonical_item_names") == EXPECTED_ITEM_NAMES, "canonical item names drift")
        _check(blockers, artifact.get("item_name_count") == 23, "item name count drift")
        _check(
            blockers,
            artifact.get("array_key_policy") == "exact_set_equal_to_canonical_item_names"
            and artifact.get("array_key_count") == 23
            and artifact.get("noncanonical_array_keys") == [],
            "array key policy drift",
        )
        _check(
            blockers,
            artifact.get("schema_probe") == "runtime_generated_fixture_pickle_restricted_decode",
            "schema probe mode drift",
        )
        _check(blockers, artifact.get("compared_arrays") == EXPECTED_ARRAYS, "compared array set drift")
        tolerance = artifact.get("tolerance")
        _check(
            blockers,
            isinstance(tolerance, dict)
            and tolerance.get("absolute") == 1.0e-7
            and tolerance.get("relative_scale") == 1.0e-6,
            "tolerance drift",
        )
    _check(
        blockers,
        artifact_schema
        == {
            "schema": "sipi.pybert_data.v1",
            "item_names": EXPECTED_ITEM_NAMES,
            "array_keys": sorted(EXPECTED_ITEM_NAMES),
        },
        "runtime pickle schema drift",
    )
    oracle = document.get("oracle")
    _check(blockers, isinstance(oracle, dict), "oracle missing")
    if isinstance(oracle, dict):
        runner_path = oracle.get("runner")
        _check(blockers, runner_path == "tools/run_pb_01_legacy_leaf_replay.py", "oracle runner path drift")
        _check(blockers, oracle.get("runner_sha256") == _sha256_file(root / runner_path), "oracle runner hash drift")
        _check(blockers, oracle.get("local_observation") == "passed", "local observation drift")
        _check(blockers, oracle.get("bound_report") is None, "unbound report must remain explicit")
    parity = document.get("parity")
    _check(
        blockers,
        isinstance(parity, dict)
        and parity.get("status") == "scoped_leaf_observed_open"
        and parity.get("numeric_payload_compared") is True
        and parity.get("compared_array_count") == 12
        and parity.get("branch_complete") is False
        and parity.get("exact_pybert_data_class_pickle") is False,
        "parity boundary drift",
    )
    claims = document.get("claims")
    _check(blockers, isinstance(claims, dict), "claims missing")
    if isinstance(claims, dict):
        _check(blockers, claims.get("scoped_nrz_metallic_line_leaf") is True, "scoped leaf claim missing")
        _check(blockers, all(value is False for key, value in claims.items() if key != "scoped_nrz_metallic_line_leaf"), "claim boundary drift")
    open_branches = document.get("open_branches")
    _check(blockers, isinstance(open_branches, list) and len(open_branches) >= 7, "open branch inventory drift")
    audit = document.get("audit")
    _check(blockers, isinstance(audit, dict), "audit missing")
    if isinstance(audit, dict):
        path = audit.get("path")
        digest = audit.get("sha256")
        _check(blockers, path == "docs/baselines/audits/2026-08-23-pb-01-legacy-leaf-runtime.md", "audit path drift")
        _check(blockers, digest == _sha256_file(root / path), "audit hash drift")
    serialized = json.dumps(document, ensure_ascii=True, sort_keys=True, default=str)
    _check(blockers, ABSOLUTE.search(serialized) is None, "evidence contains an absolute host path")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    try:
        document = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
        result = verify(document, artifact_schema=generate_pickle_schema())
    except (OSError, ValueError, pickle.UnpicklingError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
