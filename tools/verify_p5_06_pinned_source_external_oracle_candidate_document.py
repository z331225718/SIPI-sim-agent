"""Verify the checked-in P5-06 candidate-run document without external I/O.

This is the baseline document gate.  It intentionally does not import or run
the dynamic MATLAB artifact observer; external custody can only supplement
this exact, hash-bound document and cannot replace it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-pinned-source-external-matlab-oracle-candidate-run.v1.yaml"
SCHEMA = "sipi.p5-06.pinned-source-external-matlab-oracle-candidate-run.v1"
STATUS = "pinned_source_external_matlab_oracle_candidate_run_observed"
DOCUMENT_BYTE_BUDGET = 64 * 1024

EXPECTED_TOOLS = [
    {"path": "tools/run_matlab_oracle.py", "git_blob": "36d4fa55f6eaf9ecdd72ba2cebfbc1b01908e8bc", "git_blob_sha256": "db63ed42375ac990cb53d9926f603e050b652b0706c079f2e4456a5d97d87d42", "git_blob_bytes": 30851},
    {"path": "tools/matlab_oracle/run_com_oracle.m", "git_blob": "5845a4a088fede05e9a13ae91db7b41888a3b2be", "git_blob_sha256": "ce1da4203b4372094b6cc1ad9e9ca762d9a4c4e4ef769d14a4dcb0e941d286f6", "git_blob_bytes": 5394},
    {"path": "tools/matlab_oracle/com_oracle_case_metrics.m", "git_blob": "9d13c8c9468a31ff9c06e2985bb6d03efc6428b6", "git_blob_sha256": "93fb174b26256b485a86e56ed765858eec7f5f28371df56e182c3a5e8d77a794", "git_blob_bytes": 3401},
    {"path": "tools/matlab_oracle/rebuild_oracle_summary.m", "git_blob": "114c1dc8d5041f670540e5ea40ca029b55bb7c8e", "git_blob_sha256": "ce909fb2e0a5d08c1b31d1c91b636bc1974899fe3abed8ef9e988a16abd082b0", "git_blob_bytes": 738},
]
EXPECTED_ARTIFACTS = {
    "manifest.json": {"sha256": "1862eae6a9b82cff5efb19584c2becd35fc4623d463b7ec0d0da428f088dfe0b", "bytes": 3951},
    "comparison_report.json": {"sha256": "3dc09dce815d9316ffa6cd9339d829c511b8aa41ab0c668b7449d49b5fab5006", "bytes": 8079},
    "run-01/invocation.json": {"sha256": "e47da0c8cc3a516b44a95452bc8d07f435eb01947e0500c757ca798cebaee23b", "bytes": 1075},
    "run-01/summary.json": {"sha256": "75ba60c160c7dd09ba771ee7f268d5d908ec7c60062d541ef52c60d44b4b677e", "bytes": 13529},
    "run-01/matlab_oracle.mat": {"sha256": "7bd4a5f2bf25fcecabcd3fc307bccd12cbf5da224ebbb658e9d392cf8a392a2d", "bytes": 2779063},
    "run-01/matlab.log": {"sha256": "295c600d528f820d92269dbf7529c3989ac01959768ac10754c7d32b90a7e147", "bytes": 2343},
    "run-01/checkpoints/case-001-core.mat": {"sha256": "c3b0a164a2dc210c73d62cc7ebc0d5dda43fbafd3102bb13cc0d549fa9340d11", "bytes": 4894321},
}
EXPECTED_NONCLAIMS = [
    "source_checkout_is_clean",
    "config_and_fixture_git_object_custody",
    "generated_instrumented_output_git_object_custody",
    "authorized_matlab_invocation",
    "startup_isolation",
    "complete_warning_contract",
    "complete_checkpoint_alignment_contract",
    "product_parity",
    "ieee_certification",
    "release_acceptance",
    "dynamic_observer_replaces_baseline_gate",
]
LOCAL_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/|file://)", re.IGNORECASE)


class DocumentError(RuntimeError):
    """Raised when the checked-in evidence document drifts."""


def load_document(path: Path = EVIDENCE) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > DOCUMENT_BYTE_BUDGET:
        raise DocumentError("document_byte_budget_exceeded")
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise DocumentError("document_yaml_invalid") from error
    if not isinstance(value, dict):
        raise DocumentError("document_not_mapping")
    return value


def _reject_absolute_paths(value: Any, location: str = "document") -> None:
    if isinstance(value, str):
        if LOCAL_PATH.match(value) and not value.lower().startswith(("http://", "https://")):
            raise DocumentError(f"absolute_local_path:{location}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_absolute_paths(key, f"{location}.key")
            _reject_absolute_paths(item, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_absolute_paths(item, f"{location}[{index}]")


def _exact(document: Mapping[str, Any], key: str, expected: Any) -> None:
    if document.get(key) != expected:
        raise DocumentError(f"{key}_drift")


def validate(document: Mapping[str, Any] | None = None, *, path: Path = EVIDENCE) -> dict[str, Any]:
    value: Mapping[str, Any] = load_document(path) if document is None else document
    if not isinstance(value, Mapping):
        raise DocumentError("document_not_mapping")
    _reject_absolute_paths(value)
    _exact(value, "schema", SCHEMA)
    _exact(value, "status", STATUS)

    scope = value.get("scope")
    if scope != {
        "custody": "external_only",
        "baseline_gate": "checked_in_document_only",
        "product_acceptance": False,
        "ieee_certification": False,
        "source_identity_authority": "pinned_git_object",
    }:
        raise DocumentError("scope_drift")

    source = value.get("source")
    if not isinstance(source, Mapping):
        raise DocumentError("source_missing")
    for key, expected in {
        "canonical_origin": "https://github.com/z331225718/agent-com.git",
        "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
        "object_format": "sha1",
        "checkout_clean": False,
        "source_object_status": "pinned_git_object_observed_from_dirty_checkout",
    }.items():
        _exact(source, key, expected)
    _exact(source, "matlab_source", {
        "path": "matlab_src/com_ieee8023_480.m",
        "git_blob": "2e226d785c1ed2403f6d0a11288bf75939021814",
        "git_blob_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596",
        "git_blob_bytes": 458971,
        "clean_checkout_raw_sha256": "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad",
        "clean_checkout_raw_bytes": 469713,
        "line_ending_note": "clean archive/export is CRLF; normalized bytes equal the Git blob",
    })
    _exact(source, "oracle_tools", EXPECTED_TOOLS)
    _exact(source, "instrumentation_generator", {
        "path": "tools/prepare_instrumented_oracle.py",
        "git_blob": "d1def7e3ea0730e9086b7d39fccc2b5ae99f42e7",
        "git_blob_sha256": "d44775f66afa2f496cb8633a746155c11a92fc9ec3a11f5148c0de9e53d9949b",
        "git_blob_bytes": 17286,
        "instrumented_manifest_baseline_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596",
        "instrumented_source_sha256": "b77bf8a04de77a2deaec075d20ffb80cf19f13bc79689f5e0612ce6bb0dc636f",
        "generator_source_git_bound": True,
        "generated_output_git_bound": False,
    })
    _exact(source, "input_provenance", {
        "config_git_object_bound": False,
        "fixture_git_object_bound": False,
        "status": "not_closed",
    })
    _exact(source, "invocation_provenance", {
        "manifest_and_invocation_observed": True,
        "authorization": "unproven",
        "startup_isolation": "unproven",
        "status": "not_closed",
    })

    run = value.get("run")
    if not isinstance(run, Mapping):
        raise DocumentError("run_missing")
    _exact(run, "artifact_policy", "exact_known_hashes_and_structure_budget_only")
    _exact(run, "config_input_provenance", "not_closed_by_observer")
    _exact(run, "generator_output_provenance", "not_closed_by_observer")
    _exact(run, "invocation_provenance", "observed_but_authorization_and_startup_isolation_unproven")
    _exact(run, "artifacts", EXPECTED_ARTIFACTS)
    _exact(run, "checkpoint_mat_file_count", 14275)
    _exact(run, "warning_contract_status", "known_messages_observed_not_complete_contract")

    network = value.get("network")
    if not isinstance(network, Mapping) or network.get("sdd21_abs_tolerance") != 1e-12 or network.get("sdc21_abs_tolerance") != 1e-14:
        raise DocumentError("network_tolerance_drift")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or metrics.get("output_metric_count") != 14 or metrics.get("mlse_checkpoint_count") != 6 or metrics.get("repeatability_abs_tolerance") != 1e-12:
        raise DocumentError("metric_surface_drift")
    budget = value.get("matlab_v73_reader", {}).get("hdf5_structure_budget") if isinstance(value.get("matlab_v73_reader"), Mapping) else None
    if budget != {
        "result_struct_fields": 112,
        "summary_struct_fields": 13,
        "mlse_struct_fields": 10,
        "core_output_args_fields": 112,
        "checkpoint_mat_file_count": 14275,
        "checkpoint_mat_file_count_budget": 15000,
    }:
        raise DocumentError("hdf5_structure_budget_drift")
    _exact(value, "nonclaims", EXPECTED_NONCLAIMS)
    return {
        "schema": SCHEMA,
        "status": "document_gate_passed_not_acceptance",
        "artifact_hashes_locked": len(EXPECTED_ARTIFACTS),
        "oracle_tool_objects_locked": len(EXPECTED_TOOLS),
        "nonclaims_locked": len(EXPECTED_NONCLAIMS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(path=args.document), sort_keys=True))
        return 0
    except (OSError, DocumentError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "document_gate_rejected", "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
