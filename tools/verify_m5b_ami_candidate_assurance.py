"""Measure, but never promote, a Windows AMI candidate executable.

This is intentionally a diagnostic gate: its report can state that twin builds
are byte-identical, or that they are not. Only the former is eligible for a
future promotion review; neither outcome changes engine selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.m5b-ami-candidate-assurance.v1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes())


def read_u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("truncated PE field")
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated PE field")
    return struct.unpack_from("<I", data, offset)[0]


def read_u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise ValueError("truncated PE field")
    return struct.unpack_from("<Q", data, offset)[0]


def c_string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ValueError("PE string outside file")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated PE string")
    return data[offset:end].decode("ascii", "strict").lower()


def parse_pe(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("not a DOS/PE executable")
    pe = read_u32(data, 0x3C)
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    coff = pe + 4
    machine = read_u16(data, coff)
    section_count = read_u16(data, coff + 2)
    timestamp = read_u32(data, coff + 4)
    optional_size = read_u16(data, coff + 16)
    optional = coff + 20
    magic = read_u16(data, optional)
    if magic != 0x20B:
        raise ValueError("candidate must be PE32+")
    image_base = read_u64(data, optional + 24)
    subsystem = read_u16(data, optional + 68)
    directory_count = read_u32(data, optional + 108)
    if directory_count < 14:
        raise ValueError("PE optional header lacks import directories")
    directories = optional + 112
    sections_offset = optional + optional_size
    if sections_offset + section_count * 40 > len(data):
        raise ValueError("truncated section table")
    sections: list[dict[str, Any]] = []
    for index in range(section_count):
        entry = sections_offset + index * 40
        raw_name = data[entry : entry + 8].split(b"\0", 1)[0]
        sections.append({
            "name": raw_name.decode("ascii", "replace"),
            "virtualAddress": read_u32(data, entry + 12),
            "virtualSize": read_u32(data, entry + 8),
            "rawOffset": read_u32(data, entry + 20),
            "rawSize": read_u32(data, entry + 16),
            "sha256": sha256(data[read_u32(data, entry + 20) : read_u32(data, entry + 20) + read_u32(data, entry + 16)]),
        })

    def rva_offset(rva: int) -> int:
        for section in sections:
            start = section["virtualAddress"]
            span = max(section["virtualSize"], section["rawSize"])
            if start <= rva < start + span:
                offset = section["rawOffset"] + rva - start
                if offset >= len(data):
                    break
                return offset
        raise ValueError(f"RVA outside sections: 0x{rva:x}")

    def directory(index: int) -> tuple[int, int]:
        entry = directories + index * 8
        return read_u32(data, entry), read_u32(data, entry + 4)

    normal_rva, normal_size = directory(1)
    delay_rva, delay_size = directory(13)

    def normal_imports() -> list[str]:
        if normal_rva == 0 or normal_size == 0:
            return []
        offset = rva_offset(normal_rva)
        values: list[str] = []
        for _ in range(normal_size // 20 + 1):
            name_rva = read_u32(data, offset + 12)
            first_thunk = read_u32(data, offset + 16)
            if name_rva == 0 and first_thunk == 0:
                return values
            values.append(c_string(data, rva_offset(name_rva)))
            offset += 20
        raise ValueError("unterminated normal import table")

    def delay_imports() -> list[str]:
        if delay_rva == 0 or delay_size == 0:
            return []
        offset = rva_offset(delay_rva)
        values: list[str] = []
        for _ in range(delay_size // 32 + 1):
            attributes = read_u32(data, offset)
            name_value = read_u32(data, offset + 4)
            module_handle = read_u32(data, offset + 8)
            if attributes == 0 and name_value == 0 and module_handle == 0:
                return values
            if attributes & ~1:
                raise ValueError("unsupported delay import attributes")
            name_rva = name_value if attributes & 1 else name_value - image_base
            if name_rva < 0:
                raise ValueError("invalid delay import VA")
            values.append(c_string(data, rva_offset(name_rva)))
            offset += 32
        raise ValueError("unterminated delay import table")

    return {
        "machine": f"0x{machine:04x}",
        "subsystem": subsystem,
        "coffTimestamp": timestamp,
        "imageBase": f"0x{image_base:x}",
        "sections": sections,
        "normalImports": sorted(set(normal_imports())),
        "delayImports": sorted(set(delay_imports())),
    }


def system_resolution(imports: list[str], system_root: Path) -> list[dict[str, Any]]:
    system32 = system_root / "System32"
    result = []
    for name in imports:
        if name.startswith(("api-ms-win-", "ext-ms-win-")):
            result.append({"name": name, "kind": "api_set", "resolution": "windows_api_set_contract"})
            continue
        resolved = system32 / name
        if not resolved.is_file():
            raise ValueError(f"non-system or missing executable import: {name}")
        result.append({"name": name, "kind": "system32", "path": str(resolved), "sha256": file_hash(resolved)})
    return result


def assure(left: Path, right: Path, system_root: Path) -> dict[str, Any]:
    left_pe, right_pe = parse_pe(left), parse_pe(right)
    left_hash, right_hash = file_hash(left), file_hash(right)
    if left_pe["machine"] != "0x8664" or right_pe["machine"] != "0x8664":
        raise ValueError("candidate executable is not Windows x64")
    imports = sorted(set(left_pe["normalImports"] + left_pe["delayImports"]))
    if imports != sorted(set(right_pe["normalImports"] + right_pe["delayImports"])):
        raise ValueError("twin builds have different normal/delay import closure")
    report = {
        "schema": SCHEMA,
        "platform": "windows-x86_64",
        "candidate": True,
        "productionResolvable": False,
        "builds": [
            {"path": str(left), "byteLength": left.stat().st_size, "sha256": left_hash, "pe": left_pe},
            {"path": str(right), "byteLength": right.stat().st_size, "sha256": right_hash, "pe": right_pe},
        ],
        "byteReproducible": left_hash == right_hash,
        "dynamicDependencyClosure": {
            "normal": system_resolution(left_pe["normalImports"], system_root),
            "delay": system_resolution(left_pe["delayImports"], system_root),
            "vendorDllClosure": "caller_supplied_blocked_unknown",
        },
        "promotionEligible": False,
        "nonClaims": ["not engine.lock promotion", "not vendor runtime evidence", "not AMI numerical parity"],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-exe", type=Path, required=True)
    parser.add_argument("--right-exe", type=Path, required=True)
    parser.add_argument("--system-root", type=Path, default=Path(r"C:\Windows"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = assure(args.left_exe.resolve(), args.right_exe.resolve(), args.system_root.resolve())
        if args.output.exists():
            raise ValueError("assurance output already exists")
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, struct.error) as error:
        print(f"candidate assurance rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "byteReproducible": report["byteReproducible"], "report": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
