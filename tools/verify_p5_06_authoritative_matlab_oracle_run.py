"""Verify one hash-bound external Agent-COM MATLAB oracle run.

This is a custody verifier, not a COM implementation and not a product
acceptance gate.  It deliberately reads the source identity from the pinned
Git object instead of trusting ``code_revision`` or an ignored output
manifest.  MATLAB v7.3 output is inspected through its HDF5 struct metadata;
the Rust MAT-v5 configuration reader is not used for result files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ORIGIN = "https://github.com/z331225718/agent-com.git"
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SOURCE_PATH = "matlab_src/com_ieee8023_480.m"
SOURCE_BLOB = "2e226d785c1ed2403f6d0a11288bf75939021814"
SOURCE_SHA256 = "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596"
SOURCE_BYTES = 458971
METRIC_ABS_TOLERANCE = 1e-12
NETWORK_SDD_ABS_TOLERANCE = 1e-12
NETWORK_SDC_ABS_TOLERANCE = 1e-14
CHECKPOINT_FILE_COUNT = 14275
CHECKPOINT_FILE_COUNT_BUDGET = 15000
JSON_BYTE_BUDGET = 64 * 1024
LOG_BYTE_BUDGET = 64 * 1024

# This verifier intentionally accepts one exact external candidate bundle;
# it is not a general external-artifact promotion path.
KNOWN_RUN_ARTIFACTS = {
    "manifest.json": ("1862eae6a9b82cff5efb19584c2becd35fc4623d463b7ec0d0da428f088dfe0b", 3951),
    "comparison_report.json": ("3dc09dce815d9316ffa6cd9339d829c511b8aa41ab0c668b7449d49b5fab5006", 8079),
    "run-01/invocation.json": ("e47da0c8cc3a516b44a95452bc8d07f435eb01947e0500c757ca798cebaee23b", 1075),
    "run-01/summary.json": ("75ba60c160c7dd09ba771ee7f268d5d908ec7c60062d541ef52c60d44b4b677e", 13529),
    "run-01/matlab_oracle.mat": ("7bd4a5f2bf25fcecabcd3fc307bccd12cbf5da224ebbb658e9d392cf8a392a2d", 2779063),
    "run-01/matlab.log": ("295c600d528f820d92269dbf7529c3989ac01959768ac10754c7d32b90a7e147", 2343),
    "run-01/checkpoints/case-001-core.mat": ("c3b0a164a2dc210c73d62cc7ebc0d5dda43fbafd3102bb13cc0d549fa9340d11", 4894321),
}

ORACLE_TOOL_OBJECTS = {
    "tools/run_matlab_oracle.py": {
        "blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc",
        "sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42",
        "bytes": 30851,
    },
    "tools/matlab_oracle/run_com_oracle.m": {
        "blob": "5845a4a088fede05e9a13ae91db7b41888a3b2be",
        "sha256": "ce1da4203b4372094b6cc1ad9e9ca762d9a4c4e4ef769d14a4dcb0e941d286f6",
        "bytes": 5394,
    },
    "tools/matlab_oracle/com_oracle_case_metrics.m": {
        "blob": "9d13c8c9468a31ff9c06e2985bb6d03efc6428b6",
        "sha256": "93fb174b26256b485a86e56ed765858eec7f5f28371df56e182c3a5e8d77a794",
        "bytes": 3401,
    },
    "tools/matlab_oracle/rebuild_oracle_summary.m": {
        "blob": "114c1dc8d5041f670540e5ea40ca029b55bb7c8e",
        "sha256": "ce909fb2e0a5d08c1b31d1c91b636bc1974899fe3abed8ef9e988a16abd082b0",
        "bytes": 738,
    },
}
INSTRUMENT_GENERATOR_OBJECT = {
    "blob": "d1def7e3ea0730e9086b7d39fccc2b5ae99f42e7",
    "sha256": "d44775f66afa2f496cb8633a746155c11a92fc9ec3a11f5148c0de9e53d9949b",
    "bytes": 17286,
}

METRIC_FIELDS = (
    "FOM",
    "COM_dB",
    "VEC_dB",
    "VEO_mV",
    "ERL",
    "ERL11",
    "ERL22",
    "IL_dB_channel_only_at_Fnq",
    "fitted_IL_dB_at_Fnq",
    "ICN_mV",
    "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "CTLE_DC_gain_dB",
    "g_DC_HP",
    "itick",
)
MLSE_FIELDS = (
    "Q_budget_adj",
    "COM_from_matlab",
    "delta_com",
    "COM",
    "DER_MLSE",
    "DER_MLSE_trunc",
)
KNOWN_WARNING_MESSAGES = (
    "MLSE not applied because there is more noise than signal",
    "MLSE truncation failed. Try increasing trunc",
    "MLSE not applied because the DER is less than that required for the CDR to lock",
    "COM_CONTRIBUTION_CURVES not functional yet with MLSE",
    "Anti-causal response found. Finer frequency step is required for this channel",
)


class VerificationError(RuntimeError):
    """Raised when an external oracle run cannot be proven hash-consistent."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text_bytes(payload: bytes) -> bytes:
    """Normalize checkout CRLF without accepting a non-text line ending."""

    normalized = payload.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise VerificationError("bare_carriage_return_in_source_material")
    return normalized


