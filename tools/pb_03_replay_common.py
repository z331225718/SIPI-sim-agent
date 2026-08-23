"""Shared immutable replay helpers for the PB-03..PB-05 Rust leaves.

The helper intentionally treats any missing executable, failed oracle, payload
shape error, or mismatch as blocked.  It never upgrades a wrapper exit code to
numeric parity.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PB03_PARITY_ARRAYS = (
    "ber_auto_correlation.npy",
    "ber_error_indices.npy",
    "ber_observed_bits.npy",
    "ber_reference_bits.npy",
    "channel_impulse_v_per_v.npy",
    "channel_output_v.npy",
    "ctle_output_v.npy",
    "dfe_bits.npy",
    "dfe_clock_times_s.npy",
    "dfe_clocks.npy",
    "dfe_decision_scalers_v.npy",
    "dfe_decisions.npy",
    "dfe_locked.npy",
    "dfe_output_v.npy",
    "dfe_signal_samples_v.npy",
    "dfe_tap_weights_v.npy",
    "dfe_ui_estimates_s.npy",
    "legacy_channel_frequency_hz.npy",
    "legacy_channel_raw_im.npy",
    "legacy_channel_raw_re.npy",
    "legacy_channel_terminated_im.npy",
    "legacy_channel_terminated_re.npy",
    "legacy_channel_trimmed_im.npy",
    "legacy_channel_trimmed_re.npy",
    "legacy_stage_ctle_im.npy",
    "legacy_stage_ctle_out_im.npy",
    "legacy_stage_ctle_out_re.npy",
    "legacy_stage_ctle_re.npy",
    "legacy_stage_dfe_im.npy",
    "legacy_stage_dfe_out_im.npy",
    "legacy_stage_dfe_out_re.npy",
    "legacy_stage_dfe_re.npy",
    "legacy_stage_tx_im.npy",
    "legacy_stage_tx_out_im.npy",
    "legacy_stage_tx_out_re.npy",
    "legacy_stage_tx_re.npy",
    "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy",
    "rx_input_v.npy",
    "rx_output_v.npy",
    "symbols_v.npy",
    "time_s.npy",
    "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def git(repo: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def archive_repo(repo: Path, commit: str, destination: Path) -> dict[str, Any]:
    payload = bytes(git(repo, "archive", "--format=tar", commit, raw=True))
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        root = destination.resolve()
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            archive.extract(member, destination)
    resolved = str(git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    return {"commit": resolved, "tree": tree, "archive_sha256": sha256(payload)}


def _tool(executable: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    version = subprocess.run([str(executable), *version_args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    return {
        "role": role,
        "executable": executable.name,
        "path_redacted": True,
        "file_sha256": sha256(executable.read_bytes()),
        "version_exit_code": version.returncode,
        "version_output_sha256": sha256(version.stdout + b"\x00" + version.stderr),
    }


def resolve_executable(value: str) -> Path | None:
    candidates = []
    located = shutil.which(value)
    if located:
        candidates.append(Path(located))
    if value in {"cargo", "rustc", "rustup"}:
        cargo_bin = Path.home() / ".cargo" / "bin"
        candidates.extend((cargo_bin / value, cargo_bin / f"{value}.exe"))
    candidates.append(Path(value))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve_toolchain(timeout: int) -> tuple[dict[str, Any], dict[str, Path]]:
    """Resolve, hash, and version every tool once before a replay starts."""
    specs = {
        "cargo": ("cargo", ("-Vv",)),
        "rustc": ("rustc", ("-Vv",)),
        "uv": ("uv", ("--version",)),
        "python": ("python", ("--version",)),
    }
    report: dict[str, Any] = {"timeout_seconds": timeout}
    paths: dict[str, Path] = {}
    for role, (value, version_args) in specs.items():
        executable = resolve_executable(value)
        if executable is None:
            raise RuntimeError(f"{role} executable is unavailable")
        paths[role] = executable
        report[role] = _tool(executable, role, version_args)
    return report, paths


def toolchain(timeout: int) -> dict[str, Any]:
    """Compatibility wrapper for callers that only need the report."""
    report, _ = resolve_toolchain(timeout)
    return report


def fixture_info(root: Path, relative: str, fallback: Path | None = None) -> dict[str, Any]:
    path = root / relative
    archive_present = path.is_file()
    if not archive_present and fallback is not None:
        path = fallback
    payload = path.read_bytes()
    return {"path": relative, "bytes": len(payload), "sha256": sha256(payload), "archive_present": archive_present}


def npy_summary(payload: bytes) -> dict[str, Any]:
    if payload[:6] != b"\x93NUMPY":
        raise ValueError("NPZ member is not NPY")
    major = payload[6]
    header_offset = 10 if major == 1 else 12
    header_size = int.from_bytes(payload[8:header_offset], "little")
    end = header_offset + header_size
    header = ast.literal_eval(payload[header_offset:end].decode("latin1").strip())
    if not isinstance(header, dict) or header.get("descr") not in ("<f8", "|f8", ">f8"):
        raise ValueError("NPY member is not float64")
    shape = tuple(int(value) for value in header.get("shape", ()))
    count = math.prod(shape)
    raw = payload[end:]
    if len(raw) != count * 8:
        raise ValueError("NPY payload length mismatch")
    if header["descr"] == ">f8":
        raw = b"".join(raw[index : index + 8][::-1] for index in range(0, len(raw), 8))
    return {"count": count, "dtype": header["descr"], "shape": list(shape), "fortran_order": bool(header.get("fortran_order")), "f64_sha256": sha256(raw)}


def npz_summary(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    members: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.endswith(".npy"):
                continue
            members[info.filename] = npy_summary(archive.read(info))
    return {"sha256": sha256(payload), "bytes": len(payload), "logical_members": dict(sorted(members.items())), "logical_sha256": sha256(canonical(dict(sorted(members.items()))))}


def artifact_summary(output: Path) -> dict[str, Any]:
    meta = output / "meta.json"
    arrays = output / "arrays.npz"
    result: dict[str, Any] = {"meta_present": meta.is_file(), "arrays_present": arrays.is_file()}
    if meta.is_file():
        payload = meta.read_bytes()
        result["meta_sha256"] = sha256(payload)
        try:
            value = json.loads(payload.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["meta_json_valid"] = False
        else:
            result["meta_json_valid"] = isinstance(value, dict)
            result["meta_schema"] = value.get("schema") if isinstance(value, dict) else None
            result["meta_payload_sha256"] = sha256(canonical(value))
            if isinstance(value, dict):
                result["selection"] = selection_summary(value)
                result["comparison"] = comparison_summary(value)
    if arrays.is_file():
        try:
            result["arrays"] = npz_summary(arrays)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            result["arrays_error"] = type(error).__name__
    return result


def selection_summary(value: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only the stable engine-selection contract, never host paths."""
    candidates: list[Any] = []
    for container in (value.get("diagnostics"), value.get("engine_diagnostics")):
        if isinstance(container, dict):
            candidates.append(container.get("engine_selection"))
    for item in candidates:
        if not isinstance(item, dict):
            continue
        gate = item.get("parity_gate")
        return {
            "requested": item.get("requested"),
            "selected": item.get("selected"),
            "fallback_reason": item.get("fallback_reason"),
            "implementation": item.get("implementation"),
            "rust_only": item.get("rust_only"),
            "parity_gate": {
                "version": gate.get("version"),
                "status": gate.get("status"),
                "reason": gate.get("reason"),
            }
            if isinstance(gate, dict)
            else None,
        }
    return None


