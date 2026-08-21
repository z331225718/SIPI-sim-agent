"""Verify the additive Agent-COM metric authority observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06r-agent-com-metric-authority-observation.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-06r-agent-com-metric-authority-observation.md"
SCHEMA = "sipi.p5-06r.agent-com-metric-authority-observation.v1"
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
AUDIT_PATH = "docs/baselines/audits/2026-08-21-p5-06r-agent-com-metric-authority-observation.md"
ABSOLUTE = re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:home|Users|private|tmp|mnt)/")

SOURCE_OBJECTS = [
    ("matlab_src/com_ieee8023_480.m", "2e226d785c1ed2403f6d0a11288bf75939021814", 458971, "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596"),
    ("schemas/legacy-output-r480.json", "7980dcffb5a88557b8cb2e8107fae06355c91169", 2121, "aa74317a43a7152c7ed3937a04093e6c84d5583652ca4d9af2ac0fed98ad9ea6"),
    ("src/agent_com/_orchestration.py", "5d260a0aab941f1a1955fe3abef36d85a56034c0", 90877, "069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69"),
    ("src/agent_com/metrics/tdiln.py", "53aacf1c15b57cf314f0e7db5148884bf7afe3c2", 7068, "d0465246f6fd5d22d5978f5cdf2a78f7fccdfbfdd7ad0676092b4494d3698873"),
    ("src/agent_com/erl/metric.py", "ee809c9f464583b850c3e585adc8a3cfc981729b", 4029, "4051b618324448f4968e59fbb81358eb6b62bdd58e94ddf9ab67e8cfde09b3b5"),
    ("src/agent_com/models.py", "92167e385db50c76a9999c2df5118d46951b8243", 6994, "e97bd1c67fbf53f940e45fb94905e6bd5e924b164a3eecf1548a652ba0f327af"),
    ("schemas/behavior-presets.yaml", "7f67deffd1e6100f1d67912df786bbf7612eb5cc", 578, "906e1b05bedf620fa431406b0ea41fae81dd235e759ff2155c17e68dccdf6d3e"),
    ("src/agent_com/reporting.py", "efbb14dda4d656a71e6915f5c5026b719e22d141", 82620, "14c4e4f0e5e51ee6fe76343ef133a565b8c922a0794acfe6c36ac3c7bbc1a0e1"),
]
INPUT_OBJECTS = [
    ("matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "22b633b6092b4b0de0ca89273515329b362eabae", 67087, "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"),
    ("fixtures/synthetic/erl_reflective_10db_at_26p56ghz.s4p", "cb5d03536833aa1d62f6db97bae0dba6238349cb", 6457063, "72327f8d36cd7c51aaf64d803ac6e86b557d017fe574d7b2b05d4583e9494126"),
]


class ObservationError(RuntimeError):
    """Raised when the pinned observation shape is not exact."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(key)
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _git(source_root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True, check=False)
    _require(result.returncode == 0, "git_object_lookup_failed")
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _object_rows(document: dict[str, Any]) -> list[tuple[str, str, int, str]]:
    rows: list[tuple[str, str, int, str]] = []
    for item in document.get("source_objects", []):
        rows.append((str(item.get("path")), str(item.get("git_blob")), int(item.get("bytes")), str(item.get("normalized_sha256"))))
    return rows


def _verify_source_objects(source_root: Path) -> None:
    _require(source_root.is_dir(), "source_root_invalid")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{commit}}") == COMMIT, "commit_mismatch")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{tree}}") == TREE, "tree_mismatch")
    document_rows = _object_rows(_load(EVIDENCE))
    for path, oid, byte_count, digest in [*document_rows, *INPUT_OBJECTS]:
        ref = f"{COMMIT}:{path}"
        _require(_git(source_root, "rev-parse", ref) == oid, f"blob_mismatch:{path}")
        payload = _git(source_root, "cat-file", "blob", ref, binary=True)
        assert isinstance(payload, bytes)
        _require(len(payload) == byte_count, f"byte_count_mismatch:{path}")
        normalized = payload if path.endswith((".xlsx", ".s4p")) else payload.replace(b"\r\n", b"\n")
        _require(hashlib.sha256(normalized).hexdigest() == digest, f"content_hash_mismatch:{path}")


