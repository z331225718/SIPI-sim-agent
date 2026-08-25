"""Preparation-schema mutation tests (no formal replay artifacts)."""

from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from .verify_com_workbook_accm_replay_v1 import ENV_KEYS, ENV_ROLES, EXPECTED_FIXTURES, EXPECTED_SOURCE_INVENTORY, SOURCE_PATHS, UPSTREAM, stable_candidate, verify_aggregate, verify_fixed_candidate_binding, verify_registry_inventory, verify_report
except ImportError:
    from verify_com_workbook_accm_replay_v1 import ENV_KEYS, ENV_ROLES, EXPECTED_FIXTURES, EXPECTED_SOURCE_INVENTORY, SOURCE_PATHS, UPSTREAM, stable_candidate, verify_aggregate, verify_fixed_candidate_binding, verify_registry_inventory, verify_report

try:
    from .run_com_workbook_accm_replay_v1 import BUILD_ENV_KEYS, FIXTURES, binary_identity, build_env, canonical_env_lookup, canonical_lock_path, canonical_materialization_root, canonical_root_path, canonicalize_environment, capture_vcvars_env, copy_binary_custody, deterministic_flag_receipt, is_reparse_point, parse_result_artifact, pinned_blob, redact, resolve_regular, run_one, safe_extract, safe_relative, tool_identity
except ImportError:
    from run_com_workbook_accm_replay_v1 import BUILD_ENV_KEYS, FIXTURES, binary_identity, build_env, canonical_env_lookup, canonical_lock_path, canonical_materialization_root, canonical_root_path, canonicalize_environment, capture_vcvars_env, copy_binary_custody, deterministic_flag_receipt, is_reparse_point, parse_result_artifact, pinned_blob, redact, resolve_regular, run_one, safe_extract, safe_relative, tool_identity


def aggregator_module():
    try:
        from . import aggregate_com_workbook_accm_replay_v1 as builder
    except ImportError:
        import aggregate_com_workbook_accm_replay_v1 as builder
    return builder


def fake_receipt() -> dict[str, dict[str, object]]:
    empty = hashlib.sha256(b"").hexdigest()
    fresh = hashlib.sha256(b"<fresh-run-temp>").hexdigest()
    zero = hashlib.sha256(b"0").hexdigest()
    offline = hashlib.sha256(b"true").hexdigest()
    entries = {
        "SystemRoot": ["Windows"], "WINDIR": ["Windows"], "ComSpec": ["cmd.exe"],
        "CARGO_HOME": ["sipi-cargo-home-v1"], "RUSTC": ["rustc.exe"], "CARGO_BUILD_RUSTC": ["rustc.exe"],
        "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": ["rust-lld.exe"],
        "TEMP": ["<fresh-run-temp>"], "TMP": ["<fresh-run-temp>"],
        "CARGO_INCREMENTAL": ["0"], "CARGO_NET_OFFLINE": ["true"],
        "RUSTFLAGS": [], "CARGO_ENCODED_RUSTFLAGS": ["<canonical-cargo-home-remap>", "<canonical-target-remap>", "<canonical-source-remap>", "<canonical-temp-remap>", "-C", "link-arg=/Brepro"], "CL": ["/Brepro"], "_CL_": [],
    }
    result = {}
    for key in ENV_KEYS:
        value_hash = "5" * 64
        if key in {"TEMP", "TMP"}: value_hash = fresh
        elif key == "RUSTFLAGS": value_hash = empty
        elif key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "_CL_", "LINK"}: value_hash = empty
        elif key == "CL": value_hash = hashlib.sha256(b"/Brepro").hexdigest()
        elif key == "CARGO_INCREMENTAL": value_hash = zero
        elif key == "CARGO_NET_OFFLINE": value_hash = offline
        elif key == "CARGO_ENCODED_RUSTFLAGS": value_hash = "6" * 64
        result[key] = {"role": ENV_ROLES.get(key, "native_environment"), "exists": True, "entry_basenames": entries.get(key, []), "value_sha256": value_hash, "path_redacted": True, "relation": "system_root" if key in {"SystemRoot", "WINDIR"} else "system32_under_system_root" if key == "ComSpec" else None}
    result["CARGO_BUILD_RUSTC"]["value_sha256"] = result["RUSTC"]["value_sha256"]
    return result