def _git(root: Path, *arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
    )
    if result.returncode != 0:
        raise VerificationError("git_query_failed:" + " ".join(arguments))
    return result.stdout.strip() if text else result.stdout


def git_object_identity(source_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise VerificationError("source_root_missing")
    if str(_git(source_root, "remote", "get-url", "origin")) != ORIGIN:
        raise VerificationError("canonical_origin_mismatch")
    if str(_git(source_root, "rev-parse", "--show-object-format")) != "sha1":
        raise VerificationError("object_format_mismatch")
    if str(_git(source_root, "rev-parse", "HEAD")) != COMMIT:
        raise VerificationError("pinned_commit_mismatch")
    tree = str(_git(source_root, "rev-parse", f"{COMMIT}^{{tree}}"))
    if tree != TREE:
        raise VerificationError("pinned_tree_mismatch")

    objects: dict[str, dict[str, Any]] = {}
    expected_objects = {
        SOURCE_PATH: {
            "blob": SOURCE_BLOB,
            "sha256": SOURCE_SHA256,
            "bytes": SOURCE_BYTES,
        },
        **ORACLE_TOOL_OBJECTS,
    }
    for path, expected in expected_objects.items():
        blob = str(_git(source_root, "rev-parse", f"{COMMIT}:{path}"))
        if expected["blob"] != "?" * 40 and blob != expected["blob"]:
            raise VerificationError("git_blob_mismatch:" + path)
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
        assert isinstance(payload, bytes)
        if len(payload) != int(expected["bytes"]):
            raise VerificationError("git_blob_length_mismatch:" + path)
        if sha256_bytes(payload) != expected["sha256"]:
            raise VerificationError("git_blob_sha256_mismatch:" + path)
        objects[path] = {
            "git_blob": blob,
            "git_blob_sha256": sha256_bytes(payload),
            "git_blob_bytes": len(payload),
        }
    return {
        "canonical_origin": ORIGIN,
        "commit": COMMIT,
        "tree": TREE,
        "object_format": "sha1",
        "worktree_status": str(_git(source_root, "status", "--porcelain")),
        "checkout_clean": str(_git(source_root, "status", "--porcelain")) == "",
        "objects": objects,
    }


def _load_json(
    path: Path,
    *,
    expected_size: int | None = None,
    byte_budget: int = JSON_BYTE_BUDGET,
) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if expected_size is not None and size != expected_size:
            raise VerificationError(f"json_size_mismatch:{path.name}")
        if size > byte_budget:
            raise VerificationError(f"json_byte_budget_exceeded:{path.name}")
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError("json_unreadable:" + path.name) from error
    if not isinstance(value, dict):
        raise VerificationError("json_not_object:" + path.name)
    return value


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise VerificationError(f"{label}_missing:{path.name}")
    return path


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise VerificationError(f"{label}_missing:{path.name}")
    return path


def _verify_known_artifact(output_root: Path, relative_path: str) -> Path:
    expected = KNOWN_RUN_ARTIFACTS.get(relative_path)
    if expected is None:
        raise VerificationError("artifact_not_in_exact_bundle:" + relative_path)
    path = _require_file(output_root / relative_path, "oracle_artifact")
    expected_hash, expected_size = expected
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise VerificationError("oracle_artifact_size_mismatch:" + relative_path)
    if sha256_file(path) != expected_hash:
        raise VerificationError("oracle_artifact_hash_mismatch:" + relative_path)
    return path


def _manifest_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo_root / path
    return path


def _verify_exported_material(
    source_root: Path,
    repo_root: Path,
    relative_path: str,
    manifest_hash: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    path = _require_file(_manifest_path(repo_root, relative_path), "oracle_material")
    raw = path.read_bytes()
    raw_hash = sha256_bytes(raw)
    normalized = normalize_text_bytes(raw)
    object_info = expected
    blob = str(_git(source_root, "rev-parse", f"{COMMIT}:{relative_path}"))
    git_payload = _git(source_root, "cat-file", "blob", blob, text=False)
    assert isinstance(git_payload, bytes)
    if normalized != git_payload:
        raise VerificationError("oracle_material_content_drift:" + relative_path)
    if raw_hash.lower() != str(manifest_hash).lower():
        raise VerificationError("oracle_material_manifest_hash_drift:" + relative_path)
    if sha256_bytes(normalized) != object_info["sha256"]:
        raise VerificationError("oracle_material_git_hash_drift:" + relative_path)
    return {
        "path": relative_path,
        "raw_checkout_sha256": raw_hash,
        "raw_checkout_bytes": len(raw),
        "git_blob": blob,
        "git_blob_sha256": object_info["sha256"],
        "git_blob_bytes": object_info["bytes"],
    }


def _decode_matlab_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "".join(_decode_matlab_text(item) for item in value)
    if hasattr(value, "reshape"):
        return "".join(_decode_matlab_text(item) for item in value.reshape(-1))
    return str(value)


def matlab_struct_fields(group: Any) -> list[str]:
    """Read MATLAB v7.3 ``MATLAB_fields`` without trusting object names."""

    attributes = getattr(group, "attrs", {})
    matlab_class = _decode_matlab_text(attributes.get("MATLAB_class", b""))
    if matlab_class != "struct":
        raise VerificationError("matlab_group_not_struct")
    values = attributes.get("MATLAB_fields")
    if values is None:
        raise VerificationError("matlab_struct_fields_missing")
    flattened = values.reshape(-1) if hasattr(values, "reshape") else values
    fields = [_decode_matlab_text(value) for value in flattened]
    if len(fields) != len(set(fields)):
        raise VerificationError("matlab_struct_fields_duplicate")
    return fields


def _hdf5_scalar(dataset: Any) -> float:
    import numpy as np

    if not hasattr(dataset, "shape"):
        raise VerificationError("matlab_scalar_not_dataset")
    value = np.asarray(dataset[()])
    if value.size != 1:
        raise VerificationError("matlab_scalar_not_scalar")
    scalar = value.reshape(-1)[0]
    if isinstance(scalar, np.generic):
        scalar = scalar.item()
    if isinstance(scalar, bool) or not isinstance(scalar, (int, float)):
        raise VerificationError("matlab_scalar_not_real_number")
    return float(scalar)


def _verify_matlab_v73(run_dir: Path, summary: dict[str, Any]) -> dict[str, Any]:
    try:
        import h5py
    except ImportError as error:
        raise VerificationError("h5py_required_for_matlab_v73_result_reader") from error

    result_path = _require_file(run_dir / "matlab_oracle.mat", "matlab_oracle")
    core_path = _require_file(run_dir / "checkpoints" / "case-001-core.mat", "core_checkpoint")
    required_result_fields = set(METRIC_FIELDS) | {"MLSE_results", "param", "fom_result"}
    with h5py.File(result_path, "r") as result_file:
        top_level = set(result_file.keys())
        if not {"results", "summary", "#refs#"}.issubset(top_level):
            raise VerificationError("matlab_v73_top_level_surface_mismatch")
        results = result_file["results"]
        fields = set(matlab_struct_fields(results))
        if len(fields) != 112 or not required_result_fields.issubset(fields):
            raise VerificationError("matlab_result_metric_surface_incomplete")
        mlse = result_file["results"]["MLSE_results"]
        mlse_fields = set(matlab_struct_fields(mlse))
        if len(mlse_fields) != 10 or not set(MLSE_FIELDS).issubset(mlse_fields):
            raise VerificationError("matlab_result_mlse_surface_incomplete")
        summary_fields = set(matlab_struct_fields(result_file["summary"]))
        if len(summary_fields) != 13 or not {"case_count", "case_metrics", "output_metrics"}.issubset(summary_fields):
            raise VerificationError("matlab_summary_surface_incomplete")

        case = summary["case_metrics"][0]
        output_metrics = case["output_metrics"]
        for field in ("FOM", "COM_dB", "VEC_dB"):
            if field not in results or output_metrics[field].get("kind") != "finite":
                raise VerificationError("matlab_result_metric_missing:" + field)
            if abs(_hdf5_scalar(results[field]) - float(output_metrics[field]["value"])) > METRIC_ABS_TOLERANCE:
                raise VerificationError("matlab_result_metric_summary_mismatch:" + field)
        mlse_summary = case["internal_checkpoints"]["mlse"]
        for field in MLSE_FIELDS:
            if field not in mlse or field not in mlse_summary:
                raise VerificationError("matlab_result_mlse_missing:" + field)
            expected = float(mlse_summary[field])
            if abs(_hdf5_scalar(mlse[field]) - expected) > METRIC_ABS_TOLERANCE:
                raise VerificationError("matlab_result_mlse_summary_mismatch:" + field)

    with h5py.File(core_path, "r") as core_file:
        core_fields = set(core_file.keys())
        if not {"output_args", "param", "fom_result", "PDF", "CDF", "PSD_results"}.issubset(core_fields):
            raise VerificationError("matlab_core_checkpoint_surface_incomplete")
        output_fields = set(matlab_struct_fields(core_file["output_args"]))
        if len(output_fields) != 112 or not {"MLSE_results", "OP", "param", "fom_result", "PDF", "CDF", "PSD_results"}.issubset(output_fields):
            raise VerificationError("matlab_core_output_args_surface_incomplete")
    return {
        "format": "MATLAB v7.3 HDF5",
        "result_file_sha256": sha256_file(result_path),
        "core_checkpoint_sha256": sha256_file(core_path),
        "result_struct_fields_checked": len(fields),
        "mlse_struct_fields_checked": len(mlse_fields),
        "core_output_args_fields_checked": len(output_fields),
    }


def _validate_comparison(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("all_passed") is not True:
        raise VerificationError("comparison_report_not_passed")
    repeatability = report.get("matlab_repeatability")
    if not isinstance(repeatability, dict) or repeatability.get("tolerance") != METRIC_ABS_TOLERANCE:
        raise VerificationError("metric_tolerance_mismatch")
    for check in repeatability.get("checks", []):
        if check.get("passed") is not True or float(check.get("max_abs_delta", float("inf"))) > METRIC_ABS_TOLERANCE:
            raise VerificationError("metric_repeatability_outside_tolerance")
    network = report.get("network_comparison")
    if not isinstance(network, dict):
        raise VerificationError("network_comparison_missing")
    for check in network.get("checks", []):
        if check.get("passed") is not True:
            raise VerificationError("network_comparison_not_passed")
        if float(check.get("abs_delta_db", float("inf"))) > NETWORK_SDD_ABS_TOLERANCE:
            raise VerificationError("network_sdd_tolerance_mismatch")
        if float(check.get("matlab_sdc21_abs", float("inf"))) > NETWORK_SDC_ABS_TOLERANCE:
            raise VerificationError("network_sdc_tolerance_mismatch")
    return {
        "metric_abs_tolerance": METRIC_ABS_TOLERANCE,
        "network_sdd_abs_tolerance": NETWORK_SDD_ABS_TOLERANCE,
        "network_sdc_abs_tolerance": NETWORK_SDC_ABS_TOLERANCE,
        "metric_checks": len(repeatability.get("checks", [])),
        "network_checks": len(network.get("checks", [])),
    }


def observed_warning_messages(log_path: Path) -> list[str]:
    if log_path.stat().st_size > LOG_BYTE_BUDGET:
        raise VerificationError("matlab_log_byte_budget_exceeded")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return [message for message in KNOWN_WARNING_MESSAGES if message in text]


def _checkpoint_file_count(run_dir: Path) -> int:
    checkpoint_dir = _require_directory(run_dir / "checkpoints", "checkpoint_directory")
    count = 0
    for _ in checkpoint_dir.glob("*.mat"):
        count += 1
        if count > CHECKPOINT_FILE_COUNT_BUDGET:
            raise VerificationError("checkpoint_file_count_budget_exceeded")
    if count != CHECKPOINT_FILE_COUNT:
        raise VerificationError("checkpoint_file_count_mismatch")
    return count


def verify(source_root: Path, output_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    artifact_paths = {
        relative_path: _verify_known_artifact(output_root, relative_path)
        for relative_path in KNOWN_RUN_ARTIFACTS
    }
    manifest = _load_json(artifact_paths["manifest.json"], expected_size=KNOWN_RUN_ARTIFACTS["manifest.json"][1])
    run_dir = output_root / "run-01"
    summary = _load_json(artifact_paths["run-01/summary.json"], expected_size=KNOWN_RUN_ARTIFACTS["run-01/summary.json"][1])
    comparison = _load_json(artifact_paths["comparison_report.json"], expected_size=KNOWN_RUN_ARTIFACTS["comparison_report.json"][1])
    identity = git_object_identity(source_root)
    if comparison.get("provenance_manifest") != manifest:
        raise VerificationError("comparison_manifest_mismatch")

    repo_root_value = manifest.get("repo_root")
    if not isinstance(repo_root_value, str):
        raise VerificationError("manifest_repo_root_missing")
    repo_root = Path(repo_root_value)
    source_record = manifest.get("source", {}).get("com_source", {})
    if source_record.get("path") != SOURCE_PATH:
        raise VerificationError("manifest_source_path_mismatch")
    source_material = _verify_exported_material(
        source_root,
        repo_root,
        SOURCE_PATH,
        str(source_record.get("sha256", "")),
        {"sha256": SOURCE_SHA256, "bytes": SOURCE_BYTES},
    )

    tool_materials = []
    manifest_tools = {str(item.get("path")).replace("\\", "/"): item for item in manifest.get("source", {}).get("oracle_tools", [])}
    for path, expected in ORACLE_TOOL_OBJECTS.items():
        if path not in manifest_tools:
            raise VerificationError("manifest_tool_missing:" + path)
        tool_materials.append(_verify_exported_material(source_root, repo_root, path, str(manifest_tools[path].get("sha256", "")), expected))

    instrumented_record = manifest.get("source", {}).get("instrumented_source", {})
    instrumented_root = Path(str(instrumented_record.get("path", "")))
    instrumentation = _load_json(_require_file(instrumented_root / "instrumentation_manifest.json", "instrumentation_manifest"))
    if instrumentation.get("baseline", {}).get("sha256") != SOURCE_SHA256:
        raise VerificationError("instrumented_baseline_source_mismatch")
    generator_material = _verify_exported_material(
        source_root,
        repo_root,
        "tools/prepare_instrumented_oracle.py",
        str(instrumentation.get("generator_sha256", "")),
        INSTRUMENT_GENERATOR_OBJECT,
    )
    instrumented_path = _require_file(instrumented_root / "com_ieee8023_480.m", "instrumented_source")
    if sha256_file(instrumented_path) != str(instrumentation.get("instrumented", {}).get("sha256", "")):
        raise VerificationError("instrumented_source_hash_mismatch")

    invocation = _load_json(artifact_paths["run-01/invocation.json"], expected_size=KNOWN_RUN_ARTIFACTS["run-01/invocation.json"][1])
    command = " ".join(str(part) for part in invocation.get("command", []))
    for marker in ("-batch", "run_com_oracle", "COM_ORACLE_SOURCE_DIR", "COM_ORACLE_CHECKPOINT_DIR"):
        if marker not in command:
            raise VerificationError("oracle_invocation_marker_missing:" + marker)

    if int(summary.get("case_count", 0)) != len(summary.get("case_metrics", [])) or not summary.get("case_metrics"):
        raise VerificationError("summary_case_count_mismatch")
    for case in summary["case_metrics"]:
        output_metrics = case.get("output_metrics", {})
        if set(output_metrics) != set(METRIC_FIELDS):
            raise VerificationError("summary_metric_surface_mismatch")
        mlse = case.get("internal_checkpoints", {}).get("mlse", {})
        if set(mlse) != set(MLSE_FIELDS):
            raise VerificationError("summary_mlse_surface_mismatch")

    tolerance = _validate_comparison(comparison)
    mat_surface = _verify_matlab_v73(run_dir, summary)
    warning_messages = observed_warning_messages(artifact_paths["run-01/matlab.log"])
    checkpoint_count = _checkpoint_file_count(run_dir)
    return {
        "schema": "sipi.p5-06.pinned-source-external-matlab-oracle-candidate-run.v1",
        "status": "pinned_source_external_matlab_oracle_candidate_run_observed",
        "source": identity,
        "source_identity_status": "pinned_git_object_dirty_checkout" if not identity["checkout_clean"] else "pinned_git_object_clean_checkout",
        "source_material": source_material,
        "oracle_tool_material": tool_materials,
        "instrumentation": {
            "baseline_sha256": instrumentation["baseline"]["sha256"],
            "instrumented_sha256": instrumentation["instrumented"]["sha256"],
            "generator": instrumentation.get("generator"),
            "generator_sha256": instrumentation.get("generator_sha256"),
            "generator_material": generator_material,
        },
        "run": {
            "scenario": manifest.get("scenario"),
            "case_count": summary["case_count"],
            "matlab_release": summary.get("matlab_release"),
            "duration_seconds": summary.get("duration_seconds"),
            "checkpoint_mat_file_count": checkpoint_count,
            "warnings_observed": warning_messages,
            "warning_contract_status": "known_messages_observed_not_complete_contract",
            "artifact_policy": "exact_known_hashes_and_structure_budget_only",
            "input_config_provenance": "not_closed_by_this_observer",
            "generator_output_provenance": "not_closed_by_this_observer",
            "invocation_provenance": "manifest_and_invocation_observed; authorization_and_startup_isolation_unproven",
        },
        "metric_surface": {
            "output_fields": list(METRIC_FIELDS),
            "mlse_fields": list(MLSE_FIELDS),
            "tolerances": tolerance,
        },
        "matlab_v73_reader": mat_surface,
        "non_claims": [
            "The pinned Git object, not code_revision, is the source identity anchor.",
            "The source checkout was dirty; config/input, generated instrumented output, and invocation provenance are not fully Git-bound.",
            "This observes one exact external candidate bundle; it does not prove product parity or IEEE certification.",
            "The warning list is a run observation, not the complete R480 warning contract.",
            "Startup isolation, external authorization, full checkpoint alignment tolerances, and Rust MAT-v7.3 support remain open.",
            "This dynamic observer cannot replace the checked-in baseline document gate.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.source_root, args.output_root)
    except (OSError, ValueError, VerificationError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": "sipi.p5-06.pinned-source-external-matlab-oracle-candidate-run.v1", "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
