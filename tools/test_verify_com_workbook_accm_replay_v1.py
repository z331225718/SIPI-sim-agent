"""Preparation-schema mutation tests (no formal replay artifacts)."""

from __future__ import annotations

import copy
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
    from .verify_com_workbook_accm_replay_v1 import ENV_KEYS, ENV_ROLES, EXPECTED_FIXTURES, EXPECTED_SOURCE_INVENTORY, SOURCE_PATHS, UPSTREAM, verify_aggregate, verify_report
except ImportError:
    from verify_com_workbook_accm_replay_v1 import ENV_KEYS, ENV_ROLES, EXPECTED_FIXTURES, EXPECTED_SOURCE_INVENTORY, SOURCE_PATHS, UPSTREAM, verify_aggregate, verify_report

try:
    from .run_com_workbook_accm_replay_v1 import BUILD_ENV_KEYS, FIXTURES, binary_identity, build_env, canonical_env_lookup, canonicalize_environment, capture_vcvars_env, parse_result_artifact, pinned_blob, redact, resolve_regular, run_one, safe_extract, safe_relative, tool_identity
except ImportError:
    from run_com_workbook_accm_replay_v1 import BUILD_ENV_KEYS, FIXTURES, binary_identity, build_env, canonical_env_lookup, canonicalize_environment, capture_vcvars_env, parse_result_artifact, pinned_blob, redact, resolve_regular, run_one, safe_extract, safe_relative, tool_identity


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
        "CARGO_HOME": [".cargo"], "RUSTC": ["rustc.exe"], "CARGO_BUILD_RUSTC": ["rustc.exe"],
        "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": ["rust-lld.exe"],
        "TEMP": ["<fresh-run-temp>"], "TMP": ["<fresh-run-temp>"],
        "CARGO_INCREMENTAL": ["0"], "CARGO_NET_OFFLINE": ["true"],
    }
    result = {}
    for key in ENV_KEYS:
        value_hash = "5" * 64
        if key in {"TEMP", "TMP"}: value_hash = fresh
        elif key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CL", "LINK"}: value_hash = empty
        elif key == "CARGO_INCREMENTAL": value_hash = zero
        elif key == "CARGO_NET_OFFLINE": value_hash = offline
        result[key] = {"role": ENV_ROLES.get(key, "native_environment"), "exists": True, "entry_basenames": entries.get(key, []), "value_sha256": value_hash, "path_redacted": True, "relation": "system_root" if key in {"SystemRoot", "WINDIR"} else "system32_under_system_root" if key == "ComSpec" else None}
    result["CARGO_BUILD_RUSTC"]["value_sha256"] = result["RUSTC"]["value_sha256"]
    return result


