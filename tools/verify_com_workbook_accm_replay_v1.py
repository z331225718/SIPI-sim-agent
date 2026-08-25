"""Fail-closed verifier for the COM workbook/ACCM preparation schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

REPORT_SCHEMA = "sipi.com.workbook-accm-replay-prep.v4"
AGGREGATE_SCHEMA = "sipi.com.workbook-accm-replay-aggregate-prep.v4"
CANDIDATE = {"commit": "2e18a6a27cf8abc0555e24e0346a54c4ea577baf", "tree": "bfdc3e0ddd9bc76737528011e6dddc94c728f059", "archive": {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": 0, "bytes": 44615680, "sha256": "67b071cf9302d932ed2b974db3c7d82cb1e70c4b7f0dac276d788b88f1a64993"}}
FIXED_CARGO_HOME = Path("C:/sipi-cargo-home-v1")
CARGO_INVENTORY_COUNT = 7727
CARGO_INVENTORY_TOTAL_BYTES = 234108979
CARGO_INVENTORY_SHA256 = "d841c89ca7eef7018c6be0bf622cb55df079bd3cc39e7d15b9d802dd7f694c3f"
PE_EXPECTED = {"pe_offset": 120, "optional_header_offset": 144, "debug_directory_raw_pointer": 5888732, "machine": 0x8664, "optional_magic": 0x20B, "characteristics": 34, "debug_entries": 2, "codeview_rva": 5893908, "codeview_raw_pointer": 5888788, "codeview_bytes": 48, "repro_entries": 1, "canonical_sha256": "d6b133d9ca509c19c7ee112634d534b7d8b1c6e9d579255ff22de0ee46c56e87"}
PE_NORMALIZATION = [{"role": "coff_timestamp", "offset": 128, "bytes": 4}, {"role": "debug_timestamp", "offset": 5888736, "bytes": 4}, {"role": "rsds_guid", "offset": 5888792, "bytes": 16}, {"role": "debug_timestamp", "offset": 5888764, "bytes": 4}, {"role": "pe_checksum", "offset": 208, "bytes": 4}]
PE_SECTION_SHAPE = [(".text", 4096, 5494758, 1024, 5494784), (".rdata", 5500928, 753084, 5495808, 753152), (".data", 6254592, 5480, 6248960, 4096), (".pdata", 6262784, 95892, 6253056, 96256), (".tls", 6361088, 113, 6349312, 512), (".reloc", 6365184, 7876, 6349824, 8192)]
UPSTREAM = {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "runtime": "not_executed_external_only"}
FIXTURE_KEYS = ("workbook", "s4p")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])(?:[A-Za-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
SOURCE_PATHS = ("src/agent_com/api.py", "src/agent_com/_orchestration.py", "src/agent_com/network/package.py", "src/agent_com/network/two_port.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/search.py")
EXPECTED_SOURCE_INVENTORY = {
    "src/agent_com/api.py": {"git_blob_sha1": "3e7808982a63123f2bac65a86f3abb627c287be1", "bytes": 21445, "sha256": "b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570", "license": "MIT"},
    "src/agent_com/_orchestration.py": {"git_blob_sha1": "5d260a0aab941f1a1955fe3abef36d85a56034c0", "bytes": 90877, "sha256": "069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69", "license": "MIT"},
    "src/agent_com/network/package.py": {"git_blob_sha1": "55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f", "bytes": 22300, "sha256": "bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32", "license": "MIT"},
    "src/agent_com/network/two_port.py": {"git_blob_sha1": "6b1484effc18a25fe8c28373b47f55b0b99b0f4b", "bytes": 9600, "sha256": "8889d9695a56d83a59a771d938ba8084dbdfec6a24d79e14d88b83c678ddcd6a", "license": "MIT"},
    "src/agent_com/signal/fd_to_td.py": {"git_blob_sha1": "6f3af024ea20df0011843ea19a090788f1aabbc9", "bytes": 5831, "sha256": "703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687", "license": "MIT"},
    "src/agent_com/equalization/search.py": {"git_blob_sha1": "58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd", "bytes": 53859, "sha256": "924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d", "license": "MIT"},
}
EXPECTED_FIXTURES = {"workbook": {"path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae", "bytes": 67087, "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"}, "s4p": {"path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p", "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0", "bytes": 6457063, "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec"}}
REPORT_KEYS = {"schema", "run_id", "nonce", "candidate", "upstream", "fixtures", "toolchain", "build", "execution", "controls", "runs", "parity", "non_claims"}
RESULT_KEYS = {"schema_version", "source_revision", "profile", "cases", "provenance", "warnings", "timings_s", "input_manifest", "report_manifest"}
ENV_KEYS = ("SystemRoot", "ComSpec", "PATHEXT", "WINDIR", "PATH", "LIB", "LIBPATH", "INCLUDE", "VCINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir", "WindowsSDKVersion", "UCRTVersion", "UniversalCRTSdkDir", "TEMP", "TMP", "CARGO_HOME", "RUSTC", "CARGO_BUILD_RUSTC", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CL", "_CL_", "LINK")
ENV_ROLES = {"SystemRoot": "system_root", "ComSpec": "cmd", "PATHEXT": "system_path_ext", "WINDIR": "system_root", "TEMP": "fresh_run_temp", "TMP": "fresh_run_temp", "CARGO_HOME": "cargo_home", "RUSTC": "resolved_tool", "CARGO_BUILD_RUSTC": "resolved_tool", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": "resolved_tool", "RUSTC_WRAPPER": "cleared_wrapper", "RUSTC_WORKSPACE_WRAPPER": "cleared_wrapper", "CARGO_BUILD_RUSTC_WRAPPER": "cleared_wrapper", "CARGO_INCREMENTAL": "incremental_zero", "CARGO_NET_OFFLINE": "offline", "RUSTFLAGS": "deterministic_flags", "CARGO_ENCODED_RUSTFLAGS": "deterministic_encoded_flags", "CL": "native_deterministic_flags", "_CL_": "cleared_native_flags", "LINK": "cleared_linker_override"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def hex64(value: Any, label: str) -> None:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ValueError(f"invalid {label}")


def verify_registry_inventory(value: Any) -> None:
    exact(value, {"entries", "count", "total_bytes", "sha256"}, "registry inventory")
    entries = value["entries"]
    if not isinstance(entries, dict) or not entries:
        raise ValueError("registry inventory must be non-empty")
    if not isinstance(value["count"], int) or isinstance(value["count"], bool) or value["count"] != len(entries) or value["count"] <= 0:
        raise ValueError("registry inventory count drift")
    if not isinstance(value["total_bytes"], int) or isinstance(value["total_bytes"], bool) or value["total_bytes"] <= 0:
        raise ValueError("registry inventory byte total drift")
    canonical = {}
    total = 0
    for path, item in entries.items():
        if not isinstance(path, str) or PurePosixPath(path).is_absolute() or any(part in ("", ".", "..") for part in PurePosixPath(path).parts) or path.startswith("registry/") is False:
            raise ValueError("registry inventory path drift")
        exact(item, {"bytes", "sha256"}, "registry inventory entry")
        if not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or item["bytes"] < 0:
            raise ValueError("registry inventory entry size drift")
        hex64(item["sha256"], "registry inventory entry sha")
        canonical[path] = item
        total += item["bytes"]
    encoded = json.dumps({key: canonical[key] for key in sorted(canonical)}, sort_keys=True, separators=(",", ":")).encode()
    if value["total_bytes"] != total or value["sha256"] != hashlib.sha256(encoded).hexdigest():
        raise ValueError("registry inventory digest drift")
    hex64(value["sha256"], "registry inventory sha")


def recompute_registry_inventory(cargo_home: Path, expected: dict[str, Any]) -> None:
    for forbidden in ("config", "config.toml", "credentials", "credentials.toml"):
        if (cargo_home / forbidden).exists():
            raise ValueError("cargo home contains an unbound configuration override")
    src = cargo_home / "registry" / "src"
    if not src.is_dir() or is_reparse_point(src):
        raise ValueError("cargo registry source root is unavailable")
    def walk(root: Path) -> set[str]:
        if not root.is_dir() or is_reparse_point(root):
            raise ValueError("cargo registry root contains a reparse point")
        files = set()
        pending = [root]
        while pending:
            current = pending.pop()
            for child in current.iterdir():
                if is_reparse_point(child):
                    raise ValueError("cargo registry inventory contains a reparse point")
                if child.is_dir():
                    pending.append(child)
                elif child.is_file():
                    files.add(child.as_posix())
                else:
                    raise ValueError("cargo registry inventory contains a non-regular entry")
        return files
    src_files = walk(src)
    cache_files = walk(cargo_home / "registry" / "cache")
    index_files = walk(cargo_home / "registry" / "index")
    selected_src_files: set[str] = set()
    expected_src_files: set[str] = set()
    actual: dict[str, dict[str, Any]] = {}
    package_file_cache: dict[Path, set[str]] = {}
    for key in expected["entries"]:
        if key.startswith("registry/src/"):
            _, _, remainder = key.partition("registry/src/")
            package, _, relative = remainder.partition("/")
            matches = []
            for channel in sorted(src.iterdir()):
                if is_reparse_point(channel) or not channel.is_dir():
                    continue
                package_root = channel / package
                candidate = package_root / relative
                if candidate.exists():
                    matches.append((candidate, package_root))
            if len(matches) != 1:
                raise ValueError("registry source entry cannot be mechanically resolved")
            path, package_root = matches[0]
            selected_src_files.update(package_file_cache.setdefault(package_root, walk(package_root)))
            expected_src_files.add(path.as_posix())
        else:
            path = cargo_home / key
            if key.startswith("registry/cache/"):
                expected_root = cargo_home / "registry" / "cache"
                expected_set = cache_files
            elif key.startswith("registry/index/"):
                expected_root = cargo_home / "registry" / "index"
                expected_set = index_files
            else:
                raise ValueError("unknown registry inventory channel")
            expected_src_files.add(path.as_posix())
            if path.as_posix() not in expected_set:
                raise ValueError("registry inventory omitted or added a file")
        if is_reparse_point(path) or not path.is_file():
            raise ValueError("registry inventory entry is not a regular file")
        stat = path.stat()
        if stat.st_size > 256 * 1024 * 1024:
            raise ValueError("registry inventory entry exceeds bound")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        actual[key] = {"bytes": size, "sha256": digest.hexdigest()}
    if selected_src_files != expected_src_files & src_files:
        raise ValueError("registry source inventory omitted or added a file")
    expected_cache = {str((cargo_home / key).as_posix()) for key in expected["entries"] if key.startswith("registry/cache/")}
    expected_index = {str((cargo_home / key).as_posix()) for key in expected["entries"] if key.startswith("registry/index/")}
    if expected_cache != cache_files or expected_index != index_files:
        raise ValueError("registry cache/index inventory omitted or added a file")
    if actual != expected["entries"]:
        raise ValueError("registry inventory does not match fixed cargo home bytes")


def verify_fixed_candidate_binding(value: dict[str, Any]) -> None:
    before = value["build"]["cargo_registry_inventory_before"]
    after = value["build"]["cargo_registry_inventory_after"]
    for inventory in (before, after):
        if inventory["count"] != CARGO_INVENTORY_COUNT or inventory["total_bytes"] != CARGO_INVENTORY_TOTAL_BYTES or inventory["sha256"] != CARGO_INVENTORY_SHA256:
            raise ValueError("fixed cargo inventory hard anchor drift")
    for phase in ("binary_pre", "binary"):
        binary = value["candidate"][phase]
        if not binary["exists"]:
            raise ValueError("fixed candidate build did not produce a PE")
        for key, expected in PE_EXPECTED.items():
            if binary.get(key) != expected:
                raise ValueError(f"fixed PE hard anchor drift: {key}")
        if binary["normalization_map"] != PE_NORMALIZATION:
            raise ValueError("fixed PE normalization map drift")
        shape = [(item["name"], item["virtual_address"], item["virtual_bytes"], item["raw_pointer"], item["bytes"]) for item in binary["sections"]]
        if shape != PE_SECTION_SHAPE:
            raise ValueError("fixed PE section layout drift")


def path_free(value: Any) -> None:
    if isinstance(value, str):
        if value == "<abs-path>":
            return
        if value in {"/Bv", "/?", "/nologo", "/d", "/c", "/Brepro", "<canonical-cargo-home>=C:/sipi-cargo", "<canonical-source>=C:/sipi-source", "<canonical-target>=C:/sipi-target", "<canonical-temp>=C:/sipi-temp", "-C link-arg=/Brepro", "link-arg=/Brepro"}:
            return
        if "<abs-path>" in value:
            raise ValueError("embedded redaction token")
        normalized = value.replace("\\", "/")
        if PATH_LEAK.search(normalized) or "/../" in normalized or normalized.endswith("/.."):
            raise ValueError("absolute path leaked")
    elif isinstance(value, dict):
        for item in value.values():
            path_free(item)
    elif isinstance(value, list):
        for item in value:
            path_free(item)


def exact(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} key set drift")


def stable_candidate(value: dict[str, Any]) -> dict[str, Any]:
    """Compare cross-run typed PE identity while allowing approved raw custody drift."""
    result = json.loads(json.dumps(value))
    for phase in ("binary_pre", "binary"):
        binary = result.get(phase)
        if isinstance(binary, dict) and binary.get("exists"):
            binary["sha256"] = "<raw-binary>"
            binary["pdb_guid"] = "<typed-rsds-guid>"
            for section in binary.get("sections", []):
                section["sha256"] = "<raw-section>"
    custody = result.get("binary_custody")
    if isinstance(custody, dict):
        if "id" in custody:
            custody["id"] = "<custody-id>"
        for phase in ("pre", "post"):
            item = custody.get(phase)
            if isinstance(item, dict):
                if isinstance(item.get("exe"), dict):
                    item["exe"]["basename"] = "<custody-exe>"
                    item["exe"]["sha256"] = "<raw-custody-exe>"
                    item["exe"]["source_sha256"] = "<raw-source-exe>"
                if isinstance(item.get("pdb"), dict):
                    item["pdb"]["basename"] = "<custody-pdb>"
                    item["pdb"]["sha256"] = "<raw-custody-pdb>"
                    item["pdb"]["source_sha256"] = "<raw-source-pdb>"
    return result


def verify_report(path: Path, cargo_home: Path | None = None) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    exact(value, REPORT_KEYS, "report")
    if value["schema"] != REPORT_SCHEMA:
        raise ValueError("wrong report schema")
    if not isinstance(value["run_id"], str) or len(value["run_id"]) != 64 or value["run_id"] != value["run_id"].lower() or not HEX64.fullmatch(value["run_id"]):
        raise ValueError("invalid run id")
    hex64(value["nonce"], "nonce")
    candidate = value["candidate"]
    exact(candidate, {"commit", "tree", "archive", "binary_pre", "binary", "binary_custody"}, "candidate")
    if candidate["commit"] != CANDIDATE["commit"] or candidate["tree"] != CANDIDATE["tree"] or candidate["archive"] != CANDIDATE["archive"]:
        raise ValueError("candidate identity drift")
    for binary in (candidate["binary_pre"], candidate["binary"]):
        exact(binary, {"basename", "exists", "bytes", "sha256", "canonical_sha256", "pe_offset", "optional_header_offset", "debug_directory_raw_pointer", "machine", "optional_magic", "characteristics", "debug_entries", "codeview_rva", "codeview_raw_pointer", "codeview_bytes", "repro_entries", "pdb_basename", "repro", "sections", "normalization_map", "certificate_bytes", "overlay_bytes"}, "binary")
        if not isinstance(binary["basename"], str) or Path(binary["basename"]).name != binary["basename"] or not isinstance(binary["exists"], bool) or not isinstance(binary["bytes"], int) or isinstance(binary["bytes"], bool) or binary["bytes"] < 0:
            raise ValueError("binary custody invalid")
        if binary["exists"]:
            hex64(binary["sha256"], "binary sha")
            hex64(binary["canonical_sha256"], "binary canonical sha")
            if not isinstance(binary["pe_offset"], int) or binary["pe_offset"] < 0 or not isinstance(binary["optional_header_offset"], int) or binary["optional_header_offset"] != binary["pe_offset"] + 24 or not isinstance(binary["debug_directory_raw_pointer"], int) or binary["debug_directory_raw_pointer"] <= 0 or binary["machine"] != 0x8664 or binary["optional_magic"] != 0x20B or not isinstance(binary["characteristics"], int) or isinstance(binary["characteristics"], bool) or binary["characteristics"] & 0x0002 == 0 or not isinstance(binary["debug_entries"], int) or binary["debug_entries"] <= 0 or binary["repro_entries"] != 1 or not isinstance(binary["codeview_rva"], int) or binary["codeview_rva"] <= 0 or not isinstance(binary["codeview_raw_pointer"], int) or binary["codeview_raw_pointer"] <= 0 or not isinstance(binary["codeview_bytes"], int) or binary["codeview_bytes"] < 28 or not isinstance(binary["pdb_basename"], str) or Path(binary["pdb_basename"]).name != binary["pdb_basename"] or not binary["pdb_basename"].lower().endswith(".pdb") or binary["repro"] is not True:
                raise ValueError("binary PE debug identity invalid")
            if not isinstance(binary["normalization_map"], list) or [item.get("role") for item in binary["normalization_map"]].count("coff_timestamp") != 1 or [item.get("role") for item in binary["normalization_map"]].count("debug_timestamp") < 1 or [item.get("role") for item in binary["normalization_map"]].count("rsds_guid") != 1 or [item.get("role") for item in binary["normalization_map"]].count("pe_checksum") != 1:
                raise ValueError("binary normalization map incomplete")
            seen_ranges = []
            for item in binary["normalization_map"]:
                exact(item, {"role", "offset", "bytes"}, "binary normalization range")
                if item["role"] not in {"coff_timestamp", "debug_timestamp", "rsds_guid", "pe_checksum"} or not isinstance(item["offset"], int) or isinstance(item["offset"], bool) or item["offset"] < 0 or item["offset"] + item["bytes"] > binary["bytes"] or not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or item["bytes"] != {"coff_timestamp": 4, "debug_timestamp": 4, "rsds_guid": 16, "pe_checksum": 4}[item["role"]]:
                    raise ValueError("binary normalization range invalid")
                span = (item["offset"], item["offset"] + item["bytes"])
                if any(left < span[1] and span[0] < right for left, right in seen_ranges):
                    raise ValueError("binary normalization ranges overlap")
                seen_ranges.append(span)
            if [item["role"] for item in binary["normalization_map"]].count("coff_timestamp") != 1 or [item["role"] for item in binary["normalization_map"]].count("pe_checksum") != 1 or [item["role"] for item in binary["normalization_map"]].count("rsds_guid") != 1 or [item["role"] for item in binary["normalization_map"]].count("debug_timestamp") != binary["debug_entries"]:
                raise ValueError("binary normalization role/count drift")
            by_role = {role: [item for item in binary["normalization_map"] if item["role"] == role] for role in ("coff_timestamp", "pe_checksum", "rsds_guid", "debug_timestamp")}
            if by_role["coff_timestamp"][0]["offset"] != binary["pe_offset"] + 8 or by_role["pe_checksum"][0]["offset"] != binary["optional_header_offset"] + 64 or by_role["rsds_guid"][0]["offset"] != binary["codeview_raw_pointer"] + 4 or [item["offset"] for item in by_role["debug_timestamp"]] != [binary["debug_directory_raw_pointer"] + 4 + 28 * index for index in range(binary["debug_entries"])] :
                raise ValueError("binary PE structural map drift")
            if binary["certificate_bytes"] != 0 or binary["overlay_bytes"] != 0:
                raise ValueError("PE certificate or overlay is not admitted")
            if not isinstance(binary["sections"], list) or not binary["sections"]:
                raise ValueError("binary PE section inventory missing")
            for section in binary["sections"]:
                exact(section, {"name", "virtual_address", "virtual_bytes", "raw_pointer", "bytes", "sha256"}, "binary section")
                if not isinstance(section["name"], str) or not section["name"] or any(not isinstance(section[key], int) or isinstance(section[key], bool) or section[key] < 0 for key in ("virtual_address", "virtual_bytes", "raw_pointer", "bytes")):
                    raise ValueError("binary section shape invalid")
                hex64(section["sha256"], "binary section sha")
            mappings = [section for section in binary["sections"] if section["virtual_address"] <= binary["codeview_rva"] < section["virtual_address"] + max(section["virtual_bytes"], section["bytes"]) and binary["codeview_rva"] - section["virtual_address"] + binary["codeview_bytes"] <= section["bytes"] and section["raw_pointer"] + binary["codeview_rva"] - section["virtual_address"] == binary["codeview_raw_pointer"]]
            if len(mappings) != 1:
                raise ValueError("CodeView RVA/raw pointer does not map to exactly one section")
        elif binary["sha256"] is not None:
            raise ValueError("missing binary cannot have sha")
        elif binary["canonical_sha256"] is not None:
            raise ValueError("missing binary cannot have canonical sha")
        elif any(binary[key] is not None for key in ("pe_offset", "optional_header_offset", "debug_directory_raw_pointer", "machine", "optional_magic", "characteristics", "codeview_rva", "codeview_raw_pointer", "codeview_bytes")) or binary["debug_entries"] != 0 or binary["repro_entries"] != 0 or binary["pdb_basename"] is not None or binary["repro"] is not False or binary["sections"] != [] or binary["normalization_map"] != [] or binary["certificate_bytes"] != 0 or binary["overlay_bytes"] != 0:
            raise ValueError("missing binary cannot have debug identity")
    if candidate["binary_pre"] != candidate["binary"]:
        raise ValueError("binary custody changed during runtime")
    custody = candidate["binary_custody"]
    if not isinstance(custody, dict) or set(custody) != {"id", "pre", "post"} or custody["pre"] != custody["post"]:
        raise ValueError("external binary custody drift")
    if custody["id"] != value["run_id"] or not re.fullmatch(r"[0-9a-f]{64}", custody["id"]):
        raise ValueError("external custody run directory identity drift")
    if custody["pre"] is None:
        if custody["post"] is not None:
            raise ValueError("missing external binary custody drift")
    elif not isinstance(custody["pre"], dict):
        raise ValueError("external binary custody shape invalid")
    for item in (custody["pre"], custody["post"]):
        if item is None:
            continue
        exact(item, {"exe", "pdb"}, "external binary custody")
        exact(item["exe"], {"basename", "bytes", "sha256", "source_bytes", "source_sha256"}, "external exe custody")
        if not isinstance(item["exe"]["basename"], str) or Path(item["exe"]["basename"]).name != item["exe"]["basename"] or not isinstance(item["exe"]["bytes"], int) or isinstance(item["exe"]["bytes"], bool) or item["exe"]["bytes"] <= 0:
            raise ValueError("external exe custody invalid")
        hex64(item["exe"]["sha256"], "external exe sha")
        if not isinstance(item["exe"]["source_bytes"], int) or isinstance(item["exe"]["source_bytes"], bool) or item["exe"]["source_bytes"] <= 0:
            raise ValueError("external exe source custody invalid")
        hex64(item["exe"]["source_sha256"], "external exe source sha")
        if item["pdb"] is not None:
            exact(item["pdb"], {"basename", "bytes", "sha256", "source_bytes", "source_sha256"}, "external pdb custody")
            if not isinstance(item["pdb"]["basename"], str) or Path(item["pdb"]["basename"]).name != item["pdb"]["basename"] or not isinstance(item["pdb"]["bytes"], int) or isinstance(item["pdb"]["bytes"], bool) or item["pdb"]["bytes"] <= 0:
                raise ValueError("external pdb custody invalid")
            hex64(item["pdb"]["sha256"], "external pdb sha")
            if not isinstance(item["pdb"]["source_bytes"], int) or isinstance(item["pdb"]["source_bytes"], bool) or item["pdb"]["source_bytes"] <= 0:
                raise ValueError("external PDB source custody invalid")
            hex64(item["pdb"]["source_sha256"], "external PDB source sha")
            if item["pdb"]["basename"] != candidate["binary"]["pdb_basename"] or item["pdb"]["bytes"] != item["pdb"]["source_bytes"] or item["pdb"]["sha256"] != item["pdb"]["source_sha256"]:
                raise ValueError("external PDB debug identity drift")
    if candidate["binary"]["exists"]:
        if custody["pre"] is None or custody["pre"]["pdb"] is None or custody["pre"]["exe"]["bytes"] != candidate["binary"]["bytes"] or custody["pre"]["exe"]["sha256"] != candidate["binary"]["sha256"] or custody["pre"]["exe"]["source_bytes"] != candidate["binary"]["bytes"] or custody["pre"]["exe"]["source_sha256"] != candidate["binary"]["sha256"]:
            raise ValueError("external executable custody does not bind candidate binary")
    if value["upstream"] != {**UPSTREAM, "source_inventory": value["upstream"].get("source_inventory")}:
        raise ValueError("upstream identity drift")
    inventory = value["upstream"]["source_inventory"]
    if set(inventory) != set(SOURCE_PATHS):
        raise ValueError("source inventory drift")
    if inventory != EXPECTED_SOURCE_INVENTORY:
        raise ValueError("source inventory is not pinned")
    for item in inventory.values():
        exact(item, {"git_blob_sha1", "bytes", "sha256", "license"}, "source inventory")
        if not isinstance(item["git_blob_sha1"], str) or not re.fullmatch(r"[0-9a-f]{40}", item["git_blob_sha1"]) or item["license"] != "MIT" or not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or item["bytes"] < 0:
            raise ValueError("source inventory identity invalid")
        hex64(item["sha256"], "source sha")
    fixtures = value["fixtures"]
    if set(fixtures) != set(FIXTURE_KEYS):
        raise ValueError("fixture key drift")
    for key in FIXTURE_KEYS:
        item = fixtures[key]
        expected_fixture = EXPECTED_FIXTURES[key] | {"basename": Path(EXPECTED_FIXTURES[key]["path"]).name, "source_commit": UPSTREAM["commit"], "pre_sha256": EXPECTED_FIXTURES[key]["sha256"], "post_sha256": EXPECTED_FIXTURES[key]["sha256"]}
        if item != expected_fixture:
            raise ValueError(f"{key} fixture identity drift")
    toolchain = value["toolchain"]
    if set(toolchain) != {"pre", "post", "vcvars64_pre", "vcvars64_post", "native_pre", "native_post"} or toolchain["pre"] != toolchain["post"] or toolchain["vcvars64_pre"] != toolchain["vcvars64_post"] or toolchain["native_pre"] != toolchain["native_post"]:
        raise ValueError("toolchain role drift")
    if set(toolchain["pre"]) != {"cargo", "rustc", "linker", "cmd"}:
        raise ValueError("toolchain roles drift")
    for role, item in toolchain["pre"].items():
        exact(item, {"role", "basename", "file_sha256", "version_args", "version_output_sha256", "version_exit", "timeout_s", "path_redacted"}, f"{role} identity")
        if item["role"] != role or not isinstance(item["basename"], str) or Path(item["basename"]).name != item["basename"] or item["version_exit"] != 0 or item["timeout_s"] != 15 or item["path_redacted"] is not True:
            raise ValueError("tool identity invalid")
        if role == "cmd" and item["basename"].lower() != "cmd.exe":
            raise ValueError("cmd identity must be cmd.exe")
        if role == "linker" and item["basename"].lower() != "rust-lld.exe":
            raise ValueError("linker identity must be rust-lld.exe")
        hex64(item["file_sha256"], "tool file sha")
        hex64(item["version_output_sha256"], "tool version sha")
        expected_args = ["-flavor", "link", "--version"] if role == "linker" and item["basename"].lower() == "rust-lld.exe" else ["/d", "/c", "ver"] if role == "cmd" else ["--version"]
        if item["version_args"] != expected_args:
            raise ValueError("tool version probe args drift")
    vcvars = toolchain["vcvars64_pre"]
    exact(vcvars, {"role", "basename", "bytes", "file_sha256", "path_redacted"}, "vcvars64 identity")
    if vcvars["role"] != "vcvars64" or vcvars["basename"].lower() != "vcvars64.bat" or not isinstance(vcvars["bytes"], int) or isinstance(vcvars["bytes"], bool) or vcvars["bytes"] <= 0 or vcvars["path_redacted"] is not True:
        raise ValueError("vcvars64 identity invalid")
    hex64(vcvars["file_sha256"], "vcvars64 file sha")
    for group_name in ("native_pre", "native_post"):
        group = toolchain[group_name]
        if not isinstance(group, dict) or set(group) != {"cl", "lib", "rc"}:
            raise ValueError("native tool role drift")
        for role, item in group.items():
            exact(item, {"role", "basename", "file_sha256", "version_args", "version_output_sha256", "version_exit", "timeout_s", "path_redacted"}, f"native {role} identity")
            expected_args = ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"]
            if item["role"] != role or item["basename"].lower() != f"{role}.exe" or item["version_args"] != expected_args or item["version_exit"] != 0 or item["timeout_s"] != 15 or item["path_redacted"] is not True:
                raise ValueError("native tool identity invalid")
            hex64(item["file_sha256"], "native tool file sha")
            hex64(item["version_output_sha256"], "native tool version sha")
        exact(value["build"], {"command", "exit", "stdout_sha256", "stderr_sha256", "timeout_s", "env_policy", "env_receipt", "deterministic_flags", "cargo_registry_inventory_before", "cargo_registry_inventory_after", "cargo_registry_inventory_equal"}, "build")
    if not isinstance(value["build"]["exit"], int) or isinstance(value["build"]["exit"], bool) or not 0 <= value["build"]["exit"] <= 255 or value["build"]["timeout_s"] != 900 or "offline" not in value["build"]["command"] or value["build"]["env_policy"] != "canonical_root_rustflags_brepro_vcvars64_allowlist_wrappers_cleared_offline_incremental_zero":
        raise ValueError("build policy drift")
    hex64(value["build"]["stdout_sha256"], "build stdout sha")
    hex64(value["build"]["stderr_sha256"], "build stderr sha")
    receipt = value["build"]["env_receipt"]
    if set(receipt) != set(ENV_KEYS):
        raise ValueError("native environment receipt drift")
    for key, item in receipt.items():
        exact(item, {"role", "exists", "entry_basenames", "value_sha256", "path_redacted", "relation"}, "native environment receipt")
        expected_role = ENV_ROLES.get(key, "native_environment")
        if item["role"] != expected_role or item["exists"] is not True or not isinstance(item["entry_basenames"], list) or any(not isinstance(entry, str) or (entry not in {"link-arg=/Brepro", "/Brepro"} and Path(entry).name != entry) for entry in item["entry_basenames"]) or item["path_redacted"] is not True:
            raise ValueError("native environment receipt invalid")
        hex64(item["value_sha256"], "environment sha")
        expected_relation = "system_root" if key in {"SystemRoot", "WINDIR"} else "system32_under_system_root" if key == "ComSpec" else None
        if item["relation"] != expected_relation:
            raise ValueError("native environment relation drift")
    if [entry.casefold() for entry in receipt["SystemRoot"]["entry_basenames"]] != ["windows"] or [entry.casefold() for entry in receipt["WINDIR"]["entry_basenames"]] != ["windows"]:
        raise ValueError("system root receipt drift")
    if receipt["SystemRoot"]["value_sha256"] != receipt["WINDIR"]["value_sha256"]:
        raise ValueError("system root value drift")
    if receipt["ComSpec"]["entry_basenames"] != ["cmd.exe"] or receipt["ComSpec"]["relation"] != "system32_under_system_root":
        raise ValueError("cmd environment receipt drift")
    if receipt["CARGO_HOME"]["entry_basenames"] != ["sipi-cargo-home-v1"]:
        raise ValueError("cargo home receipt drift")
    if receipt["RUSTC"]["entry_basenames"] != ["rustc.exe"] or receipt["CARGO_BUILD_RUSTC"]["entry_basenames"] != ["rustc.exe"] or receipt["RUSTC"]["value_sha256"] != receipt["CARGO_BUILD_RUSTC"]["value_sha256"]:
        raise ValueError("rustc environment crosswalk drift")
    if receipt["CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"]["entry_basenames"] != ["rust-lld.exe"]:
        raise ValueError("linker environment crosswalk drift")
    for key in ("TEMP", "TMP"):
        if receipt[key]["entry_basenames"] != ["<fresh-run-temp>"] or receipt[key]["value_sha256"] != hashlib.sha256(b"<fresh-run-temp>").hexdigest():
            raise ValueError("fresh temp receipt drift")
    for key in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "_CL_", "LINK"):
        if receipt[key]["entry_basenames"] or receipt[key]["value_sha256"] != hashlib.sha256(b"").hexdigest():
            raise ValueError("cleared override receipt drift")
    if receipt["RUSTFLAGS"]["entry_basenames"] or receipt["RUSTFLAGS"]["value_sha256"] != hashlib.sha256(b"").hexdigest():
        raise ValueError("plain rustflags receipt drift")
    if receipt["CL"]["entry_basenames"] != ["/Brepro"]:
        raise ValueError("native C flags receipt drift")
    if receipt["_CL_"]["entry_basenames"] or receipt["_CL_"]["value_sha256"] != hashlib.sha256(b"").hexdigest():
        raise ValueError("native _CL_ override drift")
    if receipt["CARGO_ENCODED_RUSTFLAGS"]["entry_basenames"] != ["<canonical-cargo-home-remap>", "<canonical-target-remap>", "<canonical-source-remap>", "<canonical-temp-remap>", "-C", "link-arg=/Brepro"] or receipt["CARGO_ENCODED_RUSTFLAGS"]["value_sha256"] == hashlib.sha256(b"").hexdigest():
        raise ValueError("deterministic rustflags receipt drift")
    verify_registry_inventory(value["build"]["cargo_registry_inventory_before"])
    verify_registry_inventory(value["build"]["cargo_registry_inventory_after"])
    if value["build"]["cargo_registry_inventory_before"] != value["build"]["cargo_registry_inventory_after"] or value["build"]["cargo_registry_inventory_equal"] is not True:
        raise ValueError("fixed cargo home registry inventory drift")
    deterministic_flags = value["build"]["deterministic_flags"]
    if not isinstance(deterministic_flags, list) or [item.get("role") for item in deterministic_flags] != ["cargo_home_remap", "target_remap", "source_remap", "temp_remap", "linker_repro"]:
        raise ValueError("deterministic flag roles drift")
    for item in deterministic_flags:
        exact(item, {"role", "value", "sha256"}, "deterministic flag")
        hex64(item["sha256"], "deterministic flag sha")
        if not isinstance(item["value"], str) or item["value"] not in {"<canonical-cargo-home>=C:/sipi-cargo", "<canonical-source>=C:/sipi-source", "<canonical-target>=C:/sipi-target", "<canonical-temp>=C:/sipi-temp", "-C link-arg=/Brepro"}:
            raise ValueError("deterministic flag path leak")
    if [item["value"] for item in deterministic_flags] != ["<canonical-cargo-home>=C:/sipi-cargo", "<canonical-target>=C:/sipi-target", "<canonical-source>=C:/sipi-source", "<canonical-temp>=C:/sipi-temp", "-C link-arg=/Brepro"]:
        raise ValueError("deterministic flag values drift")
    if cargo_home is not None:
        cargo_home = cargo_home.resolve(strict=False)
        if cargo_home != FIXED_CARGO_HOME.resolve(strict=False) or cargo_home.is_symlink() or not cargo_home.is_dir():
            raise ValueError("cargo home is not the fixed external C:/sipi-cargo-home-v1 directory")
        recompute_registry_inventory(cargo_home, value["build"]["cargo_registry_inventory_before"])
        verify_fixed_candidate_binding(value)
        root = Path(tempfile.gettempdir()).resolve() / "com-workbook-accm-canonical-v4"
        target = root / "candidate" / "crates" / "sipi-agent-com-direct" / "target"
        native_temp = root / "native-tmp"
        raw_flags = [f"--remap-path-prefix={cargo_home}=C:/sipi-cargo", f"--remap-path-prefix={target}=C:/sipi-target", f"--remap-path-prefix={root / 'candidate'}=C:/sipi-source", f"--remap-path-prefix={native_temp}=C:/sipi-temp", "-C", "link-arg=/Brepro"]
        expected_flags = [hashlib.sha256(item.encode()).hexdigest() for item in raw_flags[0:4]] + [hashlib.sha256(b"-C link-arg=/Brepro").hexdigest()]
        expected_cl = "/Brepro"
        if [item["sha256"] for item in deterministic_flags] != expected_flags or value["build"]["env_receipt"]["CARGO_HOME"]["value_sha256"] != hashlib.sha256(str(cargo_home).encode()).hexdigest() or value["build"]["env_receipt"]["CARGO_ENCODED_RUSTFLAGS"]["value_sha256"] != hashlib.sha256("\x1f".join(raw_flags).encode()).hexdigest() or value["build"]["env_receipt"]["CL"]["value_sha256"] != hashlib.sha256(expected_cl.encode()).hexdigest():
            raise ValueError("deterministic flag provenance mismatch")
    if receipt["CARGO_INCREMENTAL"]["entry_basenames"] != ["0"] or receipt["CARGO_NET_OFFLINE"]["entry_basenames"] != ["true"] or receipt["CARGO_INCREMENTAL"]["value_sha256"] != hashlib.sha256(b"0").hexdigest() or receipt["CARGO_NET_OFFLINE"]["value_sha256"] != hashlib.sha256(b"true").hexdigest():
        raise ValueError("cargo policy receipt drift")
    execution = value["execution"]
    exact(execution, {"runtime_timeout_s", "source_inventory_before", "source_inventory_after", "source_inventory_equal", "canonical_root", "canonical_root_fresh", "canonical_root_cleanup"}, "execution")
    if execution["runtime_timeout_s"] != 180 or execution["source_inventory_before"] != execution["source_inventory_after"] or execution["source_inventory_equal"] is not True or execution["canonical_root"] != "com-workbook-accm-canonical-v4" or execution["canonical_root_fresh"] is not True or execution["canonical_root_cleanup"] is not True:
        raise ValueError("execution custody drift")
    controls = value["controls"]
    exact(controls, {"ac_cm_rms_vectors", "source", "no_sparam_fit", "channel_policy"}, "controls")
    if controls["ac_cm_rms_vectors"] != [[0.0, 0.0], [0.0, 0.001]] or controls["source"] != "pinned workbook vector override" or controls["no_sparam_fit"] is not True or controls["channel_policy"] != "single_fd_to_td_impulse":
        raise ValueError("control policy drift")
    if len(value["runs"]) != 2 or len({tuple(run.get("control_vector", [])) for run in value["runs"]}) != 2:
        raise ValueError("run count drift")
    matched_artifacts: list[dict[str, Any]] = []
    for run in value["runs"]:
        exact(run, {"control_vector", "status", "exit", "stdout_sha256", "stderr_sha256", "final_metrics", "consumer_proof", "artifact", "blocker"}, "run")
        if run["control_vector"] not in controls["ac_cm_rms_vectors"] or not isinstance(run["exit"], int) or isinstance(run["exit"], bool) or run["status"] not in {"blocked", "artifact_invalid", "matched"}:
            raise ValueError("run policy drift")
        hex64(run["stdout_sha256"], "run stdout sha")
        hex64(run["stderr_sha256"], "run stderr sha")
        if run["status"] in {"blocked", "artifact_invalid"}:
            if run["status"] == "blocked" and run["exit"] == 0:
                raise ValueError("blocked run cannot have successful exit")
            if run["status"] == "artifact_invalid" and run["exit"] != 0:
                raise ValueError("artifact-invalid run must have successful process exit")
            if run["exit"] == 0 or run["consumer_proof"] is not False or run["final_metrics"] is not None or run["artifact"] is not None or not isinstance(run["blocker"], str):
                if run["status"] == "blocked":
                    raise ValueError("blocked run promotion")
            if run["status"] == "artifact_invalid" and (run["consumer_proof"] is not False or run["final_metrics"] is not None or run["artifact"] is not None or not isinstance(run["blocker"], str)):
                raise ValueError("invalid artifact promotion")
        else:
            if run["exit"] != 0 or run["consumer_proof"] is not True or run["blocker"] is not None or not isinstance(run["final_metrics"], dict) or not run["final_metrics"]:
                raise ValueError("matched run lacks consumer proof")
            if set(run["final_metrics"]) != {str(index) for index in range(len(controls["ac_cm_rms_vectors"]))}:
                raise ValueError("matched metrics are not aligned to all controls")
            for metrics in run["final_metrics"].values():
                if not isinstance(metrics, dict) or set(metrics) != {"FOM_dB", "COM_dB", "sigma_N_V"} or any(not isinstance(metric, (int, float)) or isinstance(metric, bool) or not math.isfinite(metric) for metric in metrics.values()):
                    raise ValueError("non-numeric final metric")
            artifact = run["artifact"]
            if not isinstance(artifact, dict) or set(artifact) != {"path", "bytes", "sha256", "raw_bytes", "raw_sha256", "case_metrics"} or not isinstance(artifact["path"], str) or Path(artifact["path"]).name != artifact["path"] or not isinstance(artifact["bytes"], int) or isinstance(artifact["bytes"], bool) or artifact["bytes"] <= 0 or not isinstance(artifact["raw_bytes"], int) or isinstance(artifact["raw_bytes"], bool) or artifact["raw_bytes"] <= 0 or artifact["raw_bytes"] > 64 * 1024 * 1024:
                raise ValueError("result artifact custody drift")
            hex64(artifact["sha256"], "result artifact sha")
            hex64(artifact["raw_sha256"], "raw result sha")
            artifact_path = path.parent / artifact["path"]
            if not artifact_path.is_file() or artifact_path.stat().st_size != artifact["bytes"] or sha(artifact_path) != artifact["sha256"]:
                raise ValueError("result artifact physical hash drift")
            artifact_value = json.loads(artifact_path.read_text(encoding="utf-8"))
            if not isinstance(artifact_value, dict) or set(artifact_value) != {"schema", "control_vector", "cases", "metric_fields", "channel_policy"} or artifact_value["schema"] != "sipi.com.workbook-accm-canonical-metrics.v1" or artifact_value["metric_fields"] != ["FOM_dB", "COM_dB", "sigma_N_V"] or artifact_value["channel_policy"] != "single_fd_to_td_impulse" or artifact_value["control_vector"] != run["control_vector"] or not isinstance(artifact_value["cases"], list) or not artifact_value["cases"]:
                raise ValueError("result artifact schema drift")
            path_free(artifact_value)
            parsed = {}
            for case in artifact_value["cases"]:
                if not isinstance(case, dict) or not set(case).issubset({"case_index", "ac_cm_rms", "metrics", "case_id", "package_case_index", "channel_identity"}) or not {"case_index", "ac_cm_rms", "metrics"}.issubset(case) or not isinstance(case.get("case_index"), int) or isinstance(case.get("case_index"), bool) or not isinstance(case.get("ac_cm_rms"), (int, float)) or isinstance(case.get("ac_cm_rms"), bool) or not math.isfinite(case["ac_cm_rms"]) or not isinstance(case.get("metrics"), dict):
                    raise ValueError("result artifact case drift")
                for field in ("case_id", "channel_identity"):
                    if field in case and not isinstance(case[field], str):
                        raise ValueError("result artifact identity type drift")
                if "package_case_index" in case and (not isinstance(case["package_case_index"], int) or isinstance(case["package_case_index"], bool) or case["package_case_index"] < 0):
                    raise ValueError("result artifact package index drift")
                key = str(case["case_index"])
                if key in parsed:
                    raise ValueError("duplicate result artifact case")
                parsed[key] = {}
                if case["ac_cm_rms"] != run["control_vector"][case["case_index"]] or set(case["metrics"]) != {"FOM_dB", "COM_dB", "sigma_N_V"}:
                    raise ValueError("result artifact metric schema drift")
                for metric in ("FOM_dB", "COM_dB", "sigma_N_V"):
                    number = case["metrics"].get(metric)
                    if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
                        raise ValueError("result artifact metric drift")
                    parsed[key][metric] = float(number)
            if artifact["case_metrics"] != parsed or run["final_metrics"] != parsed:
                raise ValueError("artifact metrics are not mechanically bound")
            if set(parsed) != {str(index) for index in range(len(controls["ac_cm_rms_vectors"]))}:
                raise ValueError("result artifact case/control drift")
            matched_artifacts.append(artifact)
    if len(matched_artifacts) > 1 and (len({item["path"] for item in matched_artifacts}) != len(matched_artifacts) or len({item["sha256"] for item in matched_artifacts}) != len(matched_artifacts)):
        raise ValueError("controls reused one result artifact")
    statuses = {run["status"] for run in value["runs"]}
    if "matched" in statuses:
        if value["build"]["exit"] != 0 or value["candidate"]["binary"]["exists"] is not True or value["candidate"]["binary_custody"]["pre"] is None:
            raise ValueError("matched run lacks successful build and binary custody")
    expected_status = "numeric_observation" if statuses == {"matched"} else "blocked"
    if value["parity"] != {"status": expected_status, "matched": False, "acceptance": False}:
        raise ValueError("parity promotion")
    expected_non_claims = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "PDB is opaque environment-local debug custody and nonpublish"]
    if expected_status == "blocked":
        expected_non_claims.append("no final consumer proof while blocked")
    if not isinstance(value["non_claims"], list) or value["non_claims"] != expected_non_claims:
        raise ValueError("non-claim drift")
    path_free(value)
    return value


def verify_aggregate(report1: Path, report2: Path, aggregate: Path, cargo_home: Path | None = None) -> dict[str, Any]:
    first = verify_report(report1, cargo_home)
    second = verify_report(report2, cargo_home)
    value = json.loads(aggregate.read_text(encoding="utf-8"))
    exact(value, {"schema", "report_slots", "candidate", "fixtures", "upstream", "toolchain", "controls", "parity", "fresh_runs", "non_claims"}, "aggregate")
    if value["schema"] != AGGREGATE_SCHEMA or first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"]:
        raise ValueError("aggregate identity invalid")
    slots = value["report_slots"]
    if len(slots) != 2:
        raise ValueError("aggregate slot count drift")
    for slot, expected, report in zip(slots, ("run1", "run2"), (report1, report2)):
        exact(slot, {"slot", "run_id", "path", "sha256"}, "aggregate slot")
        if slot["slot"] != expected or slot["run_id"] != (first if expected == "run1" else second)["run_id"] or slot["path"] != report.name or slot["path"] != Path(slot["path"]).name:
            raise ValueError("aggregate path/order drift")
        if slot["sha256"] != sha(report):
            raise ValueError("aggregate report hash drift")
        hex64(slot["sha256"], "aggregate report sha")
    build_identity = lambda report: {key: report["build"][key] for key in ("command", "exit", "timeout_s", "env_policy", "env_receipt", "deterministic_flags", "cargo_registry_inventory_before", "cargo_registry_inventory_after", "cargo_registry_inventory_equal")}
    first_binary = first["candidate"]["binary"]
    second_binary = second["candidate"]["binary"]
    if first_binary["canonical_sha256"] != second_binary["canonical_sha256"] or first_binary["normalization_map"] != second_binary["normalization_map"] or first_binary["certificate_bytes"] != 0 or second_binary["certificate_bytes"] != 0 or first_binary["overlay_bytes"] != 0 or second_binary["overlay_bytes"] != 0 or [(item["name"], item["virtual_address"], item["virtual_bytes"], item["raw_pointer"], item["bytes"]) for item in first_binary["sections"]] != [(item["name"], item["virtual_address"], item["virtual_bytes"], item["raw_pointer"], item["bytes"]) for item in second_binary["sections"]]:
        raise ValueError("typed PE canonical identity drift")
    if stable_candidate(first["candidate"]) != stable_candidate(second["candidate"]) or value["candidate"] != first["candidate"] or first["fixtures"] != second["fixtures"] or first["upstream"] != second["upstream"] or first["toolchain"] != second["toolchain"] or build_identity(first) != build_identity(second) or first["execution"] != second["execution"] or value["fixtures"] != first["fixtures"] or value["upstream"] != first["upstream"] or value["toolchain"] != first["toolchain"] or value["controls"] != first["controls"]:
        raise ValueError("aggregate identity mismatch")
    expected_aggregate_status = "numeric_observation" if first["parity"]["status"] == second["parity"]["status"] == "numeric_observation" else "blocked"
    if value["parity"] != {"status": expected_aggregate_status, "matched": False, "acceptance": False} or value["fresh_runs"] != 2 or value["non_claims"] != ["no upstream numeric parity", "no global/product/release claim", "aggregate is preparation-only", "PDB is opaque environment-local debug custody and nonpublish"]:
        raise ValueError("aggregate promotion")
    path_free(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report1", type=Path, required=True)
    parser.add_argument("--report2", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    args = parser.parse_args()
    verify_aggregate(args.report1, args.report2, args.aggregate, args.cargo_home)
    print("verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