def valid_report(run_id: str, nonce: str) -> dict[str, object]:
    inventory = copy.deepcopy(EXPECTED_SOURCE_INVENTORY)
    fixtures = {key: {**value, "basename": Path(value["path"]).name, "source_commit": UPSTREAM["commit"]} for key, value in EXPECTED_FIXTURES.items()}
    tool = lambda role: {"role": role, "basename": "rust-lld.exe" if role == "linker" else f"{role}.exe", "version_args": ["-flavor", "link", "--version"] if role == "linker" else ["/d", "/c", "ver"] if role == "cmd" else ["--version"], "file_sha256": "c" * 64, "version_output_sha256": "d" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
    native = lambda role: {"role": role, "basename": f"{role}.exe", "version_args": ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"], "file_sha256": "e" * 64, "version_output_sha256": "f" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
    fixtures = {key: {**item, "basename": Path(item["path"]).name, "source_commit": UPSTREAM["commit"], "pre_sha256": item["sha256"], "post_sha256": item["sha256"]} for key, item in EXPECTED_FIXTURES.items()}
    receipt = fake_receipt()
    runs = [{"control_vector": [0.0, 0.0], "status": "blocked", "exit": 3, "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64, "final_metrics": None, "consumer_proof": False, "artifact": None, "blocker": "blocked"}, {"control_vector": [0.0, 0.001], "status": "blocked", "exit": 3, "stdout_sha256": "3" * 64, "stderr_sha256": "4" * 64, "final_metrics": None, "consumer_proof": False, "artifact": None, "blocker": "blocked"}]
    binary = {"basename": "sipi-com-direct-run.exe", "exists": False, "bytes": 0, "sha256": None, "canonical_sha256": None, "pe_offset": None, "optional_header_offset": None, "debug_directory_raw_pointer": None, "machine": None, "optional_magic": None, "characteristics": None, "debug_entries": 0, "codeview_rva": None, "codeview_raw_pointer": None, "codeview_bytes": None, "repro_entries": 0, "pdb_basename": None, "repro": False, "sections": [], "normalization_map": [], "certificate_bytes": 0, "overlay_bytes": 0}
    flags = [{"role": role, "value": value, "sha256": "5" * 64} for role, value in (("cargo_home_remap", "<canonical-cargo-home>=C:/sipi-cargo"), ("target_remap", "<canonical-target>=C:/sipi-target"), ("source_remap", "<canonical-source>=C:/sipi-source"), ("temp_remap", "<canonical-temp>=C:/sipi-temp"), ("linker_repro", "-C link-arg=/Brepro"))]
    registry_entries = {"registry/src/fake/file": {"bytes": 1, "sha256": "a" * 64}}
    registry = {"entries": registry_entries, "count": 1, "total_bytes": 1, "sha256": hashlib.sha256(json.dumps(registry_entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    build = {"command": "cargo build --manifest-path crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-run --release --locked --offline", "exit": 101, "stdout_sha256": "e" * 64, "stderr_sha256": "f" * 64, "timeout_s": 900, "env_policy": "canonical_root_rustflags_brepro_vcvars64_allowlist_wrappers_cleared_offline_incremental_zero", "env_receipt": receipt, "deterministic_flags": flags, "cargo_registry_inventory_before": registry, "cargo_registry_inventory_after": copy.deepcopy(registry), "cargo_registry_inventory_equal": True}
    return {"schema": "sipi.com.workbook-accm-replay-prep.v4", "run_id": run_id, "nonce": nonce, "candidate": {"commit": "2e18a6a27cf8abc0555e24e0346a54c4ea577baf", "tree": "bfdc3e0ddd9bc76737528011e6dddc94c728f059", "archive": {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": 0, "bytes": 44615680, "sha256": "67b071cf9302d932ed2b974db3c7d82cb1e70c4b7f0dac276d788b88f1a64993"}, "binary_pre": binary, "binary": copy.deepcopy(binary), "binary_custody": {"id": run_id, "pre": None, "post": None}}, "upstream": {**UPSTREAM, "source_inventory": inventory}, "fixtures": fixtures, "toolchain": {"pre": {"cargo": tool("cargo"), "rustc": tool("rustc"), "linker": tool("linker"), "cmd": tool("cmd")}, "post": {"cargo": tool("cargo"), "rustc": tool("rustc"), "linker": tool("linker"), "cmd": tool("cmd")}, "vcvars64_pre": {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 123, "file_sha256": "a" * 64, "path_redacted": True}, "vcvars64_post": {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 123, "file_sha256": "a" * 64, "path_redacted": True}, "native_pre": {"cl": native("cl"), "lib": native("lib"), "rc": native("rc")}, "native_post": {"cl": native("cl"), "lib": native("lib"), "rc": native("rc")}}, "build": build, "execution": {"runtime_timeout_s": 180, "source_inventory_before": {}, "source_inventory_after": {}, "source_inventory_equal": True, "canonical_root": "com-workbook-accm-canonical-v4", "canonical_root_fresh": True, "canonical_root_cleanup": True}, "controls": {"ac_cm_rms_vectors": [[0.0, 0.0], [0.0, 0.001]], "source": "pinned workbook vector override", "no_sparam_fit": True, "channel_policy": "single_fd_to_td_impulse"}, "runs": runs, "parity": {"status": "blocked", "matched": False, "acceptance": False}, "non_claims": ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "PDB is opaque environment-local debug custody and nonpublish", "no final consumer proof while blocked"]}


class WorkbookAccmPreparationTests(unittest.TestCase):
    def write(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def pair(self, root: Path) -> tuple[Path, Path]:
        first = self.write(root, "run1.json", valid_report("1" * 64, "a" * 64))
        second = self.write(root, "run2.json", valid_report("2" * 64, "b" * 64))
        return first, second

    def test_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            verify_report(self.write(Path(directory), "report.json", valid_report("1" * 64, "a" * 64)))

    def test_rejects_empty_registry_inventory(self) -> None:
        with self.assertRaises(ValueError):
            verify_registry_inventory({"entries": {}, "count": 0, "total_bytes": 0, "sha256": "0" * 64})

    def test_reparse_points_fail_closed(self) -> None:
        with mock.patch.object(Path, "is_symlink", return_value=False), mock.patch.object(Path, "stat", side_effect=OSError("reparse probe failed")):
            self.assertTrue(is_reparse_point(Path("candidate")))

    def test_fixed_inventory_rejects_coordinated_package_deletion(self) -> None:
        value = valid_report("1" * 64, "a" * 64)
        inventory = value["build"]["cargo_registry_inventory_before"]
        removed = next(iter(inventory["entries"]))
        del inventory["entries"][removed]
        inventory["count"] -= 1
        inventory["total_bytes"] -= 1
        with self.assertRaises(ValueError):
            verify_fixed_candidate_binding(value)

    def test_accepts_success_only_with_physical_result_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = valid_report("1" * 64, "a" * 64)
            value["build"]["exit"] = 0
            binary = {"basename": "sipi-com-direct-run.exe", "exists": True, "bytes": 1024, "sha256": "a" * 64, "canonical_sha256": "b" * 64, "pe_offset": 100, "optional_header_offset": 124, "debug_directory_raw_pointer": 256, "machine": 0x8664, "optional_magic": 0x20B, "characteristics": 2, "debug_entries": 1, "codeview_rva": 256, "codeview_raw_pointer": 512, "codeview_bytes": 28, "repro_entries": 1, "pdb_basename": "sipi-com-direct-run.pdb", "repro": True, "sections": [{"name": ".text", "virtual_address": 256, "virtual_bytes": 512, "raw_pointer": 512, "bytes": 512, "sha256": "e" * 64}], "normalization_map": [{"role": "coff_timestamp", "offset": 108, "bytes": 4}, {"role": "debug_timestamp", "offset": 260, "bytes": 4}, {"role": "rsds_guid", "offset": 516, "bytes": 16}, {"role": "pe_checksum", "offset": 188, "bytes": 4}], "certificate_bytes": 0, "overlay_bytes": 0}
            custody = {"pre": {"exe": {"basename": "run.exe", "bytes": 1024, "sha256": "a" * 64, "source_bytes": 1024, "source_sha256": "a" * 64}, "pdb": {"basename": "sipi-com-direct-run.pdb", "bytes": 128, "sha256": "d" * 64, "source_bytes": 128, "source_sha256": "d" * 64}}, "post": {"exe": {"basename": "run.exe", "bytes": 1024, "sha256": "a" * 64, "source_bytes": 1024, "source_sha256": "a" * 64}, "pdb": {"basename": "sipi-com-direct-run.pdb", "bytes": 128, "sha256": "d" * 64, "source_bytes": 128, "source_sha256": "d" * 64}}}
            custody["id"] = value["run_id"]
            value["candidate"]["binary_pre"] = copy.deepcopy(binary); value["candidate"]["binary"] = copy.deepcopy(binary); value["candidate"]["binary_custody"] = custody
            for index, run in enumerate(value["runs"], start=1):
                payload = json.dumps({"schema": "sipi.com.workbook-accm-canonical-metrics.v1", "control_vector": [0.0, 0.0], "cases": [{"case_index": 0, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}}, {"case_index": 1, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 4.0 + index, "COM_dB": 5.0 + index, "sigma_N_V": 6.0 + index}}], "metric_fields": ["FOM_dB", "COM_dB", "sigma_N_V"], "channel_policy": "single_fd_to_td_impulse"}).encode()
                if index == 2:
                    payload = payload.replace(b'"control_vector": [0.0, 0.0]', b'"control_vector": [0.0, 0.001]').replace(b'"case_index": 1, "ac_cm_rms": 0.0', b'"case_index": 1, "ac_cm_rms": 0.001')
                artifact = root / f"run-result-{index}.json"; artifact.write_bytes(payload)
                import hashlib
                case_metrics = {"0": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}, "1": {"FOM_dB": 4.0 + index, "COM_dB": 5.0 + index, "sigma_N_V": 6.0 + index}}
                run.update({"status": "matched", "exit": 0, "final_metrics": case_metrics, "consumer_proof": True, "artifact": {"path": artifact.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "raw_bytes": len(payload), "raw_sha256": hashlib.sha256(payload).hexdigest(), "case_metrics": case_metrics}, "blocker": None})
            value["parity"] = {"status": "numeric_observation", "matched": False, "acceptance": False}
            value["non_claims"] = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "PDB is opaque environment-local debug custody and nonpublish"]
            verify_report(self.write(root, "success.json", value))
            forged = copy.deepcopy(value)
            for item in forged["candidate"]["binary"]["normalization_map"]:
                item["offset"] = 128
            forged["candidate"]["binary_pre"] = copy.deepcopy(forged["candidate"]["binary"])
            with self.assertRaises(ValueError):
                verify_report(self.write(root, "forged-normalization.json", forged))

    def test_rejects_schema(self): self.mutate_report(lambda x: x.__setitem__("schema", "forged"))
    def test_rejects_run_id(self): self.mutate_report(lambda x: x.__setitem__("run_id", "../" + "1" * 61))
    def test_rejects_nonce(self): self.mutate_report(lambda x: x.__setitem__("nonce", "z" * 64))
    def test_rejects_candidate(self): self.mutate_report(lambda x: x["candidate"].__setitem__("commit", "0" * 40))
    def test_rejects_archive_crlf_binding(self): self.mutate_report(lambda x: x["candidate"]["archive"].__setitem__("sha256", "0" * 64))
    def test_rejects_fixture_path(self): self.mutate_report(lambda x: x["fixtures"]["workbook"].__setitem__("path", "C:/wrong.xlsx"))
    def test_rejects_fixture_hash(self): self.mutate_report(lambda x: x["fixtures"]["s4p"].__setitem__("sha256", "0" * 64))
    def test_rejects_source_inventory(self): self.mutate_report(lambda x: x["upstream"]["source_inventory"].pop(next(iter(x["upstream"]["source_inventory"]))))
    def test_rejects_tool_role(self): self.mutate_report(lambda x: x["toolchain"]["pre"]["cargo"].__setitem__("role", "rustc"))
    def test_rejects_non_rust_lld_linker(self): self.mutate_report(lambda x: x["toolchain"]["pre"]["linker"].__setitem__("basename", "lld-link.exe"))
    def test_rejects_wrapper_policy(self): self.mutate_report(lambda x: x["build"].__setitem__("env_policy", "inherited"))
    def test_rejects_runtime_timeout(self): self.mutate_report(lambda x: x["execution"].__setitem__("runtime_timeout_s", 181))
    def test_rejects_scalar_accm(self): self.mutate_report(lambda x: x["controls"].__setitem__("ac_cm_rms_vectors", [0.0, 0.001]))
    def test_rejects_run_status(self): self.mutate_report(lambda x: x["runs"][1].__setitem__("status", "accepted"))
    def test_rejects_consumer_proof(self): self.mutate_report(lambda x: x["runs"][0].__setitem__("consumer_proof", True))
    def test_rejects_parity_promotion(self): self.mutate_report(lambda x: x["parity"].__setitem__("matched", True))
    def test_rejects_unknown_key(self): self.mutate_report(lambda x: x.__setitem__("promotion", True))

    def mutate_report(self, mutation) -> None:
        with tempfile.TemporaryDirectory() as directory:
            value = valid_report("1" * 64, "a" * 64)
            mutation(value)
            with self.assertRaises(ValueError):
                verify_report(self.write(Path(directory), "report.json", value))

    def test_aggregate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = self.pair(root)
            aggregate = root / "aggregate.json"
            builder = aggregator_module()
            builder.aggregate(first, second, aggregate)
            verify_aggregate(first, second, aggregate)

    def test_aggregate_rejects_report_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); aggregate = root / "aggregate.json"
            builder = aggregator_module()
            builder.aggregate(first, second, aggregate)
            value = json.loads(aggregate.read_text()); value["report_slots"][0]["sha256"] = "0" * 64; aggregate.write_text(json.dumps(value))
            with self.assertRaises(ValueError): verify_aggregate(first, second, aggregate)

    def test_aggregate_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); aggregate = root / "aggregate.json"
            builder = aggregator_module()
            builder.aggregate(first, second, aggregate)
            value = json.loads(aggregate.read_text()); value["report_slots"][0]["path"] = "../run1.json"; aggregate.write_text(json.dumps(value))
            with self.assertRaises(ValueError): verify_aggregate(first, second, aggregate)

    def test_aggregate_rejects_candidate_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); aggregate = root / "aggregate.json"
            builder = aggregator_module()
            builder.aggregate(first, second, aggregate)
            value = json.loads(aggregate.read_text()); value["candidate"]["tree"] = "0" * 40; aggregate.write_text(json.dumps(value))
            with self.assertRaises(ValueError): verify_aggregate(first, second, aggregate)

    def test_rejects_duplicate_controls(self) -> None:
        self.mutate_report(lambda x: x["runs"].__setitem__(1, copy.deepcopy(x["runs"][0])))

    def test_rejects_matched_exit_zero_with_blocked_parity(self) -> None:
        def mutate(value):
            value["runs"][0].update({"status": "matched", "exit": 0, "consumer_proof": True, "final_metrics": {"FOM": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}, "artifact": {"path": "result.json", "bytes": 1, "sha256": "a" * 64}, "blocker": None})
        self.mutate_report(mutate)

    def test_rejects_promotion_nonclaim_deletion(self) -> None:
        self.mutate_report(lambda x: x["non_claims"].pop())

    def test_rejects_bool_as_binary_bytes(self) -> None:
        self.mutate_report(lambda x: x["candidate"]["binary"].__setitem__("bytes", True))

    def test_rejects_missing_required_build_environment(self) -> None:
        self.mutate_report(lambda x: x["build"]["env_receipt"]["LIB"].__setitem__("exists", False))

    def test_rejects_cmd_identity_drift(self) -> None:
        self.mutate_report(lambda x: x["toolchain"]["pre"]["cmd"].__setitem__("basename", "evil.exe"))

    def test_rejects_incomplete_native_toolset(self) -> None:
        self.mutate_report(lambda x: x["toolchain"]["native_pre"].pop("rc"))

    def test_canonical_environment_accepts_uppercase_and_rejects_aliases(self) -> None:
        environment = {"SYSTEMROOT": r"C:\Windows", "windir": r"C:\Windows", "PATH": r"C:\bin"}
        normalized = canonicalize_environment(environment)
        self.assertEqual(normalized["SystemRoot"], r"C:\Windows")
        self.assertEqual(canonical_env_lookup(environment, "SystemRoot"), r"C:\Windows")
        with self.assertRaises(ValueError):
            canonicalize_environment({"SystemRoot": r"C:\Windows", "SYSTEMROOT": r"C:\Windows"})

    def test_rejects_root_hash_and_cargo_receipt_drift(self) -> None:
        def mutate(value):
            receipt = value["build"]["env_receipt"]
            receipt["WINDIR"]["value_sha256"] = "0" * 64
            receipt["CARGO_INCREMENTAL"]["entry_basenames"] = []
        self.mutate_report(mutate)

    def test_env_receipt_is_canonical_and_verifiable(self) -> None:
        import tools.run_com_workbook_accm_replay_v1 as runner
        native = {key: r"C:\VS\bin" for key in runner.NATIVE_ENV_KEYS}
        native["VCINSTALLDIR"] = r"C:\VS"
        native["VCToolsInstallDir"] = r"C:\VS\tools"
        native["WindowsSdkDir"] = r"C:\SDK"
        native["WindowsSDKVersion"] = "10.0"
        native["UCRTVersion"] = "10.0"
        native["UniversalCRTSdkDir"] = r"C:\SDK"
        fake_environment = {"SYSTEMROOT": r"C:\WINDOWS", "PATHEXT": ".COM;.EXE"}
        vcvars_identity = {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 1, "file_sha256": "a" * 64, "path_redacted": True}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(runner.os, "environ", fake_environment), mock.patch.object(runner, "capture_vcvars_env", return_value=(native, vcvars_identity)), mock.patch.object(runner, "resolve_regular", side_effect=lambda path, role: path), mock.patch.object(runner, "native_toolset", return_value={}):
            cargo_home = Path(directory) / "sipi-cargo-home-v1"; cargo_home.mkdir()
            _, metadata = runner.build_env(Path(r"C:\Rust\bin\rustc.exe"), Path(r"C:\Rust\bin\rust-lld.exe"), Path(r"C:\VS\vcvars64.bat"), Path(r"C:\Windows\System32\cmd.exe"), cargo_home, Path(directory) / "temp")
        receipt = metadata["variables"]
        self.assertEqual(receipt["SystemRoot"]["value_sha256"], receipt["WINDIR"]["value_sha256"])
        self.assertEqual(receipt["CARGO_INCREMENTAL"]["entry_basenames"], ["0"])
        self.assertEqual(receipt["CARGO_NET_OFFLINE"]["entry_basenames"], ["true"])
        value = valid_report("1" * 64, "a" * 64)
        value["build"]["env_receipt"] = receipt
        with tempfile.TemporaryDirectory() as directory:
            verify_report(self.write(Path(directory), "uppercase-systemroot.json", value))

    def test_rejects_toolchain_drift_in_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); value = json.loads(second.read_text()); value["toolchain"]["pre"]["cargo"]["file_sha256"] = "0" * 64; second.write_text(json.dumps(value)); aggregate = root / "aggregate.json"
            with self.assertRaises(ValueError): aggregator_module().aggregate(first, second, aggregate)

    def test_rejects_vcvars_drift_in_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); value = json.loads(second.read_text()); value["toolchain"]["vcvars64_pre"]["file_sha256"] = "0" * 64; second.write_text(json.dumps(value)); aggregate = root / "aggregate.json"
            with self.assertRaises(ValueError): aggregator_module().aggregate(first, second, aggregate)

    def test_rejects_source_inventory_drift_in_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); value = json.loads(second.read_text()); key = next(iter(value["upstream"]["source_inventory"])); value["upstream"]["source_inventory"][key]["sha256"] = "0" * 64; second.write_text(json.dumps(value)); aggregate = root / "aggregate.json"
            with self.assertRaises(ValueError): aggregator_module().aggregate(first, second, aggregate)

    def test_rejects_deterministic_flag_drift_in_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first, second = self.pair(root); value = json.loads(second.read_text()); value["build"]["deterministic_flags"][0]["sha256"] = "0" * 64; second.write_text(json.dumps(value)); aggregate = root / "aggregate.json"
            with self.assertRaises(ValueError): aggregator_module().aggregate(first, second, aggregate)

    def test_stable_candidate_keeps_raw_custody_hash_and_ignores_run_basename(self) -> None:
        first = {"binary_custody": {"pre": {"exe": {"basename": "run-a.exe", "bytes": 4, "sha256": "a" * 64}, "pdb": None}, "post": {"exe": {"basename": "run-a.exe", "bytes": 4, "sha256": "a" * 64}, "pdb": None}}}
        second = copy.deepcopy(first)
        second["binary_custody"]["pre"]["exe"]["basename"] = "run-b.exe"
        second["binary_custody"]["post"]["exe"]["basename"] = "run-b.exe"
        self.assertEqual(stable_candidate(first), stable_candidate(second))
        second["binary_custody"]["post"]["exe"]["sha256"] = "b" * 64
        self.assertEqual(stable_candidate(first), stable_candidate(second))

    def test_canonical_root_reuse_and_custody_bytes(self) -> None:
        with canonical_materialization_root() as first:
            self.assertEqual(first, canonical_root_path())
            (first / "discarded").write_bytes(b"stale")
        with canonical_materialization_root() as second:
            self.assertEqual(second, canonical_root_path())
            self.assertEqual([item.name for item in second.iterdir()], [".fresh-sentinel"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "built.exe"; destination = root / "custody" / "run.exe"
            source.write_bytes(b"deterministic-build-bytes")
            source.with_suffix(".pdb").write_bytes(b"Microsoft C/C++ MSF 7.00" + b"pdb-bytes" + bytes.fromhex("c" * 32))
            destination.parent.mkdir()
            copied = copy_binary_custody(source, destination, {"pdb_basename": "built.pdb", "pdb_guid": "c" * 32, "repro": True})
            expected = {"basename": destination.name, "bytes": destination.stat().st_size, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
            pdb = destination.parent / "built.pdb"
            self.assertEqual(copied, {"exe": {**expected, "source_bytes": source.stat().st_size, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, "pdb": {"basename": pdb.name, "bytes": pdb.stat().st_size, "sha256": hashlib.sha256(pdb.read_bytes()).hexdigest(), "source_bytes": source.with_suffix(".pdb").stat().st_size, "source_sha256": hashlib.sha256(source.with_suffix(".pdb").read_bytes()).hexdigest()}})

    def test_canonical_root_lock_rejects_concurrent_owner(self) -> None:
        lock = canonical_lock_path()
        with lock.open("xb") as stream:
            stream.write(b"foreign-owner")
        try:
            with self.assertRaises(RuntimeError), canonical_materialization_root():
                pass
        finally:
            lock.unlink()

    def test_canonical_root_setup_failure_releases_owned_lock(self) -> None:
        root = canonical_root_path()
        lock = canonical_lock_path()
        with mock.patch.object(Path, "mkdir", side_effect=OSError("mkdir blocked")), self.assertRaises(OSError):
            with canonical_materialization_root():
                pass
        self.assertFalse(lock.exists())
        self.assertFalse(root.exists())

    def test_path_gate_rejects_punctuation_and_unix_paths(self) -> None:
        for leaked in ("error=C:/secret", 'path="D:/secret"', "at(/opt/private)", "file:///etc/passwd", "at(/var/private)"):
            with self.subTest(leaked=leaked):
                value = valid_report("1" * 64, "a" * 64); value["runs"][0]["blocker"] = leaked
                with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                    verify_report(self.write(Path(directory), "report.json", value))

    def test_exact_redaction_token_is_allowed_but_embedded_is_not(self) -> None:
        value = valid_report("1" * 64, "a" * 64)
        value["runs"][0]["blocker"] = "<abs-path>"
        with tempfile.TemporaryDirectory() as directory:
            verify_report(self.write(Path(directory), "redacted.json", value))
        value["runs"][0]["blocker"] = "prefix <abs-path> suffix"
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            verify_report(self.write(Path(directory), "embedded.json", value))

    def test_redact_collapses_multiple_absolute_paths(self) -> None:
        self.assertEqual(redact(r"failed at C:\secret\one and /var/private/two"), "<abs-path>")

    def test_safe_archive_paths_reject_escape_and_drive(self) -> None:
        for name in ("../escape", "C:/escape", "/absolute", "//server/share"):
            with self.subTest(name=name), self.assertRaises(ValueError): safe_relative(name)

    def test_safe_archive_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "bad.tar"; destination = root / "out"
            with tarfile.open(archive, "w") as stream:
                info = tarfile.TarInfo("link"); info.type = tarfile.SYMTYPE; info.linkname = "secret"; stream.addfile(info)
            with self.assertRaises(ValueError): safe_extract(archive, destination)

    def test_pinned_blob_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            item = pinned_blob(Path.cwd().parent / "COM", FIXTURES["workbook"], Path(directory) / "workbook.xlsx")
            self.assertEqual(item["sha256"], FIXTURES["workbook"]["sha256"])

    def test_build_env_rejects_inherited_flags(self) -> None:
        old = os.environ.get("RUSTFLAGS")
        os.environ["RUSTFLAGS"] = "-C opt-level=0"
        try:
            with self.assertRaises(RuntimeError): build_env(Path("rustc.exe"), Path("link.exe"), Path("vcvars64.bat"), Path("cmd.exe"), Path.cwd(), Path.cwd())
        finally:
            if old is None: os.environ.pop("RUSTFLAGS", None)
            else: os.environ["RUSTFLAGS"] = old

    def test_vcvars_parser_requires_native_allowlist(self) -> None:
        output = "PATH=C:\\VS\\bin\nLIB=C:\\VS\\lib\nLIBPATH=C:\\VS\\lib\nINCLUDE=C:\\VS\\include\nVCINSTALLDIR=C:\\VS\nVCToolsInstallDir=C:\\VS\\tools\nWindowsSdkDir=C:\\SDK\nWindowsSDKVersion=10.0\nUCRTVersion=10.0\nUniversalCRTSdkDir=C:\\SDK\n"
        parsed = __import__("tools.run_com_workbook_accm_replay_v1", fromlist=["_parse_vcvars_output"])._parse_vcvars_output("banner\nMARK\n" + output, "MARK")
        self.assertEqual(parsed["WindowsSDKVersion"], "10.0")
        with self.assertRaises(ValueError):
            __import__("tools.run_com_workbook_accm_replay_v1", fromlist=["_parse_vcvars_output"])._parse_vcvars_output("MARK\n" + output + "PATH=C:\\evil\n", "MARK")
        with self.assertRaises(ValueError):
            __import__("tools.run_com_workbook_accm_replay_v1", fromlist=["_parse_vcvars_output"])._parse_vcvars_output("MARK\n" + output.replace("UCRTVersion=10.0\n", ""), "MARK")

    def test_build_env_does_not_inherit_processor_or_user_profile(self) -> None:
        self.assertNotIn("NUMBER_OF_PROCESSORS", BUILD_ENV_KEYS)
        self.assertNotIn("USERPROFILE", BUILD_ENV_KEYS)
        self.assertNotIn("HOME", BUILD_ENV_KEYS)

    def test_resolved_tool_and_fake_cmd_are_rejected(self) -> None:
        with self.assertRaises(ValueError): resolve_regular(Path("cmd.exe"), "cmd")

    def test_vcvars_probe_rejects_wrong_script_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); wrong = root / "setup.bat"; wrong.write_text("", encoding="ascii")
            with self.assertRaises(ValueError): capture_vcvars_env(wrong, root / "cmd.exe")
            vcvars = root / "vcvars64.bat"; vcvars.write_text("", encoding="ascii")
            cmd = root / "cmd.exe"; cmd.write_bytes(b"cmd")
            with mock.patch("tools.run_com_workbook_accm_replay_v1.subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd.exe"], 15)):
                with self.assertRaises(RuntimeError): capture_vcvars_env(vcvars, cmd)

    def test_runner_does_not_overwrite_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.json"; output.write_text("keep")
            with self.assertRaises(FileExistsError): run_one(Path(directory), Path(directory), Path("cargo.exe"), Path("rustc.exe"), Path("link.exe"), Path("vcvars64.bat"), Path("cmd.exe"), Path(directory), "1" * 64, output, Path(directory) / "custody")

    def test_result_parser_rejects_nonfinite_and_binds_all_cases(self) -> None:
        payload = json.dumps({"schema_version": 1, "source_revision": "r480", "profile": {}, "cases": [{"case_index": 0, "channels": {}, "metrics": {"FOM": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}, "diagnostics": {}}, {"case_index": 1, "channels": {}, "metrics": {"FOM": 4.0, "COM_dB": 5.0, "sigma_N_V": 6.0}, "diagnostics": {}}], "provenance": {}, "warnings": [], "timings_s": {}, "input_manifest": {}, "report_manifest": {}}).encode()
        _, metrics = parse_result_artifact(payload, [0.0, 0.001])
        self.assertEqual(set(metrics), {"0", "1"})
        with self.assertRaises(ValueError): parse_result_artifact(payload.replace(b"4.0", b"NaN"), [0.0, 0.001])

    def test_binary_identity_rejects_pseudo_pe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.exe"; payload = bytearray(1024); payload[:2] = b"MZ"; payload[0x3C:0x40] = (0x80).to_bytes(4, "little"); payload[0x80:0x84] = b"PE\0\0"; path.write_bytes(payload)
            with self.assertRaises(ValueError): binary_identity(path)

    def test_runner_state_machine_all_success_mixed_and_blocked(self) -> None:
        try:
            from . import run_com_workbook_accm_replay_v1 as runner
            from . import verify_com_workbook_accm_replay_v1 as verifier
        except ImportError:
            import run_com_workbook_accm_replay_v1 as runner
            import verify_com_workbook_accm_replay_v1 as verifier
        def fake_tool(_, role):
            return {"role": role, "basename": "rust-lld.exe" if role == "linker" else role + ".exe", "version_args": ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"] if role == "rc" else ["/d", "/c", "ver"] if role == "cmd" else ["-flavor", "link", "--version"] if role == "linker" else ["--version"], "file_sha256": "a" * 64, "version_output_sha256": "b" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
        def fake_archive(_, destination):
            destination.write_bytes(b"archive")
            return {"command": "archive", "exit": 0, "bytes": 7, "sha256": "c" * 64}
        def fake_extract(_, destination): (destination / "crates" / "sipi-agent-com-direct" / "target" / "release").mkdir(parents=True)
        def fake_blob(_, fixture, destination):
            destination.write_bytes(b"fixture")
            import hashlib
            return {**fixture, "basename": Path(fixture["path"]).name, "source_commit": runner.UPSTREAM_COMMIT, "bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}
        def fake_run(command, **kwargs):
            if "build" in command:
                if mode == "blocked": return subprocess.CompletedProcess(command, 101, "", "build failed")
                binary = Path(kwargs["cwd"]) / "crates" / "sipi-agent-com-direct" / "target" / "release" / "sipi-com-direct-run.exe"; pe = bytearray(1024); pe[:2] = b"MZ"; pe[0x3C:0x40] = (0x80).to_bytes(4, "little"); pe[0x80:0x84] = b"PE\0\0"; pe[0x84:0x86] = (0x8664).to_bytes(2, "little"); pe[0x86:0x88] = (1).to_bytes(2, "little"); pe[0x96:0x98] = (0x0002).to_bytes(2, "little"); pe[0x94:0x96] = (0xF0).to_bytes(2, "little"); pe[0x98:0x9A] = (0x20B).to_bytes(2, "little"); pe[0xA8:0xAC] = (0x100).to_bytes(4, "little"); pe[0xD4:0xD8] = (0x200).to_bytes(4, "little"); pe[0x188 + 8:0x188 + 12] = (0x200).to_bytes(4, "little"); pe[0x188 + 12:0x188 + 16] = (0x100).to_bytes(4, "little"); pe[0x188 + 16:0x188 + 20] = (0x100).to_bytes(4, "little"); pe[0x188 + 20:0x188 + 24] = (0x200).to_bytes(4, "little"); pe[0x188 + 36:0x188 + 40] = (0x20000000).to_bytes(4, "little"); binary.write_bytes(pe)
                return subprocess.CompletedProcess(command, 0, "", "")
            if mode == "mixed" and command[command.index("--override") + 1].endswith("0.001]"):
                return subprocess.CompletedProcess(command, 5, "", "runtime failed")
            out = Path(command[command.index("--output-dir") + 1]); out.mkdir(parents=True, exist_ok=True)
            if mode == "invalid":
                (out / "result.json").write_text("{}")
                return subprocess.CompletedProcess(command, 0, "", "")
            nonzero = command[command.index("--override") + 1].endswith("0.001]")
            metrics = [{"case_index": 0, "metrics": {"FOM": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}}, {"case_index": 1, "metrics": {"FOM": 4.0 + (1.0 if nonzero else 0.0), "COM_dB": 5.0 + (1.0 if nonzero else 0.0), "sigma_N_V": 6.0 + (1.0 if nonzero else 0.0)}}]
            (out / "result.json").write_text(json.dumps({"schema_version": 1, "source_revision": "r480", "profile": {}, "cases": [{"case_index": item["case_index"], "channels": {}, "metrics": item["metrics"], "diagnostics": {}} for item in metrics], "provenance": {}, "warnings": [], "timings_s": {}, "input_manifest": {}, "report_manifest": {}}))
            return subprocess.CompletedProcess(command, 0, "", "")
        native_receipt = fake_receipt()
        native_meta = {"vcvars64": {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 123, "file_sha256": "a" * 64, "path_redacted": True}, "native_tools": {"cl": fake_tool(None, "cl"), "lib": fake_tool(None, "lib"), "rc": fake_tool(None, "rc")}, "variables": native_receipt}
        fake_native_env = {key: f"native-{key}" for key in runner.NATIVE_ENV_KEYS}
        def fake_binary_identity(path, *_):
            if not path.is_file():
                return {"basename": path.name, "exists": False, "bytes": 0, "sha256": None, "canonical_sha256": None, "pe_offset": None, "optional_header_offset": None, "debug_directory_raw_pointer": None, "machine": None, "optional_magic": None, "characteristics": None, "debug_entries": 0, "codeview_rva": None, "codeview_raw_pointer": None, "codeview_bytes": None, "repro_entries": 0, "pdb_basename": None, "repro": False, "sections": [], "normalization_map": [], "certificate_bytes": 0, "overlay_bytes": 0}
            return {"basename": path.name, "exists": True, "bytes": 1024, "sha256": "a" * 64, "canonical_sha256": "b" * 64, "pe_offset": 100, "optional_header_offset": 124, "debug_directory_raw_pointer": 256, "machine": 0x8664, "optional_magic": 0x20B, "characteristics": 2, "debug_entries": 1, "codeview_rva": 256, "codeview_raw_pointer": 512, "codeview_bytes": 28, "repro_entries": 1, "pdb_basename": "sipi-com-direct-run.pdb", "repro": True, "sections": [{"name": ".text", "virtual_address": 256, "virtual_bytes": 512, "raw_pointer": 512, "bytes": 512, "sha256": "e" * 64}], "normalization_map": [{"role": "coff_timestamp", "offset": 108, "bytes": 4}, {"role": "debug_timestamp", "offset": 260, "bytes": 4}, {"role": "rsds_guid", "offset": 516, "bytes": 16}, {"role": "pe_checksum", "offset": 188, "bytes": 4}], "certificate_bytes": 0, "overlay_bytes": 0}
        def fake_custody(binary, destination, identity):
            destination.write_bytes(b"x" * 1024)
            pdb_destination = destination.parent / identity["pdb_basename"]
            pdb_destination.write_bytes(b"p" * 128)
            return {"exe": {"basename": destination.name, "bytes": 1024, "sha256": "a" * 64, "source_bytes": 1024, "source_sha256": "a" * 64}, "pdb": {"basename": pdb_destination.name, "bytes": 128, "sha256": "d" * 64, "source_bytes": 128, "source_sha256": "d" * 64}}
        def fake_registry(*_):
            entries = {"registry/src/fake/file": {"bytes": 1, "sha256": "a" * 64}}
            return {"entries": entries, "count": 1, "total_bytes": 1, "sha256": hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        for mode in ("success", "mixed", "blocked", "invalid"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                for target, replacement in (("archive", fake_archive), ("safe_extract", fake_extract), ("candidate_inventory", lambda _: {}), ("cargo_registry_inventory", fake_registry), ("pinned_blob", fake_blob), ("source_inventory", lambda _: {}), ("tool_identity", fake_tool), ("resolve_regular", lambda path, role: path), ("build_env", lambda *_: (fake_native_env, native_meta)), ("capture_vcvars_env", lambda *_: (fake_native_env, native_meta["vcvars64"])), ("native_toolset", lambda _: native_meta["native_tools"]), ("binary_identity", fake_binary_identity), ("copy_binary_custody", fake_custody), ("custody_file_identity", lambda path: {"basename": path.name, "bytes": 1024, "sha256": "a" * 64}), ("bounded_run", fake_run)):
                    stack.enter_context(mock.patch.object(runner, target, replacement))
                stack.enter_context(mock.patch.object(runner, "FIXED_CARGO_HOME", Path(directory)))
                stack.enter_context(mock.patch.object(runner, "custody_file_identity", lambda path: {"basename": path.name, "bytes": 128 if path.suffix.lower() == ".pdb" else 1024, "sha256": "d" * 64 if path.suffix.lower() == ".pdb" else "a" * 64}))
                report = run_one(Path(directory), Path(directory), Path("cargo.exe"), Path("rustc.exe"), Path("rust-lld.exe"), Path("vcvars64.bat"), Path("cmd.exe"), Path(directory), "1" * 64, Path(directory) / "report.json", Path(directory) / "custody")
                statuses = [item["status"] for item in report["runs"]]
                self.assertEqual(report["parity"]["status"], "numeric_observation" if mode == "success" else "blocked")
                self.assertEqual(statuses, ["matched", "matched"] if mode == "success" else ["matched", "blocked"] if mode == "mixed" else ["artifact_invalid", "artifact_invalid"] if mode == "invalid" else ["blocked", "blocked"])
                expected_fixtures = {key: {name: item[name] for name in ("path", "git_blob_sha1", "bytes", "sha256")} for key, item in report["fixtures"].items()}
                for target, replacement in (("CANDIDATE", report["candidate"]), ("UPSTREAM", {key: report["upstream"][key] for key in ("commit", "tree", "runtime")}), ("SOURCE_PATHS", tuple(report["upstream"]["source_inventory"])), ("EXPECTED_SOURCE_INVENTORY", report["upstream"]["source_inventory"]), ("EXPECTED_FIXTURES", expected_fixtures), ("FIXTURE_KEYS", tuple(expected_fixtures))):
                    stack.enter_context(mock.patch.object(verifier, target, replacement))
                verifier.verify_report(Path(directory) / "report.json")

    def test_success_controls_cannot_reuse_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = valid_report("1" * 64, "a" * 64)
            payload = json.dumps({"schema": "sipi.com.workbook-accm-canonical-metrics.v1", "control_vector": [0.0, 0.0], "cases": [{"case_index": 0, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}}, {"case_index": 1, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 4.0, "COM_dB": 5.0, "sigma_N_V": 6.0}}], "metric_fields": ["FOM_dB", "COM_dB", "sigma_N_V"], "channel_policy": "single_fd_to_td_impulse"}).encode()
            artifact = root / "same.json"; artifact.write_bytes(payload)
            import hashlib
            metrics = {"0": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}, "1": {"FOM_dB": 4.0, "COM_dB": 5.0, "sigma_N_V": 6.0}}
            for run in value["runs"]:
                run.update({"status": "matched", "exit": 0, "final_metrics": metrics, "consumer_proof": True, "artifact": {"path": artifact.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "raw_bytes": len(payload), "raw_sha256": hashlib.sha256(payload).hexdigest(), "case_metrics": metrics}, "blocker": None})
            value["parity"] = {"status": "numeric_observation", "matched": False, "acceptance": False}
            value["non_claims"] = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "PDB is opaque environment-local debug custody and nonpublish"]
            with self.assertRaises(ValueError): verify_report(self.write(root, "reuse.json", value))


if __name__ == "__main__":
    unittest.main()
