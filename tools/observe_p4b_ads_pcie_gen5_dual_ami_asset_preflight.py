"""Observe, but never admit, one local ADS PCIe Gen5 dual-AMI asset set.

The report is deliberately hash/structure-only and must be written outside the
product worktree.  No asset bytes, parameters, or source paths are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-ads-pcie-gen5-dual-ami-asset-observation.v1"
ASSETS = {
    "pcie-gen5-ibis": "pcie_gen5.ibs",
    "pcie-tx-ami": "ctspcie_tx_gen5.ami",
    "pcie-rx-ami": "ctspcie_rx_gen5.ami",
    "pcie-tx-dll": "ctspcie_tx_win64.dll",
    "pcie-rx-dll": "ctspcie_rx_win64.dll",
}
ABI_EXPORTS = {"AMI_Init", "AMI_GetWave", "AMI_Close"}
SYSTEM_IMPORTS = {"kernel32.dll", "msvcrt.dll", "user32.dll"}
EXPECTED_IBIS_BINDINGS = {
    "pcie_tx": {
        "platform": "Windows_mingw64-g++_64",
        "dll_logical_name": ASSETS["pcie-tx-dll"],
        "ami_logical_name": ASSETS["pcie-tx-ami"],
    },
    "pcie_rx": {
        "platform": "Windows_mingw64-g++_64",
        "dll_logical_name": ASSETS["pcie-rx-dll"],
        "ami_logical_name": ASSETS["pcie-rx-ami"],
    },
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ObservationError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & 0x400)


def require_child(root: Path, name: str) -> Path:
    candidate = root / name
    if not candidate.is_file() or candidate.is_symlink() or is_reparse(candidate):
        raise ObservationError("asset_is_not_a_regular_file")
    if candidate.resolve() != root.resolve() / name:
        raise ObservationError("asset_escapes_external_root")
    return candidate


def materialize(root: Path) -> dict[str, tuple[Path, int, str]]:
    if not root.is_dir() or root.is_symlink() or is_reparse(root):
        raise ObservationError("external_root_is_not_a_real_directory")
    copied: dict[str, tuple[Path, int, str]] = {}
    temp = Path(tempfile.mkdtemp(prefix="sipi-p4b-ads-dual-ami-"))
    try:
        for asset_id, name in ASSETS.items():
            source = require_child(root, name)
            before = source.read_bytes()
            identity = (len(before), sha256(before))
            destination = temp / name
            shutil.copyfile(source, destination)
            after = source.read_bytes()
            if (len(after), sha256(after)) != identity:
                raise ObservationError("external_asset_changed_during_materialization")
            copied_bytes = destination.read_bytes()
            if (len(copied_bytes), sha256(copied_bytes)) != identity:
                raise ObservationError("fresh_copy_identity_mismatch")
            copied[asset_id] = (destination, *identity)
        return copied
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def read_u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ObservationError("truncated_pe_field")
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ObservationError("truncated_pe_field")
    return struct.unpack_from("<I", data, offset)[0]


def c_string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ObservationError("pe_string_outside_file")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ObservationError("unterminated_pe_string")
    return data[offset:end].decode("ascii", "strict")


def pe_surface(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ObservationError("not_a_pe_image")
    pe = read_u32(data, 0x3C)
    if data[pe : pe + 4] != b"PE\0\0":
        raise ObservationError("missing_pe_signature")
    coff = pe + 4
    machine = read_u16(data, coff)
    sections_count = read_u16(data, coff + 2)
    optional_size = read_u16(data, coff + 16)
    characteristics = read_u16(data, coff + 18)
    optional = coff + 20
    if read_u16(data, optional) != 0x20B:
        raise ObservationError("not_pe32_plus")
    directory_count = read_u32(data, optional + 108)
    if directory_count < 14:
        raise ObservationError("pe_directories_missing")
    directories = optional + 112
    section_offset = optional + optional_size
    if section_offset + sections_count * 40 > len(data):
        raise ObservationError("truncated_pe_sections")
    sections = []
    for index in range(sections_count):
        entry = section_offset + index * 40
        sections.append(
            {
                "virtual_address": read_u32(data, entry + 12),
                "virtual_size": read_u32(data, entry + 8),
                "raw_offset": read_u32(data, entry + 20),
                "raw_size": read_u32(data, entry + 16),
            }
        )

    def rva_offset(rva: int) -> int:
        for section in sections:
            start = section["virtual_address"]
            span = max(section["virtual_size"], section["raw_size"])
            if start <= rva < start + span:
                value = section["raw_offset"] + rva - start
                if value < len(data):
                    return value
        raise ObservationError("pe_rva_outside_sections")

    def directory(index: int) -> tuple[int, int]:
        entry = directories + index * 8
        return read_u32(data, entry), read_u32(data, entry + 4)

    def imports(rva: int, size: int, *, delayed: bool) -> list[str]:
        if rva == 0 or size == 0:
            return []
        offset = rva_offset(rva)
        stride = 32 if delayed else 20
        names: list[str] = []
        for _ in range(size // stride + 1):
            if delayed:
                attributes = read_u32(data, offset)
                name_value = read_u32(data, offset + 4)
                module = read_u32(data, offset + 8)
                if attributes == 0 and name_value == 0 and module == 0:
                    return sorted(set(names))
                if attributes != 1:
                    raise ObservationError("unsupported_delay_import_attributes")
                name_rva = name_value
            else:
                name_rva = read_u32(data, offset + 12)
                first_thunk = read_u32(data, offset + 16)
                if name_rva == 0 and first_thunk == 0:
                    return sorted(set(names))
            names.append(c_string(data, rva_offset(name_rva)).lower())
            offset += stride
        raise ObservationError("unterminated_import_table")

    export_rva, export_size = directory(0)
    if export_rva == 0 or export_size == 0:
        raise ObservationError("missing_export_table")
    export = rva_offset(export_rva)
    count = read_u32(data, export + 24)
    names_rva = read_u32(data, export + 32)
    names_offset = rva_offset(names_rva)
    exports = sorted({c_string(data, rva_offset(read_u32(data, names_offset + 4 * index))) for index in range(count)})
    normal_rva, normal_size = directory(1)
    delay_rva, delay_size = directory(13)
    return {
        "machine": "windows-x86_64" if machine == 0x8664 else f"pe_machine_0x{machine:04x}",
        "is_dll": bool(characteristics & 0x2000),
        "exports": exports,
        "normal_imports": imports(normal_rva, normal_size, delayed=False),
        "delay_imports": imports(delay_rva, delay_size, delayed=True),
    }


def ibis_bindings(data: bytes) -> tuple[str, dict[str, dict[str, str]]]:
    if b"\0" in data:
        raise ObservationError("ibis_contains_nul")
    text = data.decode("ascii", "strict")
    version = re.search(r"(?mi)^\[IBIS Ver\]\s+(\S+)\s*$", text)
    if not version:
        raise ObservationError("ibis_version_missing")
    models: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in text.splitlines():
        model = re.match(r"^\[Model\]\s+(\S+)\s*$", line, re.IGNORECASE)
        if model:
            current = model.group(1)
            continue
        executable = re.match(r"^Executable\s+(\S+)\s+(\S+)\s+(\S+)\s*$", line, re.IGNORECASE)
        if executable and current:
            models[current] = {
                "platform": executable.group(1),
                "dll_logical_name": executable.group(2),
                "ami_logical_name": executable.group(3),
            }
    needed = {"pcie_tx", "pcie_rx"}
    if set(models) & needed != needed:
        raise ObservationError("ibis_algorithmic_bindings_missing")
    bindings = {name: models[name] for name in sorted(needed)}
    if bindings != EXPECTED_IBIS_BINDINGS:
        raise ObservationError("ibis_algorithmic_bindings_do_not_match_allowlist")
    return version.group(1), bindings


def ami_surface(data: bytes) -> dict[str, str]:
    if b"\0" in data:
        raise ObservationError("ami_contains_nul")
    text = data.decode("utf-8", "strict")
    root = re.match(r"^\s*\(\s*([^\s()]+)", text)
    version = re.search(r"\(AMI_Version\s+.*?\(Value\s+\"?([^\s)\"]+)", text, re.DOTALL)
    if not root or not version:
        raise ObservationError("ami_root_or_version_missing")
    return {"root": root.group(1), "ami_version": version.group(1)}


def asset_set_digest(assets: dict[str, tuple[Path, int, str]]) -> str:
    rows = [f"{asset_id}\t{size}\t{identity}" for asset_id, (_, size, identity) in sorted(assets.items())]
    return sha256(("\n".join(rows) + "\n").encode("ascii"))


def observe(external_root: Path) -> dict[str, Any]:
    copied = materialize(external_root.resolve())
    temp_root = next(iter(copied.values()))[0].parent
    try:
        ibis_version, bindings = ibis_bindings(copied["pcie-gen5-ibis"][0].read_bytes())
        tx_ami = ami_surface(copied["pcie-tx-ami"][0].read_bytes())
        rx_ami = ami_surface(copied["pcie-rx-ami"][0].read_bytes())
        pe = {asset_id: pe_surface(copied[asset_id][0]) for asset_id in ("pcie-tx-dll", "pcie-rx-dll")}
        for surface in pe.values():
            if surface["machine"] != "windows-x86_64" or not surface["is_dll"]:
                raise ObservationError("dll_is_not_windows_x64")
            if not ABI_EXPORTS <= set(surface["exports"]):
                raise ObservationError("required_abi_export_missing")
            if set(surface["normal_imports"]) != SYSTEM_IMPORTS or surface["delay_imports"] != []:
                raise ObservationError("unexpected_static_import_closure")
        return {
            "schema": SCHEMA,
            "status": "external_only_identity_observed_worker_blocked",
            "external_root_retained": False,
            "fresh_materialization": "single_private_copy_toctou_checked",
            "asset_set_digest": asset_set_digest(copied),
            "assets": [
                {"id": asset_id, "logical_name": ASSETS[asset_id], "byte_length": size, "sha256": identity}
                for asset_id, (_, size, identity) in sorted(copied.items())
            ],
            "ibis": {"version": ibis_version, "bindings": bindings},
            "ami": {"pcie_tx": tx_ami, "pcie_rx": rx_ami},
            "dll": pe,
            "non_claims": [
                "not_worker_admission",
                "not_runtime_load_or_getwave_evidence",
                "not_ami_or_ibis_compatibility",
                "not_dependency_closure",
                "not_third_party_rights_or_redistribution_evidence",
                "not_tx_to_rx_composition_or_numerical_parity",
            ],
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-report-sha256")
    arguments = parser.parse_args(argv)
    try:
        report = arguments.report.resolve()
        if ROOT == report or ROOT in report.parents:
            raise ObservationError("report_must_stay_outside_product_root")
        if report.exists():
            raise ObservationError("report_already_exists")
        result = observe(arguments.external_root)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
        expected = arguments.expected_report_sha256
        if expected is not None and (not HEX64.fullmatch(expected) or sha256(encoded.encode("utf-8")) != expected):
            raise ObservationError("external_observation_source_drift")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(encoded.encode("utf-8"))
    except (ObservationError, OSError, UnicodeError, struct.error) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