def comparison_summary(value: dict[str, Any]) -> dict[str, Any] | None:
    """Summarize compare semantics without reducing them to process status."""
    diagnostics = value.get("diagnostics")
    comparison = diagnostics.get("comparison") if isinstance(diagnostics, dict) else None
    if not isinstance(comparison, dict):
        return None
    arrays = comparison.get("arrays")
    metrics = comparison.get("metrics")
    metadata = comparison.get("metadata")
    details: dict[str, Any] = {
        "schema": comparison.get("schema"),
        "passed": comparison.get("passed"),
        "status_only_comparison": comparison.get("status_only_comparison"),
        "arrays_passed": arrays.get("passed") if isinstance(arrays, dict) else None,
        "metrics_passed": metrics.get("passed") if isinstance(metrics, dict) else None,
        "metadata_passed": metadata.get("passed") if isinstance(metadata, dict) else None,
        "reason": comparison.get("reason"),
        "reference_required": comparison.get("reference_required"),
        "source": (diagnostics.get("compare_reference") or {}).get("source")
        if isinstance(diagnostics.get("compare_reference"), dict)
        else None,
    }
    return details


def run_command(command: list[str], cwd: Path, timeout: int, tool_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    resolved = list(command)
    environment = os.environ.copy()
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir():
        environment["PATH"] = str(cargo_bin) + os.pathsep + environment.get("PATH", "")
    # Never inherit wrapper state from the host and make the selected compiler
    # explicit for every Cargo invocation.
    environment.pop("RUSTC_WRAPPER", None)
    environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    if tool_paths is not None and "rustc" in tool_paths:
        environment["RUSTC"] = str(tool_paths["rustc"])
    if resolved and resolved[0] in {"cargo", "rustc", "uv", "python"}:
        executable = tool_paths.get(resolved[0]) if tool_paths is not None else resolve_executable(resolved[0])
        if executable is None:
            return {"exit_code": None, "error": f"{resolved[0]} executable unavailable", "stdout_sha256": None, "stderr_sha256": None}
        resolved[0] = str(executable)
    try:
        process = subprocess.run(resolved, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"exit_code": None, "error": type(error).__name__, "stdout_sha256": None, "stderr_sha256": None}
    result: dict[str, Any] = {
        "exit_code": process.returncode,
        "stdout_sha256": sha256(process.stdout),
        "stderr_sha256": sha256(process.stderr),
    }
    try:
        parsed_stderr = json.loads(process.stderr.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed_stderr = None
    if isinstance(parsed_stderr, dict):
        result["stderr_json"] = parsed_stderr
    return result


def _binary(target: Path) -> Path:
    return target / "release" / ("sipi-pybert-direct.exe" if os.name == "nt" else "sipi-pybert-direct")


def build_summary(result: dict[str, Any], binary: Path) -> dict[str, Any]:
    """Emit a stable build schema plus a structural Windows PE digest."""
    custody = windows_pe_replay_custody(binary) if binary.is_file() else None
    return {
        "exit_code": result.get("exit_code"),
        "stdout_sha256": result.get("stdout_sha256"),
        "stderr_sha256": result.get("stderr_sha256"),
        "binary_sha256": sha256(binary.read_bytes()) if binary.is_file() else None,
        "binary_custody": custody,
    }


def _u16(payload: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(payload):
        raise ValueError("PE field is out of bounds")
    return struct.unpack_from("<H", payload, offset)[0]


def _u32(payload: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(payload):
        raise ValueError("PE field is out of bounds")
    return struct.unpack_from("<I", payload, offset)[0]


def _rva_file_range(
    rva: int,
    size: int,
    sections: list[tuple[int, int, int, int]],
    payload_size: int,
) -> tuple[int, int]:
    if size < 0 or rva < 0:
        raise ValueError("PE RVA range is negative")
    if size == 0:
        raise ValueError("PE RVA range is empty")
    matches: list[tuple[int, int]] = []
    for virtual_address, virtual_size, raw_pointer, raw_size in sections:
        span = max(virtual_size, raw_size)
        if virtual_address <= rva and rva + size <= virtual_address + span:
            file_offset = raw_pointer + (rva - virtual_address)
            if file_offset < raw_pointer or file_offset + size > raw_pointer + raw_size:
                continue
            if file_offset + size > payload_size:
                continue
            matches.append((file_offset, size))
    if len(matches) != 1:
        raise ValueError("PE RVA range has an ambiguous or missing section")
    return matches[0]


def windows_pe_replay_custody(binary: Path) -> dict[str, Any]:
    """Hash a PE while normalizing only its structured reproducibility fields.

    This intentionally does not search for or rewrite arbitrary bytes such as
    PDB paths, CodeView ages, or linker payloads.  An unknown debug layout is
    rejected instead of being silently omitted from the canonical digest.
    """
    payload = binary.read_bytes()
    if len(payload) < 0x40 or payload[:2] != b"MZ":
        raise ValueError("binary is not a PE image")
    pe_offset = _u32(payload, 0x3C)
    if pe_offset < 0x40 or pe_offset + 4 + 20 > len(payload) or payload[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("PE header is invalid")
    coff = pe_offset + 4
    machine = _u16(payload, coff)
    section_count = _u16(payload, coff + 2)
    characteristics = _u16(payload, coff + 18)
    optional_size = _u16(payload, coff + 16)
    optional = coff + 20
    optional_end = optional + optional_size
    if section_count == 0 or optional_end > len(payload):
        raise ValueError("PE section or optional header is invalid")
    magic = _u16(payload, optional)
    if machine != 0x8664:
        raise ValueError("PE machine is not AMD64")
    if magic != 0x20B:
        raise ValueError("PE optional header is not PE32+")
    if not characteristics & 0x0002:
        raise ValueError("PE image is not executable")
    profile = "pe32-plus"
    number_of_rva_offset = optional + 108
    data_directory = optional + 112
    if number_of_rva_offset + 4 > optional_end:
        raise ValueError("PE data-directory header is truncated")
    directory_count = _u32(payload, number_of_rva_offset)
    if directory_count > 16 or data_directory + directory_count * 8 > optional_end:
        raise ValueError("PE data-directory table is invalid")
    section_table = optional_end
    section_end = section_table + section_count * 40
    if section_end > len(payload):
        raise ValueError("PE section table is truncated")
    sections: list[tuple[int, int, int, int]] = []
    for index in range(section_count):
        entry = section_table + index * 40
        virtual_size = _u32(payload, entry + 8)
        virtual_address = _u32(payload, entry + 12)
        raw_size = _u32(payload, entry + 16)
        raw_pointer = _u32(payload, entry + 20)
        if raw_size and (raw_pointer < section_end or raw_pointer + raw_size > len(payload)):
            raise ValueError("PE section bytes are out of bounds")
        sections.append((virtual_address, virtual_size, raw_pointer, raw_size))

    normalized = bytearray(payload)
    ranges: list[dict[str, Any]] = []
    fields: list[str] = []

    def zero_range(field: str, offset: int, size: int) -> None:
        if size <= 0 or offset < 0 or offset + size > len(payload):
            raise ValueError("PE normalization range is out of bounds")
        if any(offset < item["offset"] + item["length"] and item["offset"] < offset + size for item in ranges):
            raise ValueError("PE normalization ranges overlap")
        raw = payload[offset : offset + size]
        canonical_bytes = bytes(size)
        fields.append(field)
        ranges.append(
            {
                "field": field,
                "offset": offset,
                "length": size,
                "raw_hex": raw.hex(),
                "canonical_hex": canonical_bytes.hex(),
            }
        )
        normalized[offset : offset + size] = canonical_bytes

    zero_range("IMAGE_FILE_HEADER.TimeDateStamp", coff + 4, 4)
    repro_entries: list[dict[str, Any]] = []
    debug_rva = debug_size = 0
    if directory_count > 6:
        debug_rva = _u32(payload, data_directory + 6 * 8)
        debug_size = _u32(payload, data_directory + 6 * 8 + 4)
    if (debug_rva == 0) != (debug_size == 0):
        raise ValueError("PE debug directory is partially specified")
    if debug_rva:
        debug_offset, debug_bytes = _rva_file_range(debug_rva, debug_size, sections, len(payload))
        if debug_bytes % 28 != 0:
            raise ValueError("PE debug directory has an incomplete entry")
        debug_count = debug_bytes // 28
        for index in range(debug_count):
            entry = debug_offset + index * 28
            debug_type = _u32(payload, entry + 12)
            size_of_data = _u32(payload, entry + 16)
            address_of_raw_data = _u32(payload, entry + 20)
            pointer_to_raw_data = _u32(payload, entry + 24)
            zero_range(f"IMAGE_DEBUG_DIRECTORY[{index}].TimeDateStamp", entry + 4, 4)
            if size_of_data == 0:
                if pointer_to_raw_data != 0 or address_of_raw_data != 0:
                    raise ValueError("PE debug entry has an empty but non-null payload")
                debug_payload = b""
            else:
                if pointer_to_raw_data == 0:
                    if address_of_raw_data == 0:
                        raise ValueError("PE debug entry payload is missing")
                    payload_offset, _ = _rva_file_range(address_of_raw_data, size_of_data, sections, len(payload))
                else:
                    payload_offset = pointer_to_raw_data
                    if payload_offset + size_of_data > len(payload):
                        raise ValueError("PE debug entry payload is out of bounds")
                debug_payload = payload[payload_offset : payload_offset + size_of_data]
            if debug_type == 2:
                if not address_of_raw_data or not pointer_to_raw_data:
                    raise ValueError("PE CodeView debug entry lacks RVA or raw pointer")
                rva_payload_offset, _ = _rva_file_range(address_of_raw_data, size_of_data, sections, len(payload))
                if rva_payload_offset != pointer_to_raw_data:
                    raise ValueError("PE CodeView RVA and raw pointer disagree")
                if len(debug_payload) < 24 or debug_payload[:4] != b"RSDS" or b"\0" not in debug_payload[24:]:
                    raise ValueError("PE CodeView debug entry is not RSDS")
                zero_range(f"CodeView.RSDS[{index}].GUID", payload_offset + 4, 16)
            elif debug_type == 16:
                if len(repro_entries) >= 1:
                    raise ValueError("PE has duplicate REPRO debug entries")
                repro_entries.append(
                    {
                        "present": True,
                        "debug_directory_index": index,
                        "bytes": len(debug_payload),
                        "raw_sha256": sha256(debug_payload),
                    }
                )
            elif debug_type not in set(range(1, 18)):
                raise ValueError(f"PE debug entry type {debug_type} is unsupported")
    ranges.sort(key=lambda item: item["offset"])
    fields = [item["field"] for item in ranges]
    canonical_payload = bytes(normalized)
    return {
        "schema": "sipi.windows-pe-replay-custody.v1",
        "raw_sha256": sha256(payload),
        "canonical_sha256": sha256(canonical_payload),
        "format": "PE",
        "machine": machine,
        "characteristics": characteristics,
        "bytes": len(payload),
        "profile": profile,
        "repro_entry": repro_entries[0]
        if repro_entries
        else {"present": False, "debug_directory_index": None, "bytes": 0, "raw_sha256": None},
        "normalization": {
            "map": "zero-only:IMAGE_FILE_HEADER.TimeDateStamp+IMAGE_DEBUG_DIRECTORY.TimeDateStamp+CodeView.RSDS.GUID",
            "fields": fields,
            "ranges": ranges,
            "changed_byte_count": sum(
                sum(a != b for a, b in zip(bytes.fromhex(item["raw_hex"]), bytes.fromhex(item["canonical_hex"])))
                for item in ranges
            ),
        },
    }


PE_CUSTODY_KEYS = {
    "schema",
    "raw_sha256",
    "canonical_sha256",
    "format",
    "machine",
    "characteristics",
    "bytes",
    "profile",
    "repro_entry",
    "normalization",
}
PE_REPRO_KEYS = {"present", "debug_directory_index", "bytes", "raw_sha256"}
PE_NORMALIZATION_KEYS = {"map", "fields", "ranges", "changed_byte_count"}
PE_RANGE_KEYS = {"field", "offset", "length", "raw_hex", "canonical_hex"}
PE_RANGE_FIELD = re.compile(
    r"(?:IMAGE_FILE_HEADER\.TimeDateStamp|IMAGE_DEBUG_DIRECTORY\[\d+\]\.TimeDateStamp|CodeView\.RSDS\[\d+\]\.GUID)\Z"
)


def validate_windows_pe_replay_custody(value: Any) -> list[str]:
    """Validate the report-only PE custody schema without trusting its digest."""
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != PE_CUSTODY_KEYS:
        return ["binary custody keys drift"]
    if value.get("schema") != "sipi.windows-pe-replay-custody.v1":
        errors.append("binary custody schema drift")
    for key in ("raw_sha256", "canonical_sha256"):
        if not isinstance(value.get(key), str) or HEX64.fullmatch(value[key]) is None:
            errors.append(f"binary custody {key} drift")
    if value.get("format") != "PE":
        errors.append("binary custody format drift")
    machine = value.get("machine")
    if machine != 0x8664:
        errors.append("binary custody machine drift")
    characteristics = value.get("characteristics")
    if isinstance(characteristics, bool) or not isinstance(characteristics, int) or not characteristics & 0x0002:
        errors.append("binary custody executable characteristics drift")
    if isinstance(value.get("bytes"), bool) or not isinstance(value.get("bytes"), int) or value["bytes"] <= 0:
        errors.append("binary custody byte count drift")
    if value.get("profile") != "pe32-plus":
        errors.append("binary custody profile drift")

    repro = value.get("repro_entry")
    if not isinstance(repro, dict) or set(repro) != PE_REPRO_KEYS:
        errors.append("binary custody REPRO entry drift")
    elif repro.get("present") not in {True, False}:
        errors.append("binary custody REPRO presence drift")
    else:
        if repro.get("present") and (isinstance(repro.get("debug_directory_index"), bool) or not isinstance(repro.get("debug_directory_index"), int) or repro["debug_directory_index"] < 0):
            errors.append("binary custody REPRO index drift")
        if not repro.get("present") and repro.get("debug_directory_index") is not None:
            errors.append("binary custody absent REPRO index drift")
        if isinstance(repro.get("bytes"), bool) or not isinstance(repro.get("bytes"), int) or repro["bytes"] < 0:
            errors.append("binary custody REPRO byte count drift")
        raw_repro = repro.get("raw_sha256")
        if raw_repro is not None and (not isinstance(raw_repro, str) or HEX64.fullmatch(raw_repro) is None):
            errors.append("binary custody REPRO digest drift")
        if repro.get("present") and (not isinstance(raw_repro, str) or HEX64.fullmatch(raw_repro) is None):
            errors.append("binary custody present REPRO digest missing")
        if not repro.get("present") and (repro.get("bytes") != 0 or raw_repro is not None):
            errors.append("binary custody absent REPRO payload drift")

    normalization = value.get("normalization")
    if not isinstance(normalization, dict) or set(normalization) != PE_NORMALIZATION_KEYS:
        return errors + ["binary custody normalization keys drift"]
    if normalization.get("map") != "zero-only:IMAGE_FILE_HEADER.TimeDateStamp+IMAGE_DEBUG_DIRECTORY.TimeDateStamp+CodeView.RSDS.GUID":
        errors.append("binary custody normalization map drift")
    fields = normalization.get("fields")
    ranges = normalization.get("ranges")
    if not isinstance(fields, list) or not all(isinstance(item, str) and PE_RANGE_FIELD.fullmatch(item) for item in fields):
        errors.append("binary custody normalization fields drift")
        fields = []
    if not isinstance(ranges, list):
        errors.append("binary custody normalization ranges drift")
        ranges = []
    if fields != [item.get("field") for item in ranges if isinstance(item, dict)]:
        errors.append("binary custody normalization field map drift")
    previous_end = -1
    changed = 0
    for item in ranges:
        if not isinstance(item, dict) or set(item) != PE_RANGE_KEYS:
            errors.append("binary custody normalization range keys drift")
            continue
        field = item.get("field")
        offset = item.get("offset")
        length = item.get("length")
        raw_hex = item.get("raw_hex")
        canonical_hex = item.get("canonical_hex")
        if not isinstance(field, str) or PE_RANGE_FIELD.fullmatch(field) is None:
            errors.append("binary custody normalization range field drift")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            errors.append("binary custody normalization range offset drift")
        if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
            errors.append("binary custody normalization range length drift")
        if not isinstance(offset, int) or not isinstance(length, int) or offset < previous_end:
            errors.append("binary custody normalization ranges overlap or are unsorted")
        if isinstance(offset, int) and isinstance(length, int):
            previous_end = max(previous_end, offset + length)
        try:
            raw = bytes.fromhex(raw_hex) if isinstance(raw_hex, str) else b""
            canonical_bytes = bytes.fromhex(canonical_hex) if isinstance(canonical_hex, str) else b""
        except ValueError:
            raw = canonical_bytes = b""
            errors.append("binary custody normalization range bytes are not hex")
        if isinstance(length, int) and (len(raw) != length or len(canonical_bytes) != length):
            errors.append("binary custody normalization range byte length drift")
        if canonical_bytes and any(canonical_bytes):
            errors.append("binary custody normalization is not zero-only")
        changed += sum(a != b for a, b in zip(raw, canonical_bytes))
        if field == "IMAGE_FILE_HEADER.TimeDateStamp" and length != 4:
            errors.append("binary custody COFF timestamp range drift")
        if field != "IMAGE_FILE_HEADER.TimeDateStamp" and field and field.endswith("TimeDateStamp") and length != 4:
            errors.append("binary custody debug timestamp range drift")
        if field and field.endswith("GUID") and length != 16:
            errors.append("binary custody RSDS GUID range drift")
    if not any(item.get("field") == "IMAGE_FILE_HEADER.TimeDateStamp" for item in ranges if isinstance(item, dict)):
        errors.append("binary custody COFF timestamp normalization missing")
    if normalization.get("changed_byte_count") != changed:
        errors.append("binary custody changed-byte count drift")
    return errors


def windows_pe_custody_shape(value: Any) -> dict[str, Any] | None:
    """Return the cross-run shape, excluding raw normalized bytes."""
    if validate_windows_pe_replay_custody(value):
        return None
    normalization = value["normalization"]
    ranges = [
        {key: item[key] for key in ("field", "offset", "length", "canonical_hex")}
        for item in normalization["ranges"]
    ]
    return {
        "format": value["format"],
        "machine": value["machine"],
        "characteristics": value["characteristics"],
        "bytes": value["bytes"],
        "profile": value["profile"],
        "repro_present": value["repro_entry"]["present"],
        "normalization": {
            "map": normalization["map"],
            "fields": normalization["fields"],
            "ranges": ranges,
        },
    }


def compare_windows_pe_custody(first: Any, second: Any) -> list[str]:
    errors = validate_windows_pe_replay_custody(first) + validate_windows_pe_replay_custody(second)
    if errors:
        return errors
    if first["canonical_sha256"] != second["canonical_sha256"]:
        errors.append("canonical PE digests differ across fresh runs")
    if windows_pe_custody_shape(first) != windows_pe_custody_shape(second):
        errors.append("canonical PE profile or normalization map differs across fresh runs")
    first_repro = first["repro_entry"]
    second_repro = second["repro_entry"]
    if first_repro["present"] and first_repro["raw_sha256"] != second_repro["raw_sha256"]:
        errors.append("IMAGE_DEBUG_TYPE_REPRO payload digests differ across fresh runs")
    return errors


def windows_pe_repro_policy(first: Any, second: Any) -> str:
    if validate_windows_pe_replay_custody(first) or validate_windows_pe_replay_custody(second):
        return "invalid"
    first_entry = first["repro_entry"]
    second_entry = second["repro_entry"]
    if not first_entry["present"] and not second_entry["present"]:
        return "not_present"
    if first_entry["present"] and second_entry["present"] and first_entry["raw_sha256"] == second_entry["raw_sha256"]:
        return "present_equal"
    if first_entry["present"] and second_entry["present"]:
        return "present_raw_drift"
    return "presence_mismatch"


def payload_digest(summary: dict[str, Any], row: str) -> str | None:
    arrays = summary.get("arrays") if isinstance(summary, dict) else None
    if not isinstance(arrays, dict):
        return None
    members = arrays.get("logical_members")
    if not isinstance(members, dict):
        return None
    if row == "PB-03":
        if not set(PB03_PARITY_ARRAYS).issubset(members):
            return None
        return sha256(canonical({name: members[name] for name in PB03_PARITY_ARRAYS}))
    return arrays.get("logical_sha256")


def compact_artifact(summary: dict[str, Any], row: str) -> dict[str, Any]:
    """Keep reports bounded while retaining every gate input."""
    value = dict(summary)
    arrays = value.get("arrays")
    if not isinstance(arrays, dict):
        return value
    arrays = dict(arrays)
    members = arrays.get("logical_members")
    if isinstance(members, dict):
        arrays["logical_member_count"] = len(members)
        arrays["logical_members"] = {
            name: members[name]
            for name in PB03_PARITY_ARRAYS
            if row == "PB-03" and name in members
        }
    value["arrays"] = arrays
    return value


def run_once(
    row: str,
    candidate_repo: Path,
    upstream_repo: Path,
    fixture: str,
    candidate_commit: str,
    candidate_tree: str,
    candidate_archive_sha256: str,
    run_id: str,
    timeout: int,
) -> dict[str, Any]:
    fixture = PurePosixPath(fixture).as_posix()
    if PureWindowsPath(fixture).is_absolute() or PurePosixPath(fixture).is_absolute() or ".." in PurePosixPath(fixture).parts:
        raise RuntimeError("fixture must be repository-relative")
    toolchain_report, tool_paths = resolve_toolchain(timeout)
    with tempfile.TemporaryDirectory(prefix=f"sipi-{row.lower()}-") as work:
        work_root = Path(work)
        candidate_root = work_root / "candidate"
        upstream_root = work_root / "upstream"
        candidate_identity = archive_repo(candidate_repo, candidate_commit, candidate_root)
        if candidate_identity.get("tree") != candidate_tree or candidate_identity.get("archive_sha256") != candidate_archive_sha256:
            raise RuntimeError("candidate archive identity does not match the requested prep commit")
        candidate_archive_fixture_present = (candidate_root / fixture).is_file()
        if not candidate_archive_fixture_present:
            raise RuntimeError("fixed fixture is missing from the candidate archive")
        upstream_identity = archive_repo(upstream_repo, UPSTREAM_COMMIT, upstream_root)
        fixture_bytes = (candidate_root / fixture).read_bytes()
        oracle_fixture = upstream_root / fixture
        oracle_fixture.parent.mkdir(parents=True, exist_ok=True)
        if oracle_fixture.is_file() and oracle_fixture.read_bytes() != fixture_bytes:
            raise RuntimeError("oracle fixture differs from the candidate archive corpus")
        if not oracle_fixture.is_file():
            oracle_fixture.write_bytes(fixture_bytes)
        fixture_path = candidate_root / fixture
        # The direct crate is its own workspace, so Cargo places artifacts next
        # to its manifest rather than at the repository root.
        candidate_target = candidate_root / "crates" / "sipi-pybert-direct" / "target"
        candidate_output = work_root / "candidate-output"
        upstream_output = work_root / "upstream-output"
        build_result = run_command(["cargo", "build", "--manifest-path", str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"), "--release", "--locked"], candidate_root, timeout, tool_paths)
        binary = _binary(candidate_target)
        build = build_summary(build_result, binary)
        command = {"PB-03": "sim-rust", "PB-04": "sim-auto", "PB-05": "sim-compare"}[row]
        if binary.is_file():
            candidate_process = run_command([str(binary), command, str(fixture_path), "--output-dir", str(candidate_output)], candidate_root, timeout, tool_paths)
        else:
            candidate_process = {"exit_code": None, "skipped": True}
        oracle_process = run_command(["uv", "run", "--project", str(upstream_root), "--frozen", "--extra", "native", "pybert", command, str(oracle_fixture), "--output-dir", str(upstream_output)], upstream_root, timeout, tool_paths)
        candidate_artifact = artifact_summary(candidate_output)
        oracle_artifact = artifact_summary(upstream_output)
        candidate_payload = payload_digest(candidate_artifact, row)
        oracle_payload = payload_digest(oracle_artifact, row)
        candidate_artifact = compact_artifact(candidate_artifact, row)
        oracle_artifact = compact_artifact(oracle_artifact, row)
        expected_schema = {
            "PB-03": "pybert.native-cli-result.v1",
            "PB-04": "pybert.cli-auto-result.v1",
            "PB-05": "pybert.cli-compare-result.v1",
        }[row]
        candidate_ok = (
            candidate_process.get("exit_code") == 0
            and candidate_artifact.get("meta_schema") == expected_schema
            and candidate_payload is not None
        )
        oracle_ok = (
            oracle_process.get("exit_code") == 0
            and oracle_artifact.get("meta_schema") == expected_schema
            and oracle_payload is not None
        )
        candidate_selection = candidate_artifact.get("selection")
        if candidate_selection is None:
            candidate_selection = selection_summary(candidate_process.get("stderr_json", {}))
        candidate_comparison = candidate_artifact.get("comparison")
        if candidate_comparison is None:
            candidate_comparison = comparison_summary(candidate_process.get("stderr_json", {}))
        candidate_no_reference = (
            row == "PB-05"
            and isinstance(candidate_comparison, dict)
            and candidate_comparison.get("reason") == "not_evaluated"
            and candidate_comparison.get("reference_required") == "external_python_reference_required"
            and candidate_comparison.get("status_only_comparison") is False
        )
        if candidate_no_reference:
            # A missing independent reference is an expected fail-closed outcome,
            # not a process/schema regression.  The row remains blocked because
            # payload parity was intentionally not evaluated.
            candidate_ok = True
        selection = {
            "candidate": candidate_selection,
            "oracle": oracle_artifact.get("selection"),
            "expected": {
                "requested": "auto",
                "selected": "python",
                "parity_gate_status": "blocked",
            }
            if row == "PB-04"
            else None,
        }
        comparison = {
            "candidate": candidate_comparison,
            "oracle": oracle_artifact.get("comparison"),
            "payload_gate": {
                "candidate_artifact_present": candidate_payload is not None,
                "oracle_artifact_present": oracle_payload is not None,
                "logical_arrays_equal": candidate_payload is not None and candidate_payload == oracle_payload,
                "status_only_comparison": False,
            }
            if row == "PB-05"
            else None,
        }
        semantic_ok = True
        if row == "PB-04":
            candidate_selection = selection.get("candidate")
            oracle_selection = oracle_artifact.get("selection")
            semantic_ok = (
                isinstance(candidate_selection, dict)
                and candidate_selection.get("requested") == "auto"
                and candidate_selection.get("selected") == "python"
                and candidate_selection.get("implementation") == "external_python_reference_required"
                and candidate_selection.get("rust_only") is False
                and isinstance(candidate_selection.get("parity_gate"), dict)
                and candidate_selection["parity_gate"].get("status") == "blocked"
                and isinstance(oracle_selection, dict)
                and oracle_selection.get("requested") == "auto"
                and oracle_selection.get("selected") == "python"
                and isinstance(oracle_selection.get("parity_gate"), dict)
                and oracle_selection["parity_gate"].get("status") == "blocked"
            )
        if row == "PB-05":
            candidate_comparison = comparison.get("candidate")
            oracle_comparison = oracle_artifact.get("comparison")
            semantic_ok = (
                isinstance(candidate_comparison, dict)
                and candidate_comparison.get("schema") == "pybert.engine-compare.v1"
                and candidate_comparison.get("status_only_comparison") is False
                and (
                    candidate_comparison.get("reason") == "not_evaluated"
                    or candidate_comparison.get("arrays_passed") is not None
                )
                and isinstance(oracle_comparison, dict)
                and oracle_comparison.get("schema") == "pybert.engine-compare.v1"
                and oracle_comparison.get("status_only_comparison") is not True
                and oracle_comparison.get("arrays_passed") is not None
            )
        blockers: list[str] = []
        if not candidate_ok:
            blockers.append("candidate process or artifact schema/payload gate failed")
        if not oracle_ok:
            blockers.append("oracle process or artifact schema/payload gate failed")
        if candidate_payload is None or oracle_payload is None or candidate_payload != oracle_payload:
            if candidate_no_reference:
                blockers.append("candidate/oracle payload parity not_evaluated: external_python_reference_required")
            else:
                blockers.append("candidate/oracle logical payload gate failed")
        if not semantic_ok:
            blockers.append("workflow semantic gate failed")
        fixture_record = fixture_info(candidate_root, fixture)
        fixture_record["archive_present"] = candidate_archive_fixture_present
        return {
            "schema": f"sipi.{row.lower()}-direct-replay.v1",
            "status": "passed" if not blockers else "blocked",
            "source_mode": "git_archive_at_immutable_commit",
            "row": row,
            "run_id": run_id,
            "fresh_run_nonce": uuid.uuid4().hex,
            "candidate": candidate_identity,
            "upstream": upstream_identity,
            "fixture": fixture_record,
            "build": build,
            "toolchain": toolchain_report,
            "replay": {
                "candidate_process": candidate_process,
                "oracle_process": oracle_process,
                "candidate_artifact": candidate_artifact,
                "oracle_artifact": oracle_artifact,
                "payload": {"candidate_logical_sha256": candidate_payload, "oracle_logical_sha256": oracle_payload, "equal": candidate_payload is not None and candidate_payload == oracle_payload},
                "selection": selection,
                "comparison": comparison,
                "semantic_gate": semantic_ok,
            },
            "blockers": blockers,
            "claims": {"payload_parity": bool(candidate_ok and oracle_ok and candidate_payload == oracle_payload and semantic_ok), "global_row_closed": False, "release_approval": False},
            "non_claims": ["This is one frozen fixture only.", "Wrapper, selection, comparison, and uncovered branches remain open unless their payload gate passes.", "This evidence is not a license decision or release approval."],
        }


def parse_run_args(row: str, fixture: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--fixture", default=fixture)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    args.row = row
    return args


def run_main(args: argparse.Namespace) -> int:
    try:
        report = run_once(args.row, args.candidate_repo.resolve(), args.upstream_repo.resolve(), args.fixture, args.candidate_commit, args.candidate_tree, args.candidate_archive_sha256, args.run_id, args.timeout_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": report["status"], "output": args.output.as_posix()}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1
