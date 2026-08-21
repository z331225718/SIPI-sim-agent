"""Verify the independent P5-02p pinned-source parameter observation."""

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
EVIDENCE = ROOT / "docs/baselines/p5-02p-pinned-mlse-default-consumption-observation.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-02p-pinned-mlse-default-consumption-observation.md"

SCHEMA = "sipi.p5-02p.pinned-mlse-default-consumption-observation.v1"
OBSERVATION_METHOD = {
    "document_only": "static YAML contract and mutation gate; no external checkout is read",
    "source_root_mode": "optional Git-object revalidation with rev-parse and cat-file",
    "source_git_object_checked_default": False,
    "source_line_check": "exact decoded blob lines for assignments, helper, input shape, and consumers",
}
AUDIT_BINDING = {
    "path": "docs/baselines/audits/2026-08-21-p5-02p-pinned-mlse-default-consumption-observation.md",
    "sha256": "f392d24f311247e9b45c02da10d1250bebeecb5c43065465255a26f2cfb3c3b1",
}
SOURCE = {
    "repository": "https://github.com/z331225718/agent-com.git",
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "path": "matlab_src/com_ieee8023_480.m",
    "git_blob_oid_sha1": "2e226d785c1ed2403f6d0a11288bf75939021814",
    "normalized_content_sha256": "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596",
    "checkout_status": "dirty_external_checkout_not_used",
    "binding": "canonical_git_object",
}
PARAMETER_INPUT_SURFACE = {
    "source_lines": [
        {"line": 8738, "expression": "first_column_data = parameter(:,1);"},
        {"line": 8747, "expression": "    parameter = parameter(1:first_start_row-1,:);"},
    ],
    "observation": "parameter is a MATLAB cell-table surface; package blocks are split before keyword lookup.",
    "provenance_status": "source_input_shape_observed_not_workbook_provenance",
}
READER = {
    "repository": SOURCE["repository"],
    "commit": SOURCE["commit"],
    "path": "src/agent_com/config/excel.py",
    "git_blob_oid_sha1": "1cce4365b64f3bb0ef1f7617107d2df4c929afc7",
    "mat_reader": "scipy.io.loadmat",
    "simplify_cells": False,
    "required_variable": "parameter",
    "required_rank": 2,
    "cell_surface": "COM_Settings",
    "lookup_surface": "case_insensitive_right_hand_cell",
    "provenance_status": "pinned_source_reader_observed_not_product_authority",
}
HELPER_CONTRACT = {
    "source_line": 10408,
    "function": "xls_parameter",
    "source_lines": [
        {"line": 10408, "text": "function p=xls_parameter(param_sheet, param_name, eval_if_string, default_value)"},
        {"line": 10411, "text": "[row, col]=find(strcmpi(param_sheet, param_name)); % RIM 08-26-2020 make case insensitive"},
        {"line": 10414, "text": "        missingParameter(param_name);"},
        {"line": 10416, "text": "        p = default_value;"},
        {"line": 10422, "text": "    error('COM:XLS_parameter:MultipleOccurrence', ..."},
        {"line": 10423, "text": "        '%d occurrences of \"%s\" found. Please recheck spreadsheet', numel(row), param_name);% RIM 01-0 8-20"},
        {"line": 10426, "text": "    p=param_sheet{row, col+1};"},
        {"line": 10429, "text": "    p=eval(p);"},
    ],
    "lookup_expression": "[row, col]=find(strcmpi(param_sheet, param_name)); % RIM 08-26-2020 make case insensitive",
    "missing_without_default": "missingParameter(param_name)",
    "missing_with_default": "p = default_value;",
    "duplicate_behavior": "error COM:XLS_parameter:MultipleOccurrence",
    "value_expression": "p=param_sheet{row, col+1};",
    "string_behavior": "eval_when_eval_if_string_is_true",
    "observation": "selected defaults are fallback arguments to xls_parameter, not product-policy defaults.",
}
ENTRIES = [
    {
        "id": "der_cdr",
        "keyword": "DER_CDR",
        "target_variable": "param.DER_CDR",
        "assignment_source_line": 8915,
        "assignment": "param.DER_CDR = xls_parameter(parameter, 'DER_CDR',true,1e-2); % min DER required for a CDR ",
        "default_kind": "fallback_literal",
        "source_default_literal": "1e-2",
        "comment_observation": "min DER required for a CDR",
        "consumers": [
            {"source_line": 2187, "expression": "if DER_DFE <= param.DER_CDR", "source_line_text": "if DER_DFE <= param.DER_CDR", "observation": "source gate condition for entering the MLSE sequence loop"},
        ],
        "semantic_boundary": "source gate observed; no DER tolerance or CDR acceptance rule is inferred",
    },
    {
        "id": "trunc",
        "keyword": "trunc",
        "target_variable": "param.trunc",
        "assignment_source_line": 8926,
        "assignment": "param.trunc = xls_parameter(parameter, 'trunc', true, 128); % MLSE sequence truncation length",
        "default_kind": "fallback_literal",
        "source_default_literal": 128,
        "comment_observation": "MLSE sequence truncation length",
        "consumers": [
            {"source_line": 2199, "expression": "if j == param.trunc", "source_line_text": "\tif j == param.trunc", "observation": "source checkpoint at the selected truncation index"},
            {"source_line": 2204, "expression": "elseif j < param.trunc", "source_line_text": "\telseif j < param.trunc", "observation": "source continuation of the truncation convolution path"},
            {"source_line": 2228, "expression": "warning('MLSE truncation failed. Try increasing trunc')", "source_line_text": "        warning('MLSE truncation failed. Try increasing trunc')", "observation": "source warning call when the computed delta is negative"},
        ],
        "semantic_boundary": "source loop bound and warning call observed; no checkpoint alignment tolerance is inferred",
    },
    {
        "id": "n_tc_alias",
        "keyword": "N_tc",
        "target_variable": "param.trunc",
        "assignment_source_line": 8927,
        "assignment": "param.trunc = xls_parameter(parameter, 'N_tc', true, param.trunc); % MLSE sequence truncation length",
        "default_kind": "prior_value_alias",
        "source_default_literal": "param.trunc",
        "comment_observation": "N_tc is an alias/override lookup after the trunc lookup",
        "consumers": [
            {"source_line": 2199, "expression": "if j == param.trunc", "source_line_text": "\tif j == param.trunc", "observation": "alias result shares the truncation checkpoint"},
            {"source_line": 2204, "expression": "elseif j < param.trunc", "source_line_text": "\telseif j < param.trunc", "observation": "alias result shares the truncation continuation path"},
        ],
        "semantic_boundary": "N_tc has no independent literal default; absent N_tc retains the preceding param.trunc value",
    },
    {
        "id": "q_budget_adj",
        "keyword": "Q_budget_adj",
        "target_variable": "param.Q_budget_adj",
        "assignment_source_line": 8930,
        "assignment": "param.Q_budget_adj = xls_parameter(parameter, 'Q_budget_adj', true, 0); % MLSE sequence truncation length",
        "default_kind": "fallback_literal",
        "source_default_literal": 0,
        "comment_observation": "source comment names MLSE sequence truncation length",
        "consumers": [
            {"source_line": 2212, "expression": "if param.Q_budget_adj == 0", "source_line_text": "    if param.Q_budget_adj == 0", "observation": "scalar zero selects the zero adjustment branch"},
            {"source_line": 2215, "expression": "Q_budget_adj=param.Q_budget_adj(1) -param.Q_budget_adj(2)*COM_from_matlab;", "source_line_text": "        Q_budget_adj=param.Q_budget_adj(1) -param.Q_budget_adj(2)*COM_from_matlab; ", "observation": "nonzero source value is consumed as a two-term adjustment"},
            {"source_line": 2219, "expression": "delta_com=20*log10(1/A_s *-CDF_inv_ev ( DER_MLSE_trunc,p_an,P_an )  )- Q_budget_adj ;% shakiba_3dj_01_2405", "source_line_text": "    delta_com=20*log10(1/A_s *-CDF_inv_ev ( DER_MLSE_trunc,p_an,P_an )  )- Q_budget_adj ;% shakiba_3dj_01_2405", "observation": "adjustment is subtracted in the truncation delta calculation"},
        ],
        "semantic_boundary": "source adjustment branch observed; no numeric metric tolerance is inferred",
    },
    {
        "id": "cdr",
        "keyword": "CDR",
        "target_variable": "OP.CDR",
        "assignment_source_line": 9222,
        "assignment": "OP.CDR=xls_parameter(parameter, 'CDR', false, 'MM');% 12/21 from Yuchun Lu to accomdate 'Mod-MM', Defautt is 'MM'",
        "default_kind": "fallback_literal",
        "source_default_literal": "MM",
        "comment_observation": "source comment identifies MM as the default and Mod-MM as an alternate",
        "consumers": [
            {"source_line": 3872, "expression": "switch OP.CDR", "source_line_text": "switch OP.CDR", "observation": "CDR mode selects the cursor recovery branch"},
            {"source_line": 3873, "expression": "case 'Mod-MM'", "source_line_text": "    case 'Mod-MM'", "observation": "Mod-MM uses the modified metric branch"},
            {"source_line": 3876, "expression": "otherwise % MM", "source_line_text": "    otherwise % MM", "observation": "the default/fallback branch is MM"},
        ],
        "semantic_boundary": "source cursor-mode dispatch observed; no CDR lock acceptance or tolerance is inferred",
    },
]
SCOPE = {
    "runtime_implementation": "not_implemented",
    "external_execution": "not_performed",
    "source_helper_resolution": "selected_xls_parameter_contract_resolved",
    "source_parameter_catalog": "selected_five_entries_only",
    "workbook_input_provenance": "not_closed",
    "product_parameter_import": "not_claimed",
}
NON_CLAIMS = [
    "not_runtime_implementation",
    "not_external_oracle",
    "not_full_warning_contract",
    "not_workbook_input_provenance",
    "not_generator_invocation_provenance",
    "not_checkpoint_alignment",
    "not_metric_tolerance",
    "not_duplicate_parameter_policy_complete",
    "not_acceptance",
    "not_release",
]
ABSOLUTE_PATH = re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|\\\\|/(?:home|mnt|Users|private|tmp)/")


