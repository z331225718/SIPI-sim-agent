"""Observe the fixed P7 current-candidate PE rejection without changing policy.

This observer is external-only. It admits two independently built, hash-pinned
executables and the retained layout policy, then records only the static PE
category that explains the existing ``pe_rejected`` result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p7-current-candidate-static-pe-rejection-observation.v1"
EXPECTED_EXECUTABLE_SHA256 = "a3059d052df54c0f3ebbd727bd2f71760ff33f73af82e1e2f29c0ec35b8c882d"
EXPECTED_EXECUTABLE_BYTES = 3_908_608
EXPECTED_POLICY_SHA256 = "a0ac8e7efd9d2c35a69aa6f48f8cb063cb837b779d18be0a21f39e0132e11ce2"
MAX_IMPORT_DESCRIPTORS = 65_536


class ObservationError(RuntimeError):
    pass


class PeParseError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_reparse(path: Path) -> bool:
    return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def has_link_or_reparse_ancestor(path: Path) -> bool:
    current = path
    while current != current.parent:
        try:
            if current.is_symlink() or is_reparse(current):
                return True
        except OSError:
            return True
        current = current.parent
    return False


def external_regular_file(path: Path, reason: str) -> Path:
    resolved = path.resolve()
    if (
        ROOT == resolved
        or ROOT in resolved.parents
        or not path.is_file()
        or path.is_symlink()
        or is_reparse(path)
        or has_link_or_reparse_ancestor(path.parent)
    ):
        raise ObservationError(reason)
    return resolved


def identity(path: Path) -> tuple[int, str, bytes]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ObservationError("external_input_unavailable") from error
    return len(data), sha256(data), data


def u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise PeParseError("invalid_pe")
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise PeParseError("invalid_pe")
    return struct.unpack_from("<I", data, offset)[0]


def c_string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise PeParseError("malformed_import_table")
    end = data.find(b"\0", offset)
    if end < 0:
        raise PeParseError("malformed_import_table")
    try:
        value = data[offset:end].decode("ascii", "strict").lower()
    except UnicodeDecodeError as error:
        raise PeParseError("malformed_import_name") from error
    if (
        not value.endswith(".dll")
        or not value
        or any(character in value for character in "/\\:")
        or any(ord(character) < 32 for character in value)
    ):
        raise PeParseError("malformed_import_name")
    return value


class PeImage:
    def __init__(self, data: bytes) -> None:
        if data[:2] != b"MZ":
            raise PeParseError("invalid_pe")
        pe_offset = u32(data, 0x3C)
        if data[pe_offset:pe_offset + 4] != b"PE\0\0":
            raise PeParseError("invalid_pe")
        coff = pe_offset + 4
        optional = coff + 20
        optional_size = u16(data, coff + 16)
        if u16(data, optional) != 0x20B or optional + optional_size > len(data):
            raise PeParseError("invalid_pe")
        if u32(data, optional + 108) < 14:
            raise PeParseError("invalid_pe")
        section_count = u16(data, coff + 2)
        section_offset = optional + optional_size
        if section_offset + section_count * 40 > len(data):
            raise PeParseError("invalid_pe")
        self.data = data
        self.machine = u16(data, coff)
        self.directories = optional + 112
        self.sections: list[tuple[int, int, int, int]] = []
        for index in range(section_count):
            offset = section_offset + index * 40
            virtual_address = u32(data, offset + 12)
            virtual_size = u32(data, offset + 8)
            raw_size = u32(data, offset + 16)
            raw_offset = u32(data, offset + 20)
            if raw_offset + raw_size > len(data):
                raise PeParseError("invalid_pe")
            self.sections.append((virtual_address, max(virtual_size, raw_size), raw_offset, raw_size))

    def directory(self, index: int) -> tuple[int, int]:
        offset = self.directories + index * 8
        return u32(self.data, offset), u32(self.data, offset + 4)

    def rva_offset(self, rva: int) -> int:
        for start, span, raw, raw_size in self.sections:
            if start <= rva < start + span:
                offset = raw + rva - start
                if offset < raw + raw_size and offset < len(self.data):
                    return offset
        raise PeParseError("malformed_import_table")

    def normal_imports(self) -> list[str]:
        rva, size = self.directory(1)
        if rva == 0 and size == 0:
            return []
        if rva == 0 or size < 20:
            raise PeParseError("malformed_import_table")
        offset = self.rva_offset(rva)
        entries = min(MAX_IMPORT_DESCRIPTORS, size // 20 + 1)
        imports: list[str] = []
        for _ in range(entries):
            original_first_thunk = u32(self.data, offset)
            name_rva = u32(self.data, offset + 12)
            first_thunk = u32(self.data, offset + 16)
            if original_first_thunk == 0 and name_rva == 0 and first_thunk == 0:
                return sorted(set(imports))
            if name_rva == 0:
                raise PeParseError("malformed_import_table")
            imports.append(c_string(self.data, self.rva_offset(name_rva)))
            offset += 20
        raise PeParseError("malformed_import_table")


def parse_policy(data: bytes) -> tuple[list[str], list[str]]:
    try:
        policy = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("layout_policy_invalid") from error
    if not isinstance(policy, dict) or set(policy) != {
        "schema", "platform", "expectedExecutable", "requiredFiles", "optionalFiles",
        "normalImportDllAllowlist", "forbiddenImportDllTokens", "smoke",
    }:
        raise ObservationError("layout_policy_invalid")
    allowed = policy.get("normalImportDllAllowlist")
    forbidden = policy.get("forbiddenImportDllTokens")
    if (
        policy.get("schema") != "sipi.release-layout-policy.v1"
        or policy.get("platform") != "windows-x86_64"
        or not isinstance(allowed, list)
        or not isinstance(forbidden, list)
        or any(not isinstance(value, str) or not value for value in allowed + forbidden)
    ):
        raise ObservationError("layout_policy_invalid")
    return sorted({value.lower() for value in allowed}), sorted({value.lower() for value in forbidden})


def classify(data: bytes, allowed: list[str], forbidden: list[str]) -> dict[str, Any]:
    try:
        image = PeImage(data)
    except PeParseError as error:
        return {"pe_parse_status": "rejected", "rejection_classification": str(error)}
    if image.machine != 0x8664:
        return {
            "pe_parse_status": "parsed",
            "machine": f"pe_machine_0x{image.machine:04x}",
            "rejection_classification": "wrong_machine",
        }
    delay_rva, delay_size = image.directory(13)
    if delay_rva != 0 or delay_size != 0:
        return {
            "pe_parse_status": "parsed",
            "machine": "windows-x86_64",
            "delay_import_directory_present": True,
            "rejection_classification": "delay_import_directory_present",
        }
    try:
        imports = image.normal_imports()
    except PeParseError as error:
        return {
            "pe_parse_status": "parsed",
            "machine": "windows-x86_64",
            "delay_import_directory_present": False,
            "rejection_classification": str(error),
        }
    allowed_set = set(allowed)
    allowed_imports = sorted(name for name in imports if name in allowed_set)
    disallowed = sorted(name for name in imports if name not in allowed_set)
    forbidden_matches = sorted(name for name in imports if any(token in name for token in forbidden))
    return {
        "pe_parse_status": "parsed",
        "machine": "windows-x86_64",
        "delay_import_directory_present": False,
        "normal_import_dlls": imports,
        "allowed_import_dlls": allowed_imports,
        "disallowed_import_dlls": disallowed,
        "forbidden_token_import_dlls": forbidden_matches,
        "rejection_classification": (
            "normal_import_disallowed" if disallowed or forbidden_matches else "layout_compatible"
        ),
    }


def observe_one(source: Path, policy: bytes, allowed: list[str], forbidden: list[str]) -> dict[str, Any]:
    before_length, before_hash, before = identity(source)
    if (before_length, before_hash) != (EXPECTED_EXECUTABLE_BYTES, EXPECTED_EXECUTABLE_SHA256):
        raise ObservationError("candidate_executable_identity_drift")
    temporary = Path(tempfile.mkdtemp(prefix="sipi-p7-pe-diagnosis-"))
    try:
        copied = temporary / "sipi.exe"
        shutil.copyfile(source, copied)
        after_length, after_hash, _ = identity(source)
        copied_length, copied_hash, copied_bytes = identity(copied)
        if (after_length, after_hash) != (before_length, before_hash):
            raise ObservationError("candidate_executable_changed_during_materialization")
        if (copied_length, copied_hash) != (before_length, before_hash):
            raise ObservationError("candidate_executable_copy_mismatch")
        return classify(copied_bytes, allowed, forbidden)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def observe(first: Path, second: Path, policy_path: Path) -> dict[str, Any]:
    first = external_regular_file(first, "first_executable_unavailable")
    second = external_regular_file(second, "second_executable_unavailable")
    policy_path = external_regular_file(policy_path, "layout_policy_unavailable")
    if first == second:
        raise ObservationError("fresh_executable_sources_not_distinct")
    policy_length, policy_hash, policy = identity(policy_path)
    if policy_hash != EXPECTED_POLICY_SHA256:
        raise ObservationError("layout_policy_identity_drift")
    allowed, forbidden = parse_policy(policy)
    first_observation = observe_one(first, policy, allowed, forbidden)
    second_observation = observe_one(second, policy, allowed, forbidden)
    _, policy_hash_after, _ = identity(policy_path)
    if policy_hash_after != policy_hash:
        raise ObservationError("layout_policy_changed_during_observation")
    canonical_first = json.dumps(first_observation, sort_keys=True, separators=(",", ":"))
    canonical_second = json.dumps(second_observation, sort_keys=True, separators=(",", ":"))
    if canonical_first != canonical_second:
        raise ObservationError("fresh_observation_result_mismatch")
    return {
        "schema": SCHEMA,
        "status": "external_static_pe_rejection_diagnosed_current_candidate_chain_remains_blocked",
        "fresh_materializations": 2,
        "policy": {"byte_length": policy_length, "sha256": policy_hash},
        "executable": {"byte_length": EXPECTED_EXECUTABLE_BYTES, "sha256": EXPECTED_EXECUTABLE_SHA256},
        "observation": first_observation,
        "canonical_observation_sha256": sha256(canonical_first.encode("utf-8")),
        "non_claims": [
            "not_a_layout_policy_change_or_allowlist_expansion",
            "not_static_or_dynamic_dependency_closure",
            "not_composition_archive_install_performance_or_candidate_evaluation",
            "not_release_readiness_or_promotion",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-executable", type=Path, required=True)
    parser.add_argument("--second-executable", type=Path, required=True)
    parser.add_argument("--layout-policy", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report_input = arguments.report
        report = report_input.resolve()
        if (
            ROOT == report or ROOT in report.parents or report.exists() or report_input.is_symlink()
            or has_link_or_reparse_ancestor(report_input.parent)
        ):
            raise ObservationError("report_must_be_new_and_outside_product_root")
        result = observe(arguments.first_executable, arguments.second_executable, arguments.layout_policy)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    except (ObservationError, OSError, struct.error) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
