"""Observe only static PE loader declarations of the P4B dual-AMI DLLs.

The observer deliberately has no ctypes, subprocess, ADS, or worker path.
It consumes exactly the two P4B-05b DLL identities and writes a hash-only
report outside this product tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Any
import xml.etree.ElementTree as element_tree


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-dual-ami-pe-loader-declarations-observation.v1"
DLLS = {
    "pcie-tx-dll": ("ctspcie_tx_win64.dll", 370045, "05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea"),
    "pcie-rx-dll": ("ctspcie_rx_win64.dll", 8850494, "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"),
}
DYNAMIC_LOADER_SYMBOLS = {
    "loadlibrarya", "loadlibraryw", "loadlibraryexa", "loadlibraryexw",
    "getprocaddress", "adddlldirectory", "setdlldirectorya", "setdlldirectoryw",
    "ldrloaddll",
}
MAX_TABLE_ENTRIES = 65536
MAX_MANIFEST_BYTES = 262144
HEX64 = set("0123456789abcdef")


class ObservationError(RuntimeError):
    pass


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ObservationError("truncated_pe_field")
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ObservationError("truncated_pe_field")
    return struct.unpack_from("<I", data, offset)[0]


def read_u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise ObservationError("truncated_pe_field")
    return struct.unpack_from("<Q", data, offset)[0]


def c_string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ObservationError("pe_string_outside_file")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ObservationError("unterminated_pe_string")
    return data[offset:end].decode("ascii", "strict")


def is_reparse(path: Path) -> bool:
    return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def private_copy(root: Path) -> tuple[Path, dict[str, tuple[int, str]]]:
    if not root.is_dir() or root.is_symlink() or is_reparse(root):
        raise ObservationError("external_root_is_not_a_real_directory")
    temp = Path(tempfile.mkdtemp(prefix="sipi-p4b-loader-declarations-"))
    identities: dict[str, tuple[int, str]] = {}
    try:
        for asset_id, (name, expected_length, expected_hash) in DLLS.items():
            source = root / name
            if not source.is_file() or source.is_symlink() or is_reparse(source) or source.resolve() != root.resolve() / name:
                raise ObservationError("asset_is_not_a_regular_file")
            before = source.read_bytes()
            identity = (len(before), digest(before))
            if identity != (expected_length, expected_hash):
                raise ObservationError("p4b05b_dll_identity_drift")
            destination = temp / name
            shutil.copyfile(source, destination)
            after = source.read_bytes()
            copied = destination.read_bytes()
            if (len(after), digest(after)) != identity:
                raise ObservationError("external_asset_changed_during_materialization")
            if (len(copied), digest(copied)) != identity:
                raise ObservationError("fresh_copy_identity_mismatch")
            identities[asset_id] = identity
        return temp, identities
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


class PeImage:
    def __init__(self, data: bytes) -> None:
        if data[:2] != b"MZ":
            raise ObservationError("not_a_pe_image")
        pe = read_u32(data, 0x3C)
        if data[pe:pe + 4] != b"PE\0\0":
            raise ObservationError("missing_pe_signature")
        coff = pe + 4
        self.data = data
        self.machine = read_u16(data, coff)
        count = read_u16(data, coff + 2)
        optional_size = read_u16(data, coff + 16)
        self.is_dll = bool(read_u16(data, coff + 18) & 0x2000)
        optional = coff + 20
        if read_u16(data, optional) != 0x20B:
            raise ObservationError("not_pe32_plus")
        if read_u32(data, optional + 108) < 14:
            raise ObservationError("pe_directories_missing")
        self.directories = optional + 112
        section_offset = optional + optional_size
        if section_offset + count * 40 > len(data):
            raise ObservationError("truncated_pe_sections")
        self.sections = []
        for index in range(count):
            offset = section_offset + index * 40
            raw_offset, raw_size = read_u32(data, offset + 20), read_u32(data, offset + 16)
            if raw_offset + raw_size > len(data):
                raise ObservationError("section_raw_bounds_invalid")
            self.sections.append((read_u32(data, offset + 12), max(read_u32(data, offset + 8), raw_size), raw_offset, raw_size))

    def directory(self, index: int) -> tuple[int, int]:
        offset = self.directories + index * 8
        return read_u32(self.data, offset), read_u32(self.data, offset + 4)

    def rva_offset(self, rva: int) -> int:
        for start, span, raw, raw_size in self.sections:
            if start <= rva < start + span:
                offset = raw + rva - start
                if offset < raw + raw_size and offset < len(self.data):
                    return offset
        raise ObservationError("pe_rva_outside_sections")

    def import_table(self, delayed: bool) -> list[dict[str, Any]]:
        rva, size = self.directory(13 if delayed else 1)
        if rva == 0 and size == 0:
            return []
        if rva == 0 or size == 0:
            raise ObservationError("partial_import_directory")
        offset, stride = self.rva_offset(rva), (32 if delayed else 20)
        result = []
        for _ in range(min(MAX_TABLE_ENTRIES, size // stride + 1)):
            fields = [read_u32(self.data, offset + word * 4) for word in range(stride // 4)]
            if not any(fields):
                return result
            if delayed:
                if fields[0] != 1:
                    raise ObservationError("unsupported_delay_import_attributes")
                name_rva, thunk_rva = fields[1], fields[4] or fields[3]
            else:
                name_rva, thunk_rva = fields[3], fields[0] or fields[4]
            module = c_string(self.data, self.rva_offset(name_rva)).lower()
            result.append({"module": module, "symbols": self.thunks(thunk_rva)})
            offset += stride
        raise ObservationError("unterminated_import_table")

    def thunks(self, rva: int) -> list[str]:
        if rva == 0:
            raise ObservationError("missing_import_thunk")
        offset, symbols = self.rva_offset(rva), []
        for _ in range(MAX_TABLE_ENTRIES):
            value = read_u64(self.data, offset)
            if value == 0:
                return symbols
            if value & (1 << 63):
                symbols.append(f"ordinal:{value & 0xffff}")
            else:
                symbols.append(c_string(self.data, self.rva_offset(value) + 2))
            offset += 8
        raise ObservationError("unterminated_import_thunks")

    def exports(self) -> dict[str, Any]:
        rva, size = self.directory(0)
        if rva == 0 or size == 0:
            raise ObservationError("missing_export_table")
        offset = self.rva_offset(rva)
        functions, names = read_u32(self.data, offset + 20), read_u32(self.data, offset + 24)
        function_offset = self.rva_offset(read_u32(self.data, offset + 28))
        name_offset = self.rva_offset(read_u32(self.data, offset + 32))
        ordinal_offset = self.rva_offset(read_u32(self.data, offset + 36))
        if functions > MAX_TABLE_ENTRIES or names > MAX_TABLE_ENTRIES:
            raise ObservationError("export_table_too_large")
        forwarders = []
        exported = []
        for index in range(names):
            name = c_string(self.data, self.rva_offset(read_u32(self.data, name_offset + 4 * index)))
            ordinal = read_u16(self.data, ordinal_offset + 2 * index)
            if ordinal >= functions:
                raise ObservationError("export_ordinal_outside_functions")
            target_rva = read_u32(self.data, function_offset + 4 * ordinal)
            exported.append(name)
            if rva <= target_rva < rva + size:
                forwarders.append({"export": name, "target": c_string(self.data, self.rva_offset(target_rva))})
        return {"named_exports": sorted(set(exported)), "forwarders": sorted(forwarders, key=lambda row: (row["export"], row["target"]))}

    def bound_imports(self) -> list[dict[str, Any]]:
        rva, size = self.directory(11)
        if rva == 0 and size == 0:
            return []
        if rva == 0 or size < 8:
            raise ObservationError("partial_bound_import_directory")
        base, offset, limit = self.rva_offset(rva), self.rva_offset(rva), self.rva_offset(rva) + size
        if limit > len(self.data):
            raise ObservationError("bound_import_directory_bounds")
        result = []
        while offset + 8 <= limit and len(result) < MAX_TABLE_ENTRIES:
            timestamp, name_offset, refs = read_u32(self.data, offset), read_u16(self.data, offset + 4), read_u16(self.data, offset + 6)
            if timestamp == 0 and name_offset == 0 and refs == 0:
                return result
            refs_offset = offset + 8
            if refs_offset + refs * 8 > limit:
                raise ObservationError("bound_import_forwarder_bounds")
            forwarders = []
            for index in range(refs):
                value = refs_offset + index * 8
                forwarders.append({"module": c_string(self.data, base + read_u16(self.data, value + 4)).lower(), "timestamp": read_u32(self.data, value)})
            result.append({"module": c_string(self.data, base + name_offset).lower(), "timestamp": timestamp, "forwarders": forwarders})
            offset = refs_offset + refs * 8
        raise ObservationError("unterminated_bound_import_table")

    def manifests(self) -> list[dict[str, Any]]:
        rva, size = self.directory(2)
        if rva == 0 and size == 0:
            return []
        if rva == 0 or size == 0:
            raise ObservationError("partial_resource_directory")
        base = self.rva_offset(rva)
        seen: set[tuple[int, int]] = set()
        blobs: list[tuple[str, str, bytes]] = []

        def walk(relative: int, level: int, labels: list[str]) -> None:
            if level > 3 or relative in seen:
                raise ObservationError("resource_tree_invalid")
            seen.add(relative)
            offset = base + relative
            named, ids = read_u16(self.data, offset + 12), read_u16(self.data, offset + 14)
            total = named + ids
            if total > MAX_TABLE_ENTRIES or offset + 16 + total * 8 > len(self.data):
                raise ObservationError("resource_directory_bounds")
            for index in range(total):
                entry = offset + 16 + index * 8
                name = read_u32(self.data, entry)
                child = read_u32(self.data, entry + 4)
                label = f"id:{name & 0xffff}" if not name & 0x80000000 else "named"
                if child & 0x80000000:
                    walk(child & 0x7fffffff, level + 1, labels + [label])
                elif level >= 2 and labels and labels[0] == "id:24":
                    data_entry = base + child
                    blob_rva, blob_size = read_u32(self.data, data_entry), read_u32(self.data, data_entry + 4)
                    if blob_size > MAX_MANIFEST_BYTES:
                        raise ObservationError("manifest_resource_too_large")
                    blob_offset = self.rva_offset(blob_rva)
                    if blob_offset + blob_size > len(self.data):
                        raise ObservationError("manifest_resource_bounds")
                    blobs.append((labels[1] if len(labels) > 1 else "unknown", label, self.data[blob_offset:blob_offset + blob_size]))
                # Non-manifest resources are outside this narrow declaration
                # surface. They neither prove nor disprove loader closure.

        walk(0, 0, [])
        return [manifest_record(resource_id, language, blob) for resource_id, language, blob in blobs]


def manifest_record(resource_id: str, language: str, raw: bytes) -> dict[str, Any]:
    record: dict[str, Any] = {"resource_id": resource_id, "language": language, "byte_length": len(raw), "sha256": digest(raw), "declarations": "unresolved"}
    if b"<!" in raw or b"&" in raw:
        raise ObservationError("unsafe_manifest_xml")
    try:
        root = element_tree.fromstring(raw)
    except element_tree.ParseError:
        return record
    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
    if local(root.tag) != "assembly":
        return record
    identities, dependencies, files = [], [], []
    for node in root.iter():
        tag = local(node.tag)
        if tag == "assemblyIdentity":
            identities.append(sorted((str(key), str(value)) for key, value in node.attrib.items()))
        elif tag == "file":
            files.append(node.attrib.get("name", ""))
        elif tag == "dependentAssembly":
            child = next((item for item in node if local(item.tag) == "assemblyIdentity"), None)
            dependencies.append(sorted((str(key), str(value)) for key, value in child.attrib.items()) if child is not None else [])
    record["declarations"] = {"assembly_identities": identities, "dependencies": dependencies, "files": files}
    return record


def observe_once(external_root: Path) -> dict[str, Any]:
    temporary, identities = private_copy(external_root.resolve())
    try:
        dll = {}
        for asset_id, (name, _, _) in DLLS.items():
            image = PeImage((temporary / name).read_bytes())
            normal, delayed = image.import_table(False), image.import_table(True)
            indicators = sorted({symbol for group in normal + delayed for symbol in group["symbols"] if symbol.lower() in DYNAMIC_LOADER_SYMBOLS})
            dll[asset_id] = {
                "byte_length": identities[asset_id][0], "sha256": identities[asset_id][1],
                "machine": "windows-x86_64" if image.machine == 0x8664 else f"pe_machine_0x{image.machine:04x}",
                "is_dll": image.is_dll, "normal_imports": normal, "delay_imports": delayed,
                "bound_imports": image.bound_imports(), "exports": image.exports(),
                "embedded_manifests": image.manifests(),
                "tls_directory": "present" if any(image.directory(9)) else "absent",
                "clr_directory": "present" if any(image.directory(14)) else "absent",
                "dynamic_loader_capability_indicators": indicators,
            }
        return {"schema": SCHEMA, "dll": dll}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def observe(external_root: Path) -> dict[str, Any]:
    first, second = observe_once(external_root), observe_once(external_root)
    canonical_first = json.dumps(first, sort_keys=True, separators=(",", ":"))
    if canonical_first != json.dumps(second, sort_keys=True, separators=(",", ":")):
        raise ObservationError("fresh_observation_source_drift")
    return {"schema": SCHEMA, "status": "external_only_static_loader_declarations_observed_dynamic_runtime_closure_and_worker_admission_blocked", "external_root_retained": False, "fresh_materializations": 2, "canonical_report_sha256": digest(canonical_first.encode("utf-8")), "dll": first["dll"], "non_claims": ["not_dynamic_or_runtime_dependency_closure", "not_worker_admission_or_dll_load", "not_sidecar_admission", "not_ami_or_ibis_compatibility", "not_rights_packaging_release_or_default_route", "not_getwave_or_numerical_parity"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = arguments.report.resolve()
        if ROOT == report or ROOT in report.parents or report.exists():
            raise ObservationError("report_must_be_new_and_outside_product_root")
        result = observe(arguments.external_root)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    except (ObservationError, OSError, UnicodeError, struct.error) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
