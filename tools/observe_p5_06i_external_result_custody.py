# -*- coding: utf-8 -*-
"""Observe the external COM result MAT files without invoking MATLAB.

This is a custody observer, not a COM runner.  It reads the four ignored
16-Aug-2026 result MAT files in the externally authorized ``COM`` checkout,
records their byte hashes and MATLAB v5 variable surface, and computes stable
digests for the complete ``OP``/``param`` input payload and ``output_args``
payload.  The resulting record is deliberately partial: the historical
``matlab_oracle.mat`` and warning/summary artifacts are not reconstructed from
hashes or from the CSV projection.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable

import numpy as np
from scipy.io import loadmat, whosmat
from scipy.io.matlab import mat_struct
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COM_ROOT = Path(os.environ.get("SIPI_COM_ROOT", str(ROOT.parent / "COM")))
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
CANONICAL = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06i-external-result-custody.v1.yaml"
SCHEMA = "sipi.p5-06i.external-result-custody.v1"
CANONICAL_ORIGIN = "https://github.com/z331225718/agent-com.git"
CANONICALIZER_SCHEMA = "sipi.p5-06i.mat-payload-canonical-json.v1"
RESULT_RELATIVE = Path("results") / "100GEL_C2M_host_16-Aug-2026"
EXPECTED_RESULT_FILES = {
    "C2M_eval_ fixtures--thru_case1_results.mat": ("4735668ec3731e2181d594f54f308dbbbbfd0e7885bfdd1c780ab0d222a74c7e", 9219),
    "C2M_eval_ fixtures--thru_case1_results.csv": ("761205c8fa02a256841a0fa0d834121c2046a3028411fc3630eee546d4cd6f64", 7611),
    "C2M_eval_ fixtures--thru_case2_results.mat": ("bcfb14b506eb481586ea6651b7c1f0f4d59845e2ee37c98e3916baa36fe7b69f", 9263),
    "C2M_eval_ fixtures--thru_case2_results.csv": ("2d1f307bbaa3c70ab66b2845f95b9b226c1c8fc558b31ef31d15ff1ed0c7172e", 7574),
    "C2M_eval_ synthetic--thru_10db_at_26p56ghz_case1_results.mat": ("bf79a0dfeb4c4d10e7f3844e0b59ef33947d247866348d7b6359d881595d066e", 9265),
    "C2M_eval_ synthetic--thru_10db_at_26p56ghz_case1_results.csv": ("73360aa8ec2e69f460db32435e35702d5fe05778ba7923b0443a331517b48014", 7667),
    "C2M_eval_ synthetic--thru_10db_at_26p56ghz_case2_results.mat": ("0c86b467addbf0c729f0541abbdbe9d87d27ce0828974222f10c9ce7ca0798a1", 9311),
    "C2M_eval_ synthetic--thru_10db_at_26p56ghz_case2_results.csv": ("50c93639f0b3b8b5caec0c45d15c0e4051638315531c5f8fab67f61acf7f3652", 7630),
}
REQUIRED_VARIABLES = ("output_args", "OP", "param")
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
CHECKPOINT_FIELDS = (
    "TXLE_taps",
    "DFE_taps",
    "tail_RSS",
    "sigma_N",
    "itick",
    "sgm_Ani__isi_xt_noise",
)
NORMALIZED_INPUT_FIELDS = (
    "fb",
    "max_start_freq",
    "ndfe",
    "specBER",
    "f_r",
    "snpPortsOrder",
    "ui",
    "sample_dt",
    "base",
)
MATERIAL_IDS = (
    "com-r480-matlab-source",
    "com-r480-config-120g-c2m",
    "com-synthetic-thru",
    "com-synthetic-fext",
    "com-synthetic-next",
    "com-synthetic-manifest",
)
NEEDS_ORACLE_EXPRESSIONS = {
    "param.fb": lambda param, op: _scalar(param, "fb"),
    "OP.GET_FD": lambda param, op: _scalar(op, "GET_FD"),
    "param.max_start_freq/1e9": lambda param, op: _scalar(param, "max_start_freq") / 1e9,
    "param.fb/1e9": lambda param, op: _scalar(param, "fb") / 1e9,
    "param.fb/4": lambda param, op: _scalar(param, "fb") / 4,
    "param.ndfe": lambda param, op: _scalar(param, "ndfe"),
    "2*param.specBER": lambda param, op: 2 * _scalar(param, "specBER"),
    "OP.PMD_type": lambda param, op: _scalar(op, "PMD_type"),
    "param.fb*param.f_r": lambda param, op: _scalar(param, "fb") * _scalar(param, "f_r"),
    "param.fb/2": lambda param, op: _scalar(param, "fb") / 2,
    "OP.TDMODE": lambda param, op: _scalar(op, "TDMODE"),
}


class ObservationError(RuntimeError):
    """Raised when external custody cannot be observed or verified."""


def _scalar(struct: Any, field: str) -> Any:
    if not hasattr(struct, field):
        raise ObservationError(f"missing_struct_field:{field}")
    value = getattr(struct, field)
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise ObservationError(f"non_scalar_default_source:{field}")
        value = value.reshape(-1)[0]
    if isinstance(value, np.generic):
        value = value.item()
    return value


def _number(value: Any) -> Any:
    """Return JSON-safe exact scalar markers, including NaN/Inf/complex."""

    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if np.isnan(value):
            return {"kind": "nan"}
        if np.isposinf(value):
            return {"kind": "inf", "sign": 1}
        if np.isneginf(value):
            return {"kind": "inf", "sign": -1}
        return value
    if isinstance(value, complex):
        return {"kind": "complex", "real": _number(value.real), "imag": _number(value.imag)}
    return value


def canonicalize(value: Any) -> Any:
    """Canonicalize scipy MAT values without dropping shape, dtype, or order."""

    if isinstance(value, mat_struct):
        fields = getattr(value, "_fieldnames", None)
        if not isinstance(fields, list):
            raise ObservationError("mat_struct_fields_missing")
        return {
            "kind": "mat_struct",
            "fields": {field: canonicalize(getattr(value, field)) for field in sorted(fields)},
        }
    if isinstance(value, np.ndarray):
        flattened = value.reshape(-1, order="C")
        return {
            "kind": "ndarray",
            "dtype": str(value.dtype),
            "shape": [int(dim) for dim in value.shape],
            "values": [canonicalize(item) for item in flattened],
        }
    if isinstance(value, np.generic):
        return canonicalize(value.item())
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    if isinstance(value, (bool, int, float, complex, str)):
        return _number(value)
    if isinstance(value, bytes):
        return {"kind": "bytes", "hex": value.hex()}
    if value is None:
        return None
    raise ObservationError(f"unsupported_mat_value:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(canonicalize(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _require_expected_result_identity(path: Path) -> None:
    expected = EXPECTED_RESULT_FILES.get(path.name)
    if expected is None:
        raise ObservationError("unexpected_result_file:" + path.name)
    expected_hash, expected_length = expected
    if path.stat().st_size != expected_length or sha256_file(path) != expected_hash:
        raise ObservationError("result_file_identity_drift:" + path.name)


def _posix(path: Path) -> str:
    return path.as_posix()


def _relative_to_com(com_root: Path, path: Path) -> str:
    try:
        return _posix(path.resolve().relative_to(com_root.resolve()))
    except ValueError as error:
        raise ObservationError("external_material_outside_checkout") from error


def _git(com_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(com_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ObservationError("git_query_failed:" + " ".join(args))
    return result.stdout.strip()


def _source_identity(com_root: Path) -> dict[str, Any]:
    origin = _git(com_root, "config", "--get", "remote.origin.url")
    object_format = _git(com_root, "rev-parse", "--show-object-format")
    if origin != CANONICAL_ORIGIN:
        raise ObservationError("canonical_origin_mismatch")
    if object_format != "sha1":
        raise ObservationError("object_format_mismatch")
    commit = _git(com_root, "rev-parse", "HEAD")
    return {
        "canonical_origin": origin,
        "object_format": object_format,
        "commit": commit,
        "tree": _git(com_root, "rev-parse", f"{commit}^{{tree}}"),
        "worktree_status_at_observation": _git(com_root, "status", "--porcelain"),
    }


def _registry_materials(com_root: Path) -> list[dict[str, Any]]:
    try:
        registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ObservationError("registry_unreadable") from error
    by_id = {item.get("id"): item for item in registry.get("materials", []) if isinstance(item, dict)}
    observed: list[dict[str, Any]] = []
    for material_id in MATERIAL_IDS:
        item = by_id.get(material_id)
        if item is None:
            raise ObservationError("registry_material_missing:" + material_id)
        raw_path = str(item["path"]).replace("/", "\\")
        path = Path(raw_path)
        if not path.is_absolute():
            path = com_root / path
        if not path.is_file():
            raise ObservationError("registered_material_missing:" + material_id)
        actual_hash = sha256_file(path)
        actual_length = path.stat().st_size
        if actual_hash.lower() != str(item["sha256"]).lower() or actual_length != int(item["byte_length"]):
            raise ObservationError("registered_material_hash_drift:" + material_id)
        observed.append({
            "id": material_id,
            "logical_name": item["logical_name"],
            "kind": item["kind"],
            "logical_root": "external_com_checkout",
            "relative_to_root": _relative_to_com(com_root, path),
            "sha256": actual_hash,
            "byte_length": actual_length,
            "registry_sha256": str(item["sha256"]).lower(),
            "identity_status": "matched_record",
        })
    return observed


def _mat_header(path: Path) -> dict[str, Any]:
    header = path.read_bytes()[:116]
    text = header.decode("ascii", errors="replace").rstrip(" \x00")
    if not text.startswith("MATLAB 5.0 MAT-file"):
        raise ObservationError("not_matlab_v5:" + path.name)
    created = re.search(r"Created on: (.+)$", text)
    created_text = created.group(1).strip() if created else None
    return {
        "format": "MATLAB 5.0 MAT-file",
        "platform_header": text,
        "created_on_header": created_text,
    }


def _scalar_observation(value: Any) -> dict[str, Any]:
    canonical = canonicalize(value)
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return {"kind": "empty", "shape": [int(dim) for dim in value.shape]}
        if value.size != 1:
            return {"kind": "array", "shape": [int(dim) for dim in value.shape], "digest": digest(value)}
        value = value.reshape(-1)[0]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        if np.isnan(value):
            return {"kind": "nan"}
        if np.isposinf(value):
            return {"kind": "inf", "sign": 1}
        if np.isneginf(value):
            return {"kind": "inf", "sign": -1}
        return {"kind": "finite", "value": value}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, complex):
        return {"kind": "complex", "value": canonical}
    return {"kind": "value", "value": canonical}


def _array_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, np.ndarray):
        return _scalar_observation(value)
    return {
        "shape": [int(dim) for dim in value.shape],
        "dtype": str(value.dtype),
        "digest": digest(value),
        "values": [
            _scalar_observation(item) for item in value.reshape(-1, order="C")
        ] if value.size <= 16 else None,
    }


def _field_observation(value: Any) -> dict[str, Any]:
    return _array_observation(value) if isinstance(value, np.ndarray) else _scalar_observation(value)


def _port_order_text(value: Any) -> str:
    if not isinstance(value, np.ndarray):
        raise ObservationError("port_order_not_array")
    values = value.reshape(-1, order="C")
    return "[ " + " ".join(str(int(item)) for item in values) + " ]"


def _redacted_config_file(value: Any) -> dict[str, Any]:
    observed = _scalar_observation(value)
    if observed.get("kind") != "string":
        return observed
    raw = str(observed["value"])
    normalized = raw.replace("\\", "/")
    is_absolute = bool(re.match(r"^(?:[A-Za-z]:/|/|//)", normalized))
    if not is_absolute:
        return observed
    basename = normalized.rsplit("/", 1)[-1]
    domain_digest = hashlib.sha256(
        b"sipi.p5-06i.config-file.v1\0external_com_checkout\0" + raw.encode("utf-8")
    ).hexdigest()
    return {
        "kind": "redacted_absolute_path",
        "domain": "external_com_checkout",
        "basename": basename,
        "sha256_domain_separated": domain_digest,
    }


def _selected_fields(struct: Any, fields: Iterable[str], arrays: bool = False) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for field in fields:
        if not hasattr(struct, field):
            selected[field] = {"kind": "missing"}
        else:
            value = getattr(struct, field)
            selected[field] = _array_observation(value) if arrays else _scalar_observation(value)
    return selected


def _csv_contract(com_root: Path, csv_path: Path, output_fields: list[str]) -> dict[str, Any]:
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        raise ObservationError("csv_unreadable:" + csv_path.name) from error
    header = rows[0] if rows else []
    return {
        "logical_root": "external_com_checkout",
        "relative_to_root": _relative_to_com(com_root, csv_path),
        "sha256": sha256_file(csv_path),
        "byte_length": csv_path.stat().st_size,
        "header_count": len(header),
        "row_count": max(0, len(rows) - 1),
        "header_matches_output_fields": header == output_fields,
        "payload_role": "rounded_text_projection_not_exact_payload",
    }


def _case_identity(mat_path: Path) -> dict[str, Any]:
    match = re.search(r"_case(?P<index>[0-9]+)_results\.mat$", mat_path.name)
    if match is None:
        raise ObservationError("case_identity_missing:" + mat_path.name)
    family = "synthetic" if "synthetic" in mat_path.stem else "fixtures" if "fixtures" in mat_path.stem else "unknown"
    if family == "unknown":
        raise ObservationError("case_family_unknown:" + mat_path.name)
    index = int(match.group("index"))
    return {"family": family, "index": index, "id": f"{family}_case{index}"}


def _default_resolution(canonical: dict[str, Any], param: Any, op: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in sorted(canonical["keys"]):
        defaults = canonical["keys"][key].get("defaults", [])
        for occurrence, default in enumerate(defaults):
            if default.get("kind") != "needs_matlab_oracle":
                continue
            expression = str(default.get("expression"))
            evaluator = NEEDS_ORACLE_EXPRESSIONS.get(expression)
            if evaluator is None:
                raise ObservationError("unapproved_default_expression:" + expression)
            value = evaluator(param, op)
            entries.append({
                "key": key,
                "occurrence": occurrence,
                "expression": expression,
                "required": str(default.get("required")),
                "observed_value": _scalar_observation(value),
                "status": "observed_resolved_for_this_mat_payload",
            })
    if len(entries) != int(canonical.get("needs_oracle_calls", -1)):
        raise ObservationError("default_resolution_count_drift")
    return entries


def _payload_record(com_root: Path, mat_path: Path, canonical: dict[str, Any]) -> dict[str, Any]:
    csv_path = mat_path.with_suffix(".csv")
    if not csv_path.is_file():
        raise ObservationError("csv_pair_missing:" + mat_path.name)
    # scipy receives only the eight exact, small files frozen by this observer.
    _require_expected_result_identity(mat_path)
    _require_expected_result_identity(csv_path)
    header = _mat_header(mat_path)
    variables = whosmat(str(mat_path))
    variable_inventory = [
        {"name": name, "shape": [int(dim) for dim in shape], "class": class_name}
        for name, shape, class_name in variables
    ]
    names = [entry["name"] for entry in variable_inventory]
    if set(names) != set(REQUIRED_VARIABLES) or len(names) != len(REQUIRED_VARIABLES):
        raise ObservationError("mat_variable_inventory_invalid:" + mat_path.name)
    loaded = loadmat(str(mat_path), squeeze_me=True, struct_as_record=False)
    output = loaded["output_args"]
    op = loaded["OP"]
    param = loaded["param"]
    output_field_order = list(getattr(output, "_fieldnames", []))
    output_fields = sorted(output_field_order)
    op_fields = sorted(getattr(op, "_fieldnames", []))
    param_fields = sorted(getattr(param, "_fieldnames", []))
    normalized = {"OP": op, "param": param}
    output_payload = output
    checkpoint_values = {field: getattr(output, field) for field in CHECKPOINT_FIELDS if hasattr(output, field)}
    metrics = _selected_fields(output, METRIC_FIELDS)
    checkpoints = _selected_fields(output, CHECKPOINT_FIELDS, arrays=True)
    defaults = _default_resolution(canonical, param, op)
    normalized_selected = {
        field: _field_observation(getattr(param, field)) if hasattr(param, field) else {"kind": "missing"}
        for field in NORMALIZED_INPUT_FIELDS
    }
    normalized_selected.update({
        "GET_FD": _scalar_observation(getattr(op, "GET_FD")) if hasattr(op, "GET_FD") else {"kind": "missing"},
        "TDMODE": _scalar_observation(getattr(op, "TDMODE")) if hasattr(op, "TDMODE") else {"kind": "missing"},
        "PMD_type": _scalar_observation(getattr(op, "PMD_type")) if hasattr(op, "PMD_type") else {"kind": "missing"},
    })
    return {
        "case_identity": _case_identity(mat_path),
        "mat": {
            "logical_root": "external_com_checkout",
            "relative_to_root": _relative_to_com(com_root, mat_path),
            "sha256": sha256_file(mat_path),
            "byte_length": mat_path.stat().st_size,
            "header": header,
            "registry_status": "not_in_authorized_material_registry_external_observation",
        },
        "csv": _csv_contract(com_root, csv_path, output_field_order),
        "variable_inventory": variable_inventory,
        "field_counts": {
            "output_args": len(output_fields),
            "OP": len(op_fields),
            "param": len(param_fields),
        },
        "field_names_sha256": {
            "output_args": digest(output_fields),
            "OP": digest(op_fields),
            "param": digest(param_fields),
        },
        "payload_digests": {
            "normalized_input_op_param_sha256": digest(normalized),
            "output_args_sha256": digest(output_payload),
            "full_mat_payload_sha256": digest({"OP": op, "param": param, "output_args": output}),
        },
        "observed_identity": {
            "code_revision": _scalar_observation(getattr(output, "code_revision")),
            "config_file": _redacted_config_file(getattr(output, "config_file")),
            "file_names": _scalar_observation(getattr(output, "file_names")),
            "base": _scalar_observation(getattr(param, "base")),
        },
        "normalized_input_surface": {
            "canonical_key_count": int(canonical.get("key_count", -1)),
            "selected_fields": normalized_selected,
        "port_order_observed": _port_order_text(getattr(param, "snpPortsOrder")),
            "normalized_input_digest_status": "bound_to_complete_OP_and_param_payload",
        },
        "default_resolution": {
            "canonical_ref": "docs/baselines/p5-r480-canonical-parameter-json.v2.yaml",
            "needs_oracle_occurrence_count": len(defaults),
            "entries": defaults,
            "contract_status": "observed_values_only_not_generic_default_contract",
        },
        "metrics": {
            "fields": metrics,
            "metric_digest": digest({field: getattr(output, field) for field in METRIC_FIELDS if hasattr(output, field)}),
        },
        "checkpoints": {
            "fields": checkpoints,
            "checkpoint_digest": digest(checkpoint_values),
            "tolerance_status": "missing",
        },
    }


def _load_canonical() -> dict[str, Any]:
    try:
        canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ObservationError("canonical_reference_unreadable") from error
    if not isinstance(canonical, dict) or canonical.get("schema") != "sipi.p5-02.canonical-parameter-json.v2":
        raise ObservationError("canonical_reference_invalid")
    return canonical


def observe(com_root: Path = DEFAULT_COM_ROOT) -> dict[str, Any]:
    com_root = com_root.resolve()
    result_dir = com_root / RESULT_RELATIVE
    if not result_dir.is_dir():
        raise ObservationError("result_directory_missing")
    canonical = _load_canonical()
    source_identity = _source_identity(com_root)
    materials = _registry_materials(com_root)
    mat_paths = sorted(result_dir.glob("*.mat"))
    if len(mat_paths) != 4:
        raise ObservationError("expected_four_result_mat_files")
    payloads = [_payload_record(com_root, path, canonical) for path in mat_paths]
    payloads.sort(key=lambda item: item["mat"]["relative_to_root"])
    output_field_counts = {p["field_counts"]["output_args"] for p in payloads}
    if output_field_counts != {98} or any(p["field_counts"]["OP"] != 95 or p["field_counts"]["param"] != 177 for p in payloads):
        raise ObservationError("unexpected_result_field_counts")
    c4_values = []
    for payload in payloads:
        metrics = payload["metrics"]["fields"]
        c4_values.append({
            "case_identity": payload["case_identity"],
            "COM_dB": metrics["COM_dB"],
            "ICN_mV": metrics["ICN_mV"],
            "ERL": metrics["ERL"],
        })
    return {
        "schema": SCHEMA,
        "status": "external_result_payload_observed_not_authoritative",
        "purpose": "Hash-bound observation of ignored external COM 16-Aug-2026 result MAT/CSV pairs; complete OP/param payload digests and observed default/checkpoint/metric surfaces are recorded without MATLAB invocation or product promotion.",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "external_source": {
            "logical_root": "external_com_checkout",
            "identity": source_identity,
            "result_relative": _posix(RESULT_RELATIVE),
            "matlab_invoked": False,
            "matlab_invocation_authorized": False,
            "result_generator_commit_verified": False,
            "embedded_code_revision_authority": "self_declared_only",
            "ignored_outputs_git_object_bound": False,
        },
        "registered_materials": materials,
        "canonical_input": {
            "ref": "docs/baselines/p5-r480-canonical-parameter-json.v2.yaml",
            "key_count": int(canonical.get("key_count", -1)),
            "statically_evaluated_calls": int(canonical.get("statically_evaluated_calls", -1)),
            "needs_oracle_calls": int(canonical.get("needs_oracle_calls", -1)),
            "source_sha256": str(canonical.get("source_sha256", "")).lower(),
        },
        "canonicalization": {
            "schema": CANONICALIZER_SCHEMA,
            "hash": "sha256",
            "json": "UTF-8, sort_keys=true, separators=(',', ':'), allow_nan=false",
            "mat_struct_fields": "sorted",
            "ndarray": "dtype+shape+flattened_C_order_values",
            "nonfinite": "explicit_nan_or_inf_markers",
        },
        "payload_count": len(payloads),
        "payloads": payloads,
        "aggregate_observed_metric_surface": {
            "c4_fields": ["COM_dB", "ICN_mV", "ERL"],
            "payload_values": c4_values,
            "digest": digest(c4_values),
            "required_acceptance_metric_ids": ["com_db", "erl_db", "td_iln_db"],
            "scope_status": "incomplete_tdiln_and_tolerance_policy_missing",
        },
        "warning_contract": {
            "exact_run_warning_report_status": "missing",
            "source_static_warning_inventory_ref": "docs/baselines/p5-r480-warning-observation.v1.yaml",
            "source_static_warning_call_count": 25,
            "source_static_warning_inventory_digest": "99acc4cb75d7f31e84d4e75f72a5f343e361ae87b72af815baf3d8a60f553078",
            "full_mlse_der_cdr_contract": "missing",
        },
        "reference_artifact_payload": {
            "observed": ["case_result_mat_files", "case_result_csv_projections", "OP_struct", "param_struct", "output_args_struct"],
            "missing": ["exact_matlab_oracle.mat", "exact_summary.json", "run_warning_report", "checkpoint_tolerances", "full_metric_tolerance_and_alignment_policy"],
            "status": "partial_payload_only",
        },
        "non_claims": [
            "not_a_MATLAB_invocation",
            "not_a_product_oracle",
            "not_a_product_compare",
            "not_acceptance_evidence",
            "not_release_evidence",
            "not_a_generic_default_contract",
            "not_a_warning_contract",
            "result_generator_commit_unverified",
            "embedded_code_revision_self_declared",
            "ignored_outputs_not_git_object_bound",
            "observer_limited_to_eight_exact_hash_and_length_bound_files",
        ],
    }


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ObservationError("evidence_not_mapping")
    return value


def verify(com_root: Path = DEFAULT_COM_ROOT, evidence_path: Path = EVIDENCE) -> dict[str, Any]:
    evidence = _read_yaml(evidence_path)
    expected = observe(com_root)
    if evidence != expected:
        raise ObservationError("evidence_drift")
    if evidence.get("status") != "external_result_payload_observed_not_authoritative":
        raise ObservationError("evidence_status_invalid")
    return {
        "schema": SCHEMA,
        "status": "external_result_custody_verified",
        "payload_count": evidence["payload_count"],
        "source_commit": evidence["external_source"]["identity"]["commit"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--com-root", type=Path, default=DEFAULT_COM_ROOT)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.write_evidence:
            evidence = observe(arguments.com_root)
            with arguments.evidence.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(yaml.safe_dump(evidence, sort_keys=False, allow_unicode=False))
            result = {
                "schema": SCHEMA,
                "status": "external_result_custody_written",
                "evidence": _posix(arguments.evidence.resolve().relative_to(ROOT)),
            }
        elif arguments.verify:
            result = verify(arguments.com_root, arguments.evidence)
        else:
            result = observe(arguments.com_root)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, ObservationError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