def valid_report(run_id: str, nonce: str) -> dict[str, object]:
    inventory = copy.deepcopy(EXPECTED_SOURCE_INVENTORY)
    fixtures = {key: {**value, "basename": Path(value["path"]).name, "source_commit": UPSTREAM["commit"]} for key, value in EXPECTED_FIXTURES.items()}
    tool = lambda role: {"role": role, "basename": f"{role}.exe", "version_args": ["/d", "/c", "ver"] if role == "cmd" else ["--version"], "file_sha256": "c" * 64, "version_output_sha256": "d" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
    native = lambda role: {"role": role, "basename": f"{role}.exe", "version_args": ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"], "file_sha256": "e" * 64, "version_output_sha256": "f" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
    fixtures = {key: {**item, "basename": Path(item["path"]).name, "source_commit": UPSTREAM["commit"], "pre_sha256": item["sha256"], "post_sha256": item["sha256"]} for key, item in EXPECTED_FIXTURES.items()}
    receipt = fake_receipt()
    runs = [{"control_vector": [0.0, 0.0], "status": "blocked", "exit": 3, "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64, "final_metrics": None, "consumer_proof": False, "artifact": None, "blocker": "blocked"}, {"control_vector": [0.0, 0.001], "status": "blocked", "exit": 3, "stdout_sha256": "3" * 64, "stderr_sha256": "4" * 64, "final_metrics": None, "consumer_proof": False, "artifact": None, "blocker": "blocked"}]
    binary = {"basename": "sipi-com-direct-run.exe", "exists": False, "bytes": 0, "sha256": None, "canonical_sha256": None}
    return {"schema": "sipi.com.workbook-accm-replay-prep.v3", "run_id": run_id, "nonce": nonce, "candidate": {"commit": "0f38e3e796b2312f476c6c5a181dd83d2752bb43", "tree": "241d86cc898616aa656f50ac47536fe169098115", "archive": {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": 0, "bytes": 44492800, "sha256": "9d627a57821db2f66e522eedacbefbca06a11eaa4e5b5f4c476b6ea95590cb01"}, "binary_pre": binary, "binary": copy.deepcopy(binary)}, "upstream": {**UPSTREAM, "source_inventory": inventory}, "fixtures": fixtures, "toolchain": {"pre": {"cargo": tool("cargo"), "rustc": tool("rustc"), "linker": tool("linker"), "cmd": tool("cmd")}, "post": {"cargo": tool("cargo"), "rustc": tool("rustc"), "linker": tool("linker"), "cmd": tool("cmd")}, "vcvars64_pre": {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 123, "file_sha256": "a" * 64, "path_redacted": True}, "vcvars64_post": {"role": "vcvars64", "basename": "vcvars64.bat", "bytes": 123, "file_sha256": "a" * 64, "path_redacted": True}, "native_pre": {"cl": native("cl"), "lib": native("lib"), "rc": native("rc")}, "native_post": {"cl": native("cl"), "lib": native("lib"), "rc": native("rc")}}, "build": {"command": "cargo build --manifest-path crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-run --release --locked --offline", "exit": 3, "stdout_sha256": "e" * 64, "stderr_sha256": "f" * 64, "timeout_s": 900, "env_policy": "vcvars64_allowlist_rustc_wrappers_cleared_offline_incremental_zero", "env_receipt": receipt}, "execution": {"runtime_timeout_s": 180, "source_inventory_before": {}, "source_inventory_after": {}, "source_inventory_equal": True}, "controls": {"ac_cm_rms_vectors": [[0.0, 0.0], [0.0, 0.001]], "source": "pinned workbook vector override", "no_sparam_fit": True, "channel_policy": "single_fd_to_td_impulse"}, "runs": runs, "parity": {"status": "blocked", "matched": False, "acceptance": False}, "non_claims": ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "no final consumer proof while blocked"]}


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

    def test_accepts_success_only_with_physical_result_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = valid_report("1" * 64, "a" * 64)
            for index, run in enumerate(value["runs"], start=1):
                payload = json.dumps({"schema": "sipi.com.workbook-accm-canonical-metrics.v1", "control_vector": [0.0, 0.0], "cases": [{"case_index": 0, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}}, {"case_index": 1, "ac_cm_rms": 0.0, "metrics": {"FOM_dB": 4.0 + index, "COM_dB": 5.0 + index, "sigma_N_V": 6.0 + index}}], "metric_fields": ["FOM_dB", "COM_dB", "sigma_N_V"], "channel_policy": "single_fd_to_td_impulse"}).encode()
                if index == 2:
                    payload = payload.replace(b'"control_vector": [0.0, 0.0]', b'"control_vector": [0.0, 0.001]').replace(b'"case_index": 1, "ac_cm_rms": 0.0', b'"case_index": 1, "ac_cm_rms": 0.001')
                artifact = root / f"run-result-{index}.json"; artifact.write_bytes(payload)
                import hashlib
                case_metrics = {"0": {"FOM_dB": 1.0, "COM_dB": 2.0, "sigma_N_V": 3.0}, "1": {"FOM_dB": 4.0 + index, "COM_dB": 5.0 + index, "sigma_N_V": 6.0 + index}}
                run.update({"status": "matched", "exit": 0, "final_metrics": case_metrics, "consumer_proof": True, "artifact": {"path": artifact.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "raw_bytes": len(payload), "raw_sha256": hashlib.sha256(payload).hexdigest(), "case_metrics": case_metrics}, "blocker": None})
            value["parity"] = {"status": "numeric_observation", "matched": False, "acceptance": False}
            value["non_claims"] = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim"]
            verify_report(self.write(root, "success.json", value))

    def test_rejects_schema(self): self.mutate_report(lambda x: x.__setitem__("schema", "forged"))
    def test_rejects_run_id(self): self.mutate_report(lambda x: x.__setitem__("run_id", "../" + "1" * 61))
    def test_rejects_nonce(self): self.mutate_report(lambda x: x.__setitem__("nonce", "z" * 64))
    def test_rejects_candidate(self): self.mutate_report(lambda x: x["candidate"].__setitem__("commit", "0" * 40))
    def test_rejects_archive_crlf_binding(self): self.mutate_report(lambda x: x["candidate"]["archive"].__setitem__("sha256", "0" * 64))
    def test_rejects_fixture_path(self): self.mutate_report(lambda x: x["fixtures"]["workbook"].__setitem__("path", "C:/wrong.xlsx"))
    def test_rejects_fixture_hash(self): self.mutate_report(lambda x: x["fixtures"]["s4p"].__setitem__("sha256", "0" * 64))
    def test_rejects_source_inventory(self): self.mutate_report(lambda x: x["upstream"]["source_inventory"].pop(next(iter(x["upstream"]["source_inventory"]))))
    def test_rejects_tool_role(self): self.mutate_report(lambda x: x["toolchain"]["pre"]["cargo"].__setitem__("role", "rustc"))
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
            _, metadata = runner.build_env(Path(r"C:\Rust\bin\rustc.exe"), Path(r"C:\Rust\bin\rust-lld.exe"), Path(r"C:\VS\vcvars64.bat"), Path(r"C:\Windows\System32\cmd.exe"), Path(directory) / ".cargo", Path(directory) / "temp")
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
            with self.assertRaises(RuntimeError): build_env(Path("rustc.exe"), Path("link.exe"), Path("vcvars64.bat"), Path("cmd.exe"))
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
            with self.assertRaises(FileExistsError): run_one(Path(directory), Path(directory), Path("cargo.exe"), Path("rustc.exe"), Path("link.exe"), Path("vcvars64.bat"), Path("cmd.exe"), "1" * 64, output)

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
            return {"role": role, "basename": role + ".exe", "version_args": ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"] if role == "rc" else ["/d", "/c", "ver"] if role == "cmd" else ["--version"], "file_sha256": "a" * 64, "version_output_sha256": "b" * 64, "version_exit": 0, "timeout_s": 15, "path_redacted": True}
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
        for mode in ("success", "mixed", "blocked", "invalid"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, mock.patch.object(runner, "archive", fake_archive), mock.patch.object(runner, "safe_extract", fake_extract), mock.patch.object(runner, "candidate_inventory", lambda _: {}), mock.patch.object(runner, "pinned_blob", fake_blob), mock.patch.object(runner, "source_inventory", lambda _: {}), mock.patch.object(runner, "tool_identity", fake_tool), mock.patch.object(runner, "resolve_regular", lambda path, role: path), mock.patch.object(runner, "build_env", lambda *_: (fake_native_env, native_meta)), mock.patch.object(runner, "capture_vcvars_env", lambda *_: (fake_native_env, native_meta["vcvars64"])), mock.patch.object(runner, "native_toolset", lambda _: native_meta["native_tools"]), mock.patch.object(runner, "bounded_run", fake_run):
                report = run_one(Path(directory), Path(directory), Path("cargo.exe"), Path("rustc.exe"), Path("link.exe"), Path("vcvars64.bat"), Path("cmd.exe"), "1" * 64, Path(directory) / "report.json")
                statuses = [item["status"] for item in report["runs"]]
                self.assertEqual(report["parity"]["status"], "numeric_observation" if mode == "success" else "blocked")
                self.assertEqual(statuses, ["matched", "matched"] if mode == "success" else ["matched", "blocked"] if mode == "mixed" else ["artifact_invalid", "artifact_invalid"] if mode == "invalid" else ["blocked", "blocked"])
                expected_fixtures = {key: {name: item[name] for name in ("path", "git_blob_sha1", "bytes", "sha256")} for key, item in report["fixtures"].items()}
                with mock.patch.object(verifier, "CANDIDATE", report["candidate"]), mock.patch.object(verifier, "UPSTREAM", {key: report["upstream"][key] for key in ("commit", "tree", "runtime")}), mock.patch.object(verifier, "SOURCE_PATHS", tuple(report["upstream"]["source_inventory"])), mock.patch.object(verifier, "EXPECTED_SOURCE_INVENTORY", report["upstream"]["source_inventory"]), mock.patch.object(verifier, "EXPECTED_FIXTURES", expected_fixtures), mock.patch.object(verifier, "FIXTURE_KEYS", tuple(expected_fixtures)):
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
            value["non_claims"] = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim"]
            with self.assertRaises(ValueError): verify_report(self.write(root, "reuse.json", value))


if __name__ == "__main__":
    unittest.main()