def validate_document(document: dict[str, Any] | None = None, source_root: Path | str | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "finite_com_erl_fom_tdiln_observed_scalar_td_iln_missing", "status_invalid")
    _require(document.get("authority") == "pinned_external_source_and_run_observation_only", "authority_invalid")
    scope = document.get("scope", {})
    _require(scope == {
        "work_items": ["P5-02", "P5-06", "P3C-03"],
        "slice": "P5-06r",
        "source_observation": True,
        "external_runtime": "two_fresh_clean_agent_com_runs",
        "product_runtime_invoked": False,
        "matlab_invoked": False,
        "product_vs_oracle_compare_executed": False,
        "acceptance_or_release_promoted": False,
        "historical_evidence_rewritten": False,
    }, "scope_invalid")

    selected = document.get("canonical_selection", {})
    _require(selected.get("origin") == "https://github.com/z331225718/agent-com.git", "origin_invalid")
    _require(selected.get("commit") == COMMIT and selected.get("tree") == TREE, "source_identity_invalid")
    _require(selected.get("object_format") == "sha1", "object_format_invalid")
    _require(selected.get("profile") == {"id": "r480", "source_revision": "r480", "reader_semantics": "r480", "fix_ids": []}, "profile_invalid")
    _require(selected.get("config") == {
        "role": "canonical_120f_c2c_workbook",
        "path": INPUT_OBJECTS[0][0],
        "git_blob": INPUT_OBJECTS[0][1],
        "bytes": INPUT_OBJECTS[0][2],
        "sha256": INPUT_OBJECTS[0][3],
    }, "config_binding_invalid")
    _require(selected.get("channel") == {
        "role": "THRU",
        "path": INPUT_OBJECTS[1][0],
        "git_blob": INPUT_OBJECTS[1][1],
        "bytes": INPUT_OBJECTS[1][2],
        "sha256": INPUT_OBJECTS[1][3],
    }, "channel_binding_invalid")
    _require(selected.get("override") == {"COMPUTE_TDILN": 1}, "override_invalid")
    _require(selected.get("selection_basis") == {
        "existing_named_profile": "BehaviorProfile.r480",
        "existing_named_config": "tests/test_run_api.py::STRICT_120F_C2C_CONFIG",
        "existing_named_reflective_input": "tests/test_f22_riln_golden.py::test_f22_riln_is_exposed_by_the_public_s4p_nonmmse_result",
        "existing_fixture_documentation": "fixtures/synthetic/README.md",
        "selection_policy": "one_existing_tuple_only_no_parameter_or_result_sweep",
    }, "selection_basis_invalid")

    _require(_object_rows(document) == SOURCE_OBJECTS, "source_object_inventory_invalid")
    authority = document.get("authority_map", {})
    _require(authority.get("COM_dB", {}).get("status") == "observed_finite", "com_authority_invalid")
    _require(authority.get("ERL_dB", {}).get("status") == "observed_finite_for_reflective_input", "erl_authority_invalid")
    _require(authority.get("FOM_TDILN", {}).get("required_td_iln_substitute") is False, "fom_substitution_guard_invalid")
    _require(authority.get("TD_ILN_dB", {}).get("status") == "missing_scalar", "td_iln_authority_invalid")

    runs = document.get("runs", {})
    _require(runs.get("count") == 2, "run_count_invalid")
    _require(runs.get("payload_kind") == "external_hash_only_scalar_projection", "payload_kind_invalid")
    _require(runs.get("payload_serialization") == "json_sort_keys_true_compact_utf8", "payload_serialization_invalid")
    payloads = runs.get("payloads", [])
    _require(len(payloads) == 2, "payload_count_invalid")
    _require({item.get("bytes") for item in payloads} == {398}, "payload_bytes_invalid")
    _require({item.get("sha256") for item in payloads} == {"7f62d3ed65649e3a2eed0d3f2cb6fa1891c586361dd9cb559378445ab64862e5"}, "payload_hash_invalid")
    _require(runs.get("repeatability") == "byte_identical_payloads", "repeatability_invalid")
    cases = runs.get("cases", [])
    _require(len(cases) == 2 and [item.get("case_index") for item in cases] == [0, 1], "case_order_invalid")
    _require(cases[0] == {
        "case_index": 0,
        "COM_dB": 6.6804682852917585,
        "ERL_dB": 36.59476569210085,
        "ERL11_dB": 38.131566296755295,
        "ERL22_dB": 36.59476569210085,
        "FOM_TDILN": 22.366448964047528,
        "ICN_mV": 0.0,
        "TD_ILN_dB": "missing",
        "TD_ILN": "missing",
    }, "case0_invalid")
    _require(cases[1] == {
        "case_index": 1,
        "COM_dB": 6.851887606480109,
        "ERL_dB": 36.59476569210085,
        "ERL11_dB": 38.131566296755295,
        "ERL22_dB": 36.59476569210085,
        "FOM_TDILN": 22.366448964047528,
        "ICN_mV": 0.0,
        "TD_ILN_dB": "missing",
        "TD_ILN": "missing",
    }, "case1_invalid")

    surface = document.get("required_metric_surface")
    _require(isinstance(surface, dict), "required_metric_surface_must_be_mapping")
    _require(surface.get("metrics") == [
        {"id": "COM_dB", "unit": "dB", "finite_in_all_cases": True, "status": "observed"},
        {"id": "ERL_dB", "unit": "dB", "finite_in_all_cases": True, "status": "observed"},
        {"id": "TD_ILN_dB", "unit": "dB", "finite_in_all_cases": False, "status": "missing_scalar"},
    ], "required_metric_surface_invalid")
    _require(surface.get("auxiliary_non_substitutes") == [
        {"id": "FOM_TDILN", "allowed_as": "TD_ILN_dB", "allowed": False},
        {"id": "ICN_mV", "allowed_as": "TD_ILN_dB", "allowed": False},
        {"id": "iln_vector", "allowed_as": "TD_ILN_dB", "allowed": False},
    ], "substitution_surface_invalid")

    gap = document.get("minimal_authoritative_gap", {})
    _require(gap.get("decision") == "source_api_gap_not_closed_by_canonical_input", "gap_decision_invalid")
    _require("authoritative_finite_TD_ILN_scalar_or_explicit_scalar_semantics" in gap.get("missing", []), "td_iln_gap_missing")
    _require("finite_FOM_TDILN" in gap.get("present_but_insufficient", []), "fom_gap_guard_missing")

    transition = document.get("p3c_03_transition", {})
    _require(transition.get("typed_compare_existing", {}).get("bundle_metrics") == ["COM_dB", "ERL_dB", "TD_ILN_dB"], "typed_bundle_invalid")
    _require(transition.get("typed_compare_existing", {}).get("product_crate_changed_in_this_slice") is False, "crate_scope_invalid")
    _require(transition.get("semantics_to_external_compare", {}).get("decision") == "conditionally_ready_not_admitted", "transition_invalid")

    _require(document.get("non_claims") == [
        "not_td_iln_scalar_observation",
        "not_fom_tdiln_to_td_iln_alias",
        "not_icn_to_td_iln_alias",
        "not_product_vs_agent_com_compare",
        "not_com_parity",
        "not_acceptance_evidence",
        "not_release_evidence",
        "not_parameter_sweep",
    ], "non_claims_invalid")
    audit = document.get("audit", {})
    _require(audit.get("path") == AUDIT_PATH, "audit_path_invalid")
    _require(AUDIT.is_file(), "audit_missing")
    _require(audit.get("sha256") == _sha256(AUDIT), "audit_hash_invalid")
    _require(not any(ABSOLUTE.search(value) for value in _walk(document)), "absolute_path_in_document")
    _require(not ABSOLUTE.search(AUDIT.read_text(encoding="utf-8")), "absolute_path_in_audit")
    if source_root is not None:
        _verify_source_objects(Path(source_root))
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "source_object_checked": source_root is not None,
        "finite_required_metrics": 2,
        "missing_required_metrics": ["TD_ILN_dB"],
        "p3c_03_transition": transition["semantics_to_external_compare"]["decision"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_document(source_root=args.source_root), sort_keys=True))
        return 0
    except (OSError, UnicodeError, yaml.YAMLError, ObservationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
