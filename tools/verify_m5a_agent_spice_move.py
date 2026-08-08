"""Verify the M5A-07 single-source Rust crate move and its PE evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "docs" / "baselines" / "migrations" / "m5a-agent-spice-move.v1.json"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _normalize_pe_build_metadata(data: bytes) -> bytes:
    """Remove PE linker metadata that varies with an otherwise identical build."""
    image = bytearray(data)
    if len(image) < 0x40 or image[:2] != b"MZ":
        raise ValueError("not a PE image")
    pe_offset = struct.unpack_from("<I", image, 0x3C)[0]
    if pe_offset + 24 > len(image) or image[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("PE header missing")

    section_count = struct.unpack_from("<H", image, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", image, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    if optional_offset + optional_size > len(image):
        raise ValueError("truncated PE optional header")
    optional_magic = struct.unpack_from("<H", image, optional_offset)[0]
    data_directory_offset = optional_offset + (112 if optional_magic == 0x20B else 96)
    if optional_magic not in {0x10B, 0x20B} or data_directory_offset + 56 > optional_offset + optional_size:
        raise ValueError("unsupported PE optional header")

    # IMAGE_FILE_HEADER.TimeDateStamp.
    struct.pack_into("<I", image, pe_offset + 8, 0)
    debug_rva, debug_size = struct.unpack_from("<II", image, data_directory_offset + 48)
    section_table = optional_offset + optional_size

    def raw_offset(rva: int) -> int:
        for index in range(section_count):
            offset = section_table + index * 40
            if offset + 40 > len(image):
                break
            virtual_address = struct.unpack_from("<I", image, offset + 12)[0]
            raw_size = struct.unpack_from("<I", image, offset + 16)[0]
            raw_pointer = struct.unpack_from("<I", image, offset + 20)[0]
            if virtual_address <= rva < virtual_address + max(raw_size, 1):
                return raw_pointer + rva - virtual_address
        raise ValueError("debug directory RVA is outside PE sections")

    if debug_rva == 0 and debug_size == 0:
        return bytes(image)
    if debug_size % 28:
        raise ValueError("malformed PE debug directory")
    directory_offset = raw_offset(debug_rva)
    if directory_offset + debug_size > len(image):
        raise ValueError("truncated PE debug directory")
    for offset in range(directory_offset, directory_offset + debug_size, 28):
        # IMAGE_DEBUG_DIRECTORY.TimeDateStamp.
        struct.pack_into("<I", image, offset + 4, 0)
        debug_type = struct.unpack_from("<I", image, offset + 12)[0]
        raw_pointer = struct.unpack_from("<I", image, offset + 24)[0]
        # CodeView RSDS contains a linker-generated GUID after its signature.
        if debug_type == 2 and raw_pointer + 20 <= len(image) and image[raw_pointer : raw_pointer + 4] == b"RSDS":
            image[raw_pointer + 4 : raw_pointer + 20] = bytes(16)
    return bytes(image)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _artifact_report(record: dict, before: Path, after: Path) -> dict:
    before_bytes = before.read_bytes()
    after_bytes = after.read_bytes()
    before_info = json.loads(subprocess.check_output([str(before), "build-info", "--json"], text=True))
    after_info = json.loads(subprocess.check_output([str(after), "build-info", "--json"], text=True))
    evidence = record["baseline_tag"]["artifact_equivalence"]
    report = {
        "before_sha256": _sha256(before_bytes),
        "after_sha256": _sha256(after_bytes),
        "normalized_before_sha256": _sha256(_normalize_pe_build_metadata(before_bytes)),
        "normalized_after_sha256": _sha256(_normalize_pe_build_metadata(after_bytes)),
        "build_info_equal": before_info == after_info,
    }
    report["valid"] = (
        report["normalized_before_sha256"] == report["normalized_after_sha256"]
        and report["build_info_equal"]
        and before_info == evidence["build_info"]
    )
    return report


def verify(root: Path, record_path: Path = RECORD_PATH) -> dict:
    blockers: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"ready": False, "blockers": [f"move record unreadable: {error}"]}
    if record.get("schema") != "sipi.migration-move.v1":
        blockers.append("move record schema mismatch")
        return {"ready": False, "blockers": blockers}

    source = record.get("source", {})
    target = record.get("target", {})
    source_commit = source.get("commit")
    source_path = source.get("path")
    target_path = target.get("path")
    if not all(isinstance(value, str) and value for value in (source_commit, source_path, target_path)):
        blockers.append("move record source/target identity missing")
    else:
        try:
            source_tree = _git(root, "rev-parse", f"{source_commit}:{source_path}")
            target_tree = _git(root, "rev-parse", f"HEAD:{target_path}")
            if source_tree != source.get("tree") or target_tree != target.get("tree"):
                blockers.append("move record tree evidence mismatch")
            source_files = _git(root, "ls-tree", "-r", "--name-only", source_commit, "--", source_path).splitlines()
            target_files = _git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", target_path).splitlines()
            source_relative = {path.removeprefix(f"{source_path}/") for path in source_files}
            target_relative = {path.removeprefix(f"{target_path}/") for path in target_files}
            if source_relative != target_relative:
                blockers.append("moved crate file set differs from pre-move source")
            adjustments = {
                item.get("path")
                for item in target.get("path_adjustments", [])
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            changed = set()
            for relative in source_relative & target_relative:
                source_blob = _git(root, "rev-parse", f"{source_commit}:{source_path}/{relative}")
                target_blob = _git(root, "rev-parse", f"HEAD:{target_path}/{relative}")
                if source_blob != target_blob:
                    changed.add(relative)
            if changed != adjustments:
                blockers.append("crate content changes are not exactly the recorded path adjustments")
            if _git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", source_path):
                blockers.append("pre-move crate path remains tracked")
            filtered_commit = source.get("filtered_commit")
            if not isinstance(filtered_commit, str) or not filtered_commit:
                blockers.append("move record filtered-history commit missing")
            else:
                ancestry = subprocess.run(
                    ["git", "-C", str(root), "merge-base", "--is-ancestor", filtered_commit, "HEAD"],
                    capture_output=True,
                    text=True,
                )
                if ancestry.returncode:
                    blockers.append("filtered crate history is not an ancestor of the target move")
        except subprocess.CalledProcessError as error:
            blockers.append(f"git move evidence unavailable: {error.stderr.strip()}")

    cargo_path = f"{target_path}/Cargo.toml" if isinstance(target_path, str) else ""
    try:
        cargo = _git(root, "show", f"HEAD:{cargo_path}")
        for required in ('name = "agent-spice-sim"', 'name = "agent_spice_sim"'):
            if required not in cargo:
                blockers.append(f"moved crate no longer preserves {required}")
    except subprocess.CalledProcessError:
        blockers.append("moved crate Cargo.toml is unavailable")

    return {
        "ready": not blockers,
        "source_commit": source_commit,
        "filtered_commit": source.get("filtered_commit"),
        "source_path": source_path,
        "target_path": target_path,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--record", type=Path, default=RECORD_PATH)
    parser.add_argument("--before-executable", type=Path)
    parser.add_argument("--after-executable", type=Path)
    args = parser.parse_args()
    report = verify(args.root.resolve(), args.record)
    if bool(args.before_executable) != bool(args.after_executable):
        parser.error("--before-executable and --after-executable must be supplied together")
    if args.before_executable:
        artifact = _artifact_report(json.loads(args.record.read_text(encoding="utf-8")), args.before_executable, args.after_executable)
        report["artifact_equivalence"] = artifact
        report["ready"] = report["ready"] and artifact["valid"]
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
