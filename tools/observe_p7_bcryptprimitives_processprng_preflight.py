"""Observe the P7 BCryptPrimitives/ProcessPrng preflight without changing policy."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p7-bcryptprimitives-processprng-preflight-observation.v1"
EXPECTED_EXECUTABLE_SHA256 = "a3059d052df54c0f3ebbd727bd2f71760ff33f73af82e1e2f29c0ec35b8c882d"
EXPECTED_EXECUTABLE_BYTES = 3_908_608
PROCESS_PRNG_URL = "https://learn.microsoft.com/en-us/windows/win32/seccng/processprng"
RUST_TARGET_URL = "https://doc.rust-lang.org/beta/rustc/platform-support/windows-msvc.html"
API_SET_URL = "https://learn.microsoft.com/en-us/windows/win32/apiindex/api-set-loader-operation"
RUST_RELEASE = "1.97.0"
RUST_HOST = "x86_64-pc-windows-msvc"


class ObservationError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def external_regular(path: Path, reason: str) -> Path:
    resolved = path.resolve()
    if (
        ROOT == resolved or ROOT in resolved.parents or not path.is_file() or path.is_symlink()
        or is_reparse(path) or has_link_or_reparse_ancestor(path.parent)
    ):
        raise ObservationError(reason)
    return resolved


def identity(path: Path) -> tuple[int, str, bytes]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ObservationError("external_input_unavailable") from error
    return len(data), sha256(data), data


def load_pe_parser() -> type:
    spec = importlib.util.spec_from_file_location("p4b_static_pe", ROOT / "tools" / "observe_p4b_dual_ami_pe_loader_declarations.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PeImage


def parse_process_prng(data: bytes) -> dict[str, Any]:
    try:
        image = load_pe_parser()(data)
    except Exception as error:
        raise ObservationError("candidate_pe_parse_failed") from error
    if image.machine != 0x8664:
        raise ObservationError("candidate_machine_not_windows_x86_64")
    if any(image.directory(13)):
        raise ObservationError("candidate_delay_import_directory_present")
    bcrypt = [entry for entry in image.import_table(False) if entry["module"] == "bcryptprimitives.dll"]
    if len(bcrypt) != 1:
        raise ObservationError("bcryptprimitives_import_not_unique")
    symbols = bcrypt[0]["symbols"]
    if symbols != ["ProcessPrng"]:
        raise ObservationError("bcryptprimitives_symbol_not_exact_processprng")
    if any(symbol.startswith("ordinal:") for symbol in symbols):
        raise ObservationError("bcryptprimitives_import_ordinal_not_allowed")
    return {
        "machine": "windows-x86_64",
        "delay_import_directory_present": False,
        "bcryptprimitives_import": {"import_kind": "name", "symbols": symbols},
        "normal_import_dlls": sorted(entry["module"] for entry in image.import_table(False)),
    }


def canonical_doc(url: str, required: tuple[bytes, ...]) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
    except OSError as error:
        raise ObservationError("authoritative_document_unavailable") from error
    if any(value not in data for value in required):
        raise ObservationError("authoritative_document_requirements_missing")
    return {"url": url, "byte_length": len(data), "sha256": sha256(data)}


def observe_authority() -> dict[str, Any]:
    return {
        "process_prng": canonical_doc(PROCESS_PRNG_URL, (b"BCryptPrimitives.dll", b"CngRngExt", b"Windows 8")),
        "rust_windows_msvc": canonical_doc(RUST_TARGET_URL, (b"Windows 10 or higher", b"Windows Server 2016")),
        "api_set_loader": canonical_doc(API_SET_URL, (b"mapping between API sets and binaries may differ", b"does not directly refer to a file on disk")),
        "frozen_facts": {
            "process_prng_dll": "bcryptprimitives.dll",
            "process_prng_api_set": "CngRngExt",
            "process_prng_minimum_client": "windows_8_desktop",
            "process_prng_minimum_server": "windows_server_2008_r2_desktop",
            "rust_target_client_floor": "windows_10",
            "rust_target_server_floor": "windows_server_2016",
            "api_set_mapping_device_dependent": True,
        },
    }


def toolchain_observation(rustc: Path) -> dict[str, Any]:
    rustc = external_regular(rustc, "rustc_unavailable")
    try:
        version = subprocess.run([str(rustc), "-Vv"], check=True, capture_output=True, text=True).stdout
        sysroot = Path(subprocess.run([str(rustc), "--print", "sysroot"], check=True, capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError) as error:
        raise ObservationError("rustc_observation_failed") from error
    required = {f"release: {RUST_RELEASE}", f"host: {RUST_HOST}"}
    if not required.issubset(set(version.splitlines())):
        raise ObservationError("rustc_version_or_host_mismatch")
    libdir = sysroot / "lib" / "rustlib" / RUST_HOST / "lib"
    candidates = sorted(libdir.glob("libstd-*.rlib"))
    if len(candidates) != 1 or candidates[0].is_symlink() or is_reparse(candidates[0]):
        raise ObservationError("rust_std_identity_unavailable")
    length, digest, data = identity(candidates[0])
    if b"bcryptprimitives" not in data or b"ProcessPrng" not in data:
        raise ObservationError("rust_std_processprng_tokens_missing")
    lock = subprocess.run(["git", "-C", str(ROOT), "show", "b775dde6d242e687eb71a30b9a83a87d8b31ba55:Cargo.lock"], check=True, capture_output=True).stdout
    if b'name = "getrandom"' in lock:
        raise ObservationError("unexpected_third_party_getrandom_declared")
    return {
        "release": RUST_RELEASE,
        "host": RUST_HOST,
        "version_sha256": sha256(version.encode("utf-8")),
        "std_rlib": {"byte_length": length, "sha256": digest, "processprng_tokens_present": True},
        "workspace_or_locked_third_party_processprng_package_declared": False,
        "ownership_assessment": "toolchain_standard_library_linkage_supported_not_product_callsite_provenance",
    }


def system_dll_observation(system_dll: Path) -> dict[str, Any]:
    system_root = Path(os.environ.get("SystemRoot", "")).resolve()
    expected = system_root / "System32" / "bcryptprimitives.dll"
    system_dll = external_regular(system_dll, "system_dll_unavailable")
    if system_dll != expected.resolve():
        raise ObservationError("system_dll_not_expected_system32_file")
    quoted_path = str(system_dll).replace("'", "''")
    script = (
        f"$path='{quoted_path}';"
        "Import-Module Microsoft.PowerShell.Security -ErrorAction Stop;"
        "$signature=Get-AuthenticodeSignature -LiteralPath $path;"
        "[pscustomobject]@{status=$signature.Status.ToString();subject=$signature.SignerCertificate.Subject;"
        "version=(Get-Item -LiteralPath $path).VersionInfo.FileVersion}|ConvertTo-Json -Compress"
    )
    try:
        environment = os.environ.copy()
        environment["PSModulePath"] = str(Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        signature = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ObservationError("system_dll_signature_observation_failed") from error
    if signature.get("status") != "Valid" or signature.get("subject") != "CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US":
        raise ObservationError("system_dll_signature_not_microsoft_windows_valid")
    length, digest, _ = identity(system_dll)
    return {"regular_system32_file": True, "byte_length": length, "sha256": digest, "signature_status": "valid_microsoft_windows", "file_version": signature.get("version")}


def smoke(executable: Path) -> dict[str, Any]:
    environment = {"SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"], "PATH": str(Path(os.environ["SystemRoot"]) / "System32")}
    with tempfile.TemporaryDirectory(prefix="sipi-p7-processprng-smoke-") as directory:
        try:
            result = subprocess.run([str(executable), "version", "--json"], cwd=directory, env=environment, check=False, capture_output=True)
        except OSError as error:
            raise ObservationError("system32_only_smoke_failed") from error
    if result.returncode != 0:
        raise ObservationError("system32_only_smoke_failed")
    return {"args": ["version", "--json"], "exit_code": 0, "stdout_sha256": sha256(result.stdout), "stderr_sha256": sha256(result.stderr), "stdout_bytes": len(result.stdout), "stderr_bytes": len(result.stderr)}


def observe_one(source: Path) -> dict[str, Any]:
    before_length, before_digest, _ = identity(source)
    if (before_length, before_digest) != (EXPECTED_EXECUTABLE_BYTES, EXPECTED_EXECUTABLE_SHA256):
        raise ObservationError("candidate_executable_identity_drift")
    temporary = Path(tempfile.mkdtemp(prefix="sipi-p7-processprng-custody-"))
    try:
        copied = temporary / "sipi.exe"
        shutil.copyfile(source, copied)
        after_length, after_digest, _ = identity(source)
        copied_length, copied_digest, copied_data = identity(copied)
        if (after_length, after_digest) != (before_length, before_digest):
            raise ObservationError("candidate_executable_changed_during_materialization")
        if (copied_length, copied_digest) != (before_length, before_digest):
            raise ObservationError("candidate_executable_copy_mismatch")
        result = parse_process_prng(copied_data)
        result["system32_only_smoke"] = smoke(copied)
        return result
    finally:
        try:
            shutil.rmtree(temporary)
        except OSError as error:
            raise ObservationError("custody_cleanup_failed") from error


def observe(first: Path, second: Path, rustc: Path, system_dll: Path) -> dict[str, Any]:
    first = external_regular(first, "first_executable_unavailable")
    second = external_regular(second, "second_executable_unavailable")
    if first == second:
        raise ObservationError("fresh_executable_sources_not_distinct")
    first_result, second_result = observe_one(first), observe_one(second)
    if json.dumps(first_result, sort_keys=True, separators=(",", ":")) != json.dumps(second_result, sort_keys=True, separators=(",", ":")):
        raise ObservationError("fresh_observation_result_mismatch")
    authority = observe_authority()
    toolchain = toolchain_observation(rustc)
    system_dll_record = system_dll_observation(system_dll)
    return {
        "schema": SCHEMA,
        "status": "external_processprng_loader_api_ownership_preflight_observed_policy_revision_pending",
        "fresh_materializations": 2,
        "executable": {"byte_length": EXPECTED_EXECUTABLE_BYTES, "sha256": EXPECTED_EXECUTABLE_SHA256},
        "candidate_import_and_smoke": first_result,
        "authority": authority,
        "toolchain": toolchain,
        "same_host_system_dll": system_dll_record,
        "distribution": "provided_by_operating_system_not_packaged_or_redistributed",
        "gates": {"layout_policy_v2_implemented": False, "allowlist_expanded": False, "composition_invoked": False, "archive_invoked": False, "install_invoked": False, "performance_observation_invoked": False, "candidate_evaluation_invoked": False, "dynamic_runtime_closure_evaluated": False, "release_candidate": False, "promotion_status": "blocked"},
        "non_claims": ["not_a_layout_policy_revision", "not_cross_version_or_cross_device_loader_closure", "not_fresh_machine_or_security_review", "not_release_readiness_or_promotion"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-executable", type=Path, required=True)
    parser.add_argument("--second-executable", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--system-dll", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        output = arguments.report
        report = output.resolve()
        if ROOT == report or ROOT in report.parents or report.exists() or output.is_symlink() or has_link_or_reparse_ancestor(output.parent):
            raise ObservationError("report_must_be_new_and_outside_product_root")
        result = observe(arguments.first_executable, arguments.second_executable, arguments.rustc, arguments.system_dll)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    except (ObservationError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