class ObservationError(RuntimeError):
    """Raised when the source observation document is not the pinned shape."""


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ObservationError("document_not_mapping")
    return value


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _git_text(source_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=source_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ObservationError("source_git_command_failed") from error
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ObservationError("source_git_text_invalid") from error


def _git_blob(source_root: Path, revision_path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "cat-file", "blob", revision_path],
            cwd=source_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ObservationError("source_git_blob_read_failed") from error
    return result.stdout


def _source_lines(blob: bytes) -> list[str]:
    try:
        return blob.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ObservationError("source_blob_utf8_invalid") from error


def _require_source_line(lines: list[str], line_number: int, expected: str, reason: str) -> None:
    _require(1 <= line_number <= len(lines), f"{reason}:missing")
    _require(lines[line_number - 1] == expected, f"{reason}:mismatch")


def _validate_source_git_object(document: dict[str, Any], source_root: Path) -> None:
    _require(source_root.is_dir(), "source_root_invalid")
    source = document["source"]
    commit = source["commit"]
    resolved_commit = _git_text(source_root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    _require(resolved_commit == commit, "source_commit_mismatch")
    resolved_tree = _git_text(source_root, "rev-parse", "--verify", f"{commit}^{{tree}}")
    _require(resolved_tree == source["tree"], "source_tree_mismatch")

    source_ref = f"{commit}:{source['path']}"
    resolved_source_blob = _git_text(source_root, "rev-parse", "--verify", source_ref)
    _require(resolved_source_blob == source["git_blob_oid_sha1"], "source_blob_mismatch")
    source_blob = _git_blob(source_root, source_ref)
    normalized = source_blob.replace(b"\r\n", b"\n")
    _require(hashlib.sha256(normalized).hexdigest() == source["normalized_content_sha256"], "source_content_sha256_mismatch")
    source_lines = _source_lines(source_blob)

    for entry in document["entries"]:
        _require_source_line(
            source_lines,
            entry["assignment_source_line"],
            entry["assignment"],
            f"assignment_line:{entry['id']}",
        )
        for consumer in entry["consumers"]:
            _require_source_line(
                source_lines,
                consumer["source_line"],
                consumer["source_line_text"],
                f"consumer_line:{entry['id']}:{consumer['source_line']}",
            )

    helper = document["helper_contract"]
    for item in helper["source_lines"]:
        _require_source_line(source_lines, item["line"], item["text"], f"helper_line:{item['line']}")
    for item in document["parameter_input_surface"]["source_lines"]:
        _require_source_line(source_lines, item["line"], item["expression"], f"input_line:{item['line']}")

    reader = document["reader"]
    reader_commit = _git_text(source_root, "rev-parse", "--verify", f"{reader['commit']}^{{commit}}")
    _require(reader_commit == reader["commit"], "reader_commit_mismatch")
    reader_ref = f"{reader['commit']}:{reader['path']}"
    resolved_reader_blob = _git_text(source_root, "rev-parse", "--verify", reader_ref)
    _require(resolved_reader_blob == reader["git_blob_oid_sha1"], "reader_blob_mismatch")
    _git_blob(source_root, reader_ref)


def validate(document: dict[str, Any] | None = None, source_root: Path | str | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(
        set(document)
        == {
            "schema",
            "status",
            "policy",
            "authority",
            "observation_method",
            "audit",
            "source",
            "parameter_input_surface",
            "reader",
            "helper_contract",
            "selection",
            "entries",
            "scope",
            "non_claims",
        },
        "shape_invalid",
    )
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "pinned_source_default_consumption_observed", "status_invalid")
    _require(document.get("policy") == "sipi.p5-02p.source-only-default-consumption.v1", "policy_invalid")
    _require(document.get("authority") == "source_observation_only", "authority_invalid")
    _require(document.get("observation_method") == OBSERVATION_METHOD, "observation_method_invalid")
    _require(document.get("audit") == AUDIT_BINDING, "audit_binding_invalid")
    _require(document.get("source") == SOURCE, "source_identity_invalid")
    _require(document.get("parameter_input_surface") == PARAMETER_INPUT_SURFACE, "input_surface_invalid")
    _require(document.get("reader") == READER, "reader_identity_invalid")
    _require(document.get("helper_contract") == HELPER_CONTRACT, "helper_contract_invalid")
    _require(
        document.get("selection")
        == {
            "objective": "source-backed default and consumer matrix for the MLSE and CDR parameter surface",
            "entry_count": 5,
            "selection_rule": "exact assignment and downstream source call-sites only",
        },
        "selection_invalid",
    )
    _require(document.get("entries") == ENTRIES, "entries_invalid")
    _require(document.get("scope") == SCOPE, "scope_invalid")
    _require(document.get("non_claims") == NON_CLAIMS, "non_claims_invalid")
    _require(not any(ABSOLUTE_PATH.search(value) for value in _walk_strings(document)), "evidence_absolute_path")
    _require(AUDIT.is_file(), "audit_missing")
    audit = AUDIT.read_text(encoding="utf-8")
    _require(not ABSOLUTE_PATH.search(audit), "audit_absolute_path")
    _require(_sha256(AUDIT) == AUDIT_BINDING["sha256"], "audit_hash_mismatch")
    for fragment in (
        SCHEMA,
        SOURCE["commit"],
        SOURCE["git_blob_oid_sha1"],
        "line 10408",
        "provenance statement.",
        "no MATLAB execution",
    ):
        _require(fragment in audit, f"audit_binding:{fragment}")
    source_git_object_checked = False
    if source_root is not None:
        _validate_source_git_object(document, Path(source_root))
        source_git_object_checked = True
    return {
        "schema": SCHEMA,
        "valid": True,
        "entry_count": len(ENTRIES),
        "source_commit": SOURCE["commit"],
        "source_git_object_checked": source_git_object_checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="optional Agent-COM checkout used for pinned Git-object and line verification",
    )
    arguments = parser.parse_args()
    try:
        print(json.dumps(validate(source_root=arguments.source_root), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ObservationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
