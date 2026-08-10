"""Verify the observer-only structural preflight for the selected S2P profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.s2p-matched-observation.v1"
PROFILE_ID = "channel-s2p-channel-16ghz-3db-v1"
SHA1_LENGTH = 40
SHA256_LENGTH = 64


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":") and ".." not in value.split("/")


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=text).stdout


def _load(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("pyyaml_unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("observation_not_object")
    return document


def _parse_s2p(payload: bytes) -> dict[str, Any]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise RuntimeError("s2p_not_utf8") from error
    options = [line.strip() for line in lines if line.lstrip().startswith("#")]
    if len(options) != 1:
        raise RuntimeError("s2p_option_line_invalid")
    tokens = options[0].lstrip("#").split()
    if len(tokens) != 5 or tokens[:4] != ["Hz", "S", "RI", "R"]:
        raise RuntimeError("s2p_option_not_hz_s_ri")
    try:
        z0 = float(tokens[4])
    except ValueError as error:
        raise RuntimeError("s2p_z0_invalid") from error
    if not math.isfinite(z0) or z0 <= 0:
        raise RuntimeError("s2p_z0_invalid")
    rows: list[list[float]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        fields = stripped.split()
        if len(fields) != 9:
            raise RuntimeError("s2p_two_port_row_invalid")
        try:
            row = [float(field) for field in fields]
        except ValueError as error:
            raise RuntimeError("s2p_numeric_invalid") from error
        if not all(math.isfinite(value) for value in row):
            raise RuntimeError("s2p_nonfinite")
        rows.append(row)
    if len(rows) < 2:
        raise RuntimeError("s2p_frequency_count_invalid")
    frequencies = [row[0] for row in rows]
    if frequencies[0] != 0.0 or any(right <= left for left, right in zip(frequencies, frequencies[1:])):
        raise RuntimeError("s2p_frequency_grid_invalid")
    step = frequencies[1] - frequencies[0]
    if step <= 0 or any(not math.isclose(right - left, step, rel_tol=0.0, abs_tol=abs(step) * 1.0e-12) for left, right in zip(frequencies, frequencies[1:])):
        raise RuntimeError("s2p_frequency_grid_nonuniform")
    dc_imaginary = max(abs(rows[0][index]) for index in (2, 4, 6, 8))
    nyquist_imaginary = max(abs(rows[-1][index]) for index in (2, 4, 6, 8))
    return {
        "parameter": "S",
        "format": "RI",
        "frequency_unit": "Hz",
        "port_count": 2,
        "reference_impedance_ohm": z0,
        "frequency_count": len(rows),
        "frequency_start_hz": frequencies[0],
        "frequency_step_hz": step,
        "frequency_stop_hz": frequencies[-1],
        "fft_length": 2 * (len(rows) - 1),
        "sample_interval_seconds": 1.0 / (2 * (len(rows) - 1) * step),
        "dc_nyquist_imaginary_residue_max": max(dc_imaginary, nyquist_imaginary),
    }


def _verify_source(source: dict[str, Any], source_root: Path, blockers: list[str]) -> bytes | None:
    expected = {"canonical_origin", "commit", "tree", "object_format", "path", "git_blob", "content_sha256", "redistribution"}
    if not _exact(source, expected) or not isinstance(source.get("canonical_origin"), str) or not _hex(source.get("commit"), SHA1_LENGTH) or not _hex(source.get("tree"), SHA1_LENGTH) or source.get("object_format") != "sha1" or not _safe_path(source.get("path")) or not _hex(source.get("git_blob"), SHA1_LENGTH) or not _hex(source.get("content_sha256"), SHA256_LENGTH) or source.get("redistribution") != "external_only":
        blockers.append("source_anchor_invalid")
        return None
    try:
        origin = str(_git(source_root, "remote", "get-url", "origin")).strip()
        tree = str(_git(source_root, "rev-parse", f"{source['commit']}^{{tree}}")).strip()
        blob = str(_git(source_root, "rev-parse", f"{source['commit']}:{source['path']}")).strip()
        payload = _git(source_root, "cat-file", "blob", blob, text=False)
    except (OSError, subprocess.CalledProcessError):
        blockers.append("source_git_object_unavailable")
        return None
    if origin != source["canonical_origin"] or tree != source["tree"] or blob != source["git_blob"] or hashlib.sha256(payload).hexdigest() != source["content_sha256"]:
        blockers.append("source_git_object_identity_mismatch")
        return None
    return payload


def _verify_legacy_evidence(evidence: dict[str, Any], sipi_root: Path, blockers: list[str]) -> None:
    expected = {"sipi_commit", "tool_path", "tool_git_blob", "tool_content_sha256", "scope_ref"}
    if not _exact(evidence, expected) or not _hex(evidence.get("sipi_commit"), SHA1_LENGTH) or not _safe_path(evidence.get("tool_path")) or not _hex(evidence.get("tool_git_blob"), SHA1_LENGTH) or not _hex(evidence.get("tool_content_sha256"), SHA256_LENGTH) or not _safe_path(evidence.get("scope_ref")):
        blockers.append("legacy_evidence_invalid")
        return
    try:
        blob = str(_git(sipi_root, "rev-parse", f"{evidence['sipi_commit']}:{evidence['tool_path']}")).strip()
        payload = _git(sipi_root, "cat-file", "blob", blob, text=False)
    except (OSError, subprocess.CalledProcessError):
        blockers.append("legacy_evidence_unavailable")
        return
    if blob != evidence["tool_git_blob"] or hashlib.sha256(payload).hexdigest() != evidence["tool_content_sha256"]:
        blockers.append("legacy_evidence_identity_mismatch")


def verify_document(document: object, source_root: Path, *, sipi_root: Path = ROOT) -> dict[str, Any]:
    blockers: list[str] = []
    expected = {"schema", "selection", "source", "legacy_handoff_evidence", "product_contract", "structural_expectation", "numerical_acceptance", "non_claims"}
    if not _exact(document, expected) or document.get("schema") != SCHEMA:
        return {"valid": False, "comparison_ready": False, "blockers": ["observation_schema_invalid"]}
    if document.get("selection") != {"profile_id": PROFILE_ID, "required": True, "required_by": document.get("selection", {}).get("required_by") if isinstance(document.get("selection"), dict) else None, "status": "required_pending_preflight"} or not isinstance(document["selection"].get("required_by"), str) or not document["selection"]["required_by"]:
        blockers.append("selection_invalid")
    payload = _verify_source(document["source"], source_root, blockers) if isinstance(document.get("source"), dict) else None
    if isinstance(document.get("legacy_handoff_evidence"), dict):
        _verify_legacy_evidence(document["legacy_handoff_evidence"], sipi_root, blockers)
    else:
        blockers.append("legacy_evidence_invalid")
    expected_contract = {"schema": "sipi.channel.s2p-matched.v1", "port_order": ["source_port_1", "receiver_port_2"], "wave_convention": "real_z0_power_wave", "transfer": "receiver_voltage_per_launched_source_voltage_equals_s21", "output_sign": "receiver_port_voltage_relative_to_reference"}
    if document.get("product_contract") != expected_contract:
        blockers.append("product_contract_invalid")
    expected_numerical = {"status": "blocked_missing_stimulus_policy", "required_before_compare": ["launch waveform and amplitude contract", "external resolver executable and configuration identity", "output observable/alignment and numerical tolerance policy"]}
    if document.get("numerical_acceptance") != expected_numerical:
        blockers.append("numerical_boundary_invalid")
    if not isinstance(document.get("non_claims"), list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("non_claims_invalid")
    observed: dict[str, Any] | None = None
    if payload is not None:
        try:
            observed = _parse_s2p(payload)
        except RuntimeError as error:
            blockers.append(str(error))
        else:
            expected_structure = document.get("structural_expectation")
            if not isinstance(expected_structure, dict) or set(expected_structure) != set(observed) or any(not math.isclose(float(observed[key]), float(expected_structure[key]), rel_tol=0.0, abs_tol=1.0e-12 * max(1.0, abs(float(observed[key])))) if isinstance(observed[key], float) else observed[key] != expected_structure[key] for key in observed):
                blockers.append("structural_observation_mismatch")
            elif observed["dc_nyquist_imaginary_residue_max"] > 1.0e-12:
                blockers.append("dc_nyquist_imaginary_residue_exceeds_policy")
    return {"valid": not blockers, "profile_id": PROFILE_ID, "required": True, "structural_preflight": "passed" if not blockers else "rejected", "comparison_ready": False, "numerical_acceptance_status": "blocked_missing_stimulus_policy", "observed_structure": observed, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", type=Path, default=ROOT / "docs" / "baselines" / "channel-s2p-matched-observation.v1.yaml")
    parser.add_argument("--pybert-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = verify_document(_load(arguments.observation), arguments.pybert_root)
    except (OSError, RuntimeError) as error:
        report = {"valid": False, "comparison_ready": False, "blockers": [str(error)]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
