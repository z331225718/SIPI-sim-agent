"""Focused schema and mutation tests for COM ERL v4 preparation."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_com_erl_exact_profile_replay_v4 import (
    MANIFEST,
    VerificationError,
    path_free,
    verify_aggregate,
    verify_manifest,
    verify_report,
    verify_stage,
    runtime_projection,
)
from pb_03_replay_common import windows_pe_replay_custody
from test_pb_replay_common import ReplayCommonTests


def _identity(seed: str) -> dict[str, object]:
    return {"basename": seed, "file_sha256": "1" * 64, "version_output_sha256": "2" * 64, "version_exit": 0, "status": "ok", "path_redacted": True, "timeout_s": 180}


def _inventory() -> dict[str, object]:
    return {"count": 1, "combined_sha256": "3" * 64, "files": [{"path": "one.lib", "sha256": "4" * 64}]}


def _toolchain() -> dict[str, object]:
    special = {**_identity("rust-lld.exe"), "role": "rust-lld", "probe_strategy": "rust-lld --version; generic-driver exit 1 admitted", "status": "ok"}
    compiler = {**_identity("cl.exe"), "role": "msvc-cl", "probe_strategy": "cl.exe; no-source exit 2 admitted", "status": "ok_no_source"}
    libs = {"vcruntime.lib": {"present": True, "sha256": "5" * 64, "path": "vcruntime.lib"}, "msvcrt.lib": {"present": True, "sha256": "5" * 64, "path": "msvcrt.lib"}, "oldnames.lib": {"present": True, "sha256": "5" * 64, "path": "oldnames.lib"}}
    sdk_libs = {"ucrt.lib": {"present": True, "sha256": "5" * 64, "path": "ucrt.lib"}, "kernel32.lib": {"present": True, "sha256": "5" * 64, "path": "kernel32.lib"}, "user32.lib": {"present": True, "sha256": "5" * 64, "path": "user32.lib"}}
    return {
        "git": _identity("git.exe"), "cargo": _identity("cargo.exe"), "rustc": _identity("rustc.exe"), "uv": _identity("uv.exe"), "python": _identity("python.exe"),
        "linker": special, "compiler": compiler, "msvc": {"version": "14.44.35207", "include_order": ["msvc", "sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"], "lib_order": ["msvc", "sdk_ucrt", "sdk_um"], "lib_inventory": _inventory(), "key_libs": libs, "compiler": compiler},
        "sdk": {"version": "10.0.26100.0", "include_order": ["sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"], "lib_inventory": {"ucrt": _inventory(), "um": _inventory()}, "key_libs": {"ucrt": sdk_libs, "um": sdk_libs}},
        "rustc_wrapper": "cleared", "cargo_build_rustc_wrapper": "cleared", "rustc_workspace_wrapper": "cleared", "cargo_incremental": "0", "cargo_offline": True, "uv_offline": True,
    }


def _stage(count: int, digest: str) -> dict[str, object]:
    return {"count": count, "sha256": digest}


def _valid_report(manifest: dict[str, object], run_id: str, custody: dict[str, object]) -> dict[str, object]:
    positive = run_id != "com-erl-exact-v4-n1-negative"
    runtime_n = 800 if positive else 1
    profile = copy.deepcopy(manifest["controls"]["tdr_profile"])
    profile["runtime_n_ui"] = runtime_n
    candidate_profile = {"outer": manifest["controls"]["outer"], "tdr_profile": profile} if positive else None
    upstream_profile = {"outer": manifest["controls"]["outer"], "tdr_profile": profile}
    upstream_stage = {
        "tdr_time_s": _stage(2310 if positive else 15, "1" * 64),
        "tdr_impedance_ohm": _stage(2310 if positive else 15, "2" * 64),
        "ptdr_gated": manifest["preflight"]["positive"]["upstream_gated"] if positive else manifest["preflight"]["negative"]["upstream_gated"],
    }
    candidate_stage = {
        "channel_impulse": _stage(2310, "3" * 64),
        "channel_pulse": _stage(2310, "4" * 64),
        "erl_impulse": _stage(2310, "5" * 64),
        "ptdr": _stage(2310, "6" * 64),
        "gated": manifest["preflight"]["positive"]["candidate_gated"],
    } if positive else {}
    expected_metrics = manifest["expected"]["positive"] if positive else manifest["expected"]["negative_upstream"]
    metrics = {key: expected_metrics[key] for key in ("ERL", "ERL11", "ERL_RMS", "ERL_phase_index")}
    candidate_metrics = dict(manifest["expected"]["positive_candidate"]) if positive else {}
    execution = {
        "runner": {"path": manifest["tools"]["runner"]["path"], "sha256": manifest["tools"]["runner"]["sha256"]},
        "helper": {"path": manifest["tools"]["support"]["path"], "sha256": manifest["tools"]["support"]["sha256"]},
        "pe_helper": {"path": manifest["tools"]["pe_helper"]["path"], "sha256": manifest["tools"]["pe_helper"]["sha256"]},
        "timeout_s": 180, "build_timeout_s": 900, "upstream_elapsed_s": 1.0, "candidate_timeout_s": 180 if positive else None, "candidate_build_exit": 0 if positive else None,
        "build_profile": "release", "locked": True, "upstream_python_env": manifest["execution"]["upstream_python_env"], "upstream_uv_cache_policy": "caller_supplied_external", "upstream_command": manifest["execution"]["upstream_command"],
    }
    report = {
        "schema": "sipi.com.erl-only.exact-profile-replay.v4", "run_id": run_id, "fresh_run_nonce": ("1" if run_id.endswith("run1") else "2" if run_id.endswith("run2") else "3") * 64,
        "status": "bound_clean_archive_observation" if positive else "upstream_only_guard", "path_policy": {"mode": "relative identities only", "absolute_paths_emitted": False},
        "candidate": {"commit": manifest["candidate"]["commit"], "tree": manifest["candidate"]["tree"], "archive_sha256": manifest["candidate"]["archive_sha256"], "materialization": "git archive; no working-tree overlay", "runtime_executed": positive, "excluded_from_parity": not positive, "cargo_lock_sha256": manifest["candidate"]["cargo_lock_sha256"], **({"binary_sha256": custody["raw_sha256"], "binary_custody": custody} if positive else {})},
        "upstream": {"commit": manifest["upstream"]["commit"], "tree": manifest["upstream"]["tree"], "archive_sha256": manifest["upstream"]["archive_sha256"], "materialization": "git archive; no working-tree overlay", "runtime_executed": True, "uv_lock_sha256": manifest["upstream"]["uv_lock_sha256"], "pyproject_sha256": "7" * 64},
        "input": {"fixture_relative": manifest["fixture"]["relative_path"], "fixture_sha256": manifest["fixture"]["sha256"], "fixture_bytes": manifest["fixture"]["bytes"], "fixture_rows": manifest["fixture"]["rows"], "fixture_copies": {"pre_sha256": {"candidate": manifest["fixture"]["sha256"], "upstream": manifest["fixture"]["sha256"]}, "post_sha256": {"candidate": manifest["fixture"]["sha256"], "upstream": manifest["fixture"]["sha256"]}, "independent": True, "read_only": True}, "config_sha256": "8" * 64, "upstream_workbook_sha256": "9" * 64, "channel_kind": "exact_s2p_erl_only", "s_parameter_fit": "forbidden", "channel_policy": "raw S11 FD-to-TD impulse; no fit", "controls": manifest["controls"], "runtime_n_ui": runtime_n, "observation_duration_ui": 800},
        "control_crosswalk": {"candidate_profile": candidate_profile, "upstream_materialized": upstream_profile, "runtime_projection": {"candidate": runtime_projection(candidate_profile, manifest) if positive else None, "upstream": runtime_projection(upstream_profile, manifest)}, "mapping": manifest["control_crosswalk"], "status": "numeric_mismatch_open" if positive else "excluded_from_parity"},
        "stage_payload": {"mapping": manifest["stage_mapping"], "upstream": upstream_stage, "candidate": candidate_stage, "upstream_diagnostic_keys": [], "candidate_dispatch": "erl_only" if positive else None, "ptdr": {"status": "diagnostic_only_upstream_api_does_not_expose_raw_ptdr", "compared": False}},
        "upstream_output": metrics, "candidate_output": candidate_metrics, "artifact": {"candidate_result_sha256": "a" * 64 if positive else None}, "toolchain": _toolchain(), "execution": execution,
        "parity": {"fields": ["ERL", "ERL11", "ERL_RMS", "ERL_phase_index"], "numeric_policy": manifest["numeric_policy"], "matched": False, "differences": {}, "stage_differences": {"ptdr_gated": {"upstream": upstream_stage["ptdr_gated"], "candidate": candidate_stage["gated"]}} if positive else {}, "controls_equal": positive, "status": "numeric_mismatch_open" if positive else "excluded_from_parity"},
        "non_claims": manifest["non_claims"],
    }
    return report


class V4PrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        verify_manifest(cls.manifest)

    def test_manifest_freezes_positive_and_negative_controls(self):
        self.assertEqual(self.manifest["controls"]["positive_runtime_n_ui"], 800)
        self.assertEqual(self.manifest["controls"]["negative_runtime_n_ui"], 1)
        self.assertEqual(self.manifest["expected"]["positive"]["gated_count"], 2310)
        self.assertEqual(self.manifest["expected"]["negative_upstream"]["gated_count"], 15)

    def test_manifest_binds_v3_support_and_pe_helper(self):
        self.assertEqual(self.manifest["tools"]["support"]["path"], "tools/com_erl_exact_profile_replay_v3_support.py")
        self.assertEqual(self.manifest["tools"]["pe_helper"]["path"], "tools/pb_03_replay_common.py")

    def test_path_policy_rejects_posix_windows_and_unc(self):
        for value in ("/opt/overlay.py", "C:/overlay.py", "C:\\overlay.py", "\\\\server\\share"):
            self.assertFalse(path_free(value))
        self.assertTrue(path_free("docs/baselines/report.json"))

    def test_stage_schema_rejects_forged_matched_payloads(self):
        with self.assertRaises(VerificationError):
            verify_stage({"count": 0, "sha256": "0" * 64})
        with self.assertRaises(VerificationError):
            verify_stage({"count": 2310, "sha256": "0" * 63 + "G"})

    def test_manifest_mutations_fail_closed(self):
        mutations = [
            ("candidate", {"commit": "0" * 40}),
            ("fixture", {"sha256": "0" * 64}),
            ("controls", {"positive_runtime_n_ui": 1}),
            ("execution", {"runtime_timeout_s": 15}),
            ("policy", {"s_parameter_fit": "allowed"}),
            ("stage_mapping", {"ptdr_gated": {}}),
            ("reports", {"run_ids": ["com-erl-exact-v4-n800-run1"]}),
            ("tools", {"runner": {"path": "/opt/overlay.py", "sha256": "0" * 64}}),
            ("upstream", {"uv_lock_sha256": "0" * 64}),
        ]
        for key, value in mutations:
            mutated = copy.deepcopy(self.manifest)
            mutated[key].update(value)
            with self.subTest(key=key):
                with self.assertRaises(VerificationError):
                    verify_manifest(mutated)

    def test_report_mutations_fail_closed_before_runtime_claim(self):
        base = {"schema": "sipi.com.erl-only.exact-profile-replay.v4", "run_id": "com-erl-exact-v4-n800-run1", "fresh_run_nonce": "0" * 64}
        for mutation in (
            {"run_id": "com-erl-exact-v4-n800-run1"},
            {"run_id": "com-erl-exact-v4-n800-run1", "fresh_run_nonce": "1" * 63 + "G"},
            {"run_id": "com-erl-exact-v4-n1-negative"},
            {"run_id": "com-erl-exact-v4-n800-run1", "path": "/opt/overlay.py"},
        ):
            candidate = dict(base)
            candidate.update(mutation)
            with self.assertRaises(VerificationError):
                verify_report(candidate, self.manifest)

    def test_aggregate_mutations_fail_closed(self):
        for aggregate in (
            {"schema": "sipi.com.erl-only.exact-profile-replay.v4.aggregate"},
            {"schema": "sipi.com.erl-only.exact-profile-replay.v4.aggregate", "status": "matched"},
        ):
            with self.assertRaises(VerificationError):
                verify_aggregate(aggregate, self.manifest, [])

    def test_required_negative_control_and_order_are_manifest_bound(self):
        self.assertEqual(
            self.manifest["reports"]["run_ids"],
            ["com-erl-exact-v4-n800-run1", "com-erl-exact-v4-n800-run2", "com-erl-exact-v4-n1-negative"],
        )
        self.assertNotEqual(self.manifest["reports"]["positive"][0], self.manifest["reports"]["positive"][1])

    def test_complete_valid_report_builder_and_stage_equal_forge(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "candidate.exe"
            ReplayCommonTests._write_pe(binary)
            custody = windows_pe_replay_custody(binary)
            report = _valid_report(self.manifest, "com-erl-exact-v4-n800-run1", custody)
            from verify_com_erl_exact_profile_replay_v4 import verify_report
            verify_report(report, self.manifest)
            forged = copy.deepcopy(report)
            forged["stage_payload"]["candidate"]["gated"] = copy.deepcopy(forged["stage_payload"]["upstream"]["ptdr_gated"])
            with self.assertRaises(VerificationError):
                verify_report(forged, self.manifest)
            forged = copy.deepcopy(report)
            forged["control_crosswalk"]["runtime_projection"]["candidate"]["tdr_profile"]["runtime_n_ui"] = 1
            with self.assertRaises(VerificationError):
                verify_report(forged, self.manifest)

    def test_complete_report_mutations_reject_toolchain_runner_nonclaim_and_output_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "candidate.exe"
            ReplayCommonTests._write_pe(binary)
            report = _valid_report(self.manifest, "com-erl-exact-v4-n800-run1", windows_pe_replay_custody(binary))
            for mutation in (
                lambda value: value["toolchain"].clear(),
                lambda value: value["execution"]["runner"].update({"sha256": "0" * 64}),
                lambda value: value["non_claims"].clear(),
                lambda value: value["candidate_output"].update({"ERL": 99.0}),
            ):
                forged = copy.deepcopy(report)
                mutation(forged)
                with self.subTest(mutation=mutation):
                    with self.assertRaises(VerificationError):
                        verify_report(forged, self.manifest)

    def test_complete_negative_builder_requires_none_candidate_profile(self):
        report = _valid_report(self.manifest, "com-erl-exact-v4-n1-negative", {})
        from verify_com_erl_exact_profile_replay_v4 import verify_report
        verify_report(report, self.manifest)
        forged = copy.deepcopy(report)
        forged["control_crosswalk"]["candidate_profile"] = {"forged": True}
        with self.assertRaises(VerificationError):
            verify_report(forged, self.manifest)
        forged = copy.deepcopy(report)
        forged["stage_payload"]["upstream"]["ptdr_gated"]["sha256"] = "0" * 64
        with self.assertRaises(VerificationError):
            verify_report(forged, self.manifest)

    def test_complete_aggregate_status_and_two_run_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "candidate.exe"
            ReplayCommonTests._write_pe(binary)
            custody = windows_pe_replay_custody(binary)
            names = self.manifest["reports"]["positive"] + [self.manifest["reports"]["negative"]]
            paths = [Path(name) for name in names]
            reports = [_valid_report(self.manifest, run_id, custody) if "n800" in run_id else _valid_report(self.manifest, run_id, {}) for run_id in self.manifest["reports"]["run_ids"]]
            try:
                for path, report in zip(paths, reports, strict=True):
                    path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
                hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
                aggregate = {
                    "schema": "sipi.com.erl-only.exact-profile-replay.v4.aggregate", "status": "bound_clean_archive_observation", "run_ids": self.manifest["reports"]["run_ids"],
                    "reports": [{"path": path.as_posix(), "sha256": digest, "run_id": report["run_id"], "nonce": report["fresh_run_nonce"]} for path, digest, report in zip(paths, hashes, reports, strict=True)],
                    "candidate": {key: reports[0]["candidate"].get(key) for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")},
                    "upstream": reports[0]["upstream"], "fixture": self.manifest["fixture"], "controls": self.manifest["controls"], "stage_mapping": self.manifest["stage_mapping"], "toolchain_exact_equal": True, "pe_custody_compare": {"status": "ok", "errors": []},
                    "parity": {"status": "numeric_mismatch_open", "run_statuses": ["numeric_mismatch_open", "numeric_mismatch_open", "excluded_from_parity"]}, "non_claims": self.manifest["non_claims"],
                }
                verify_aggregate(aggregate, self.manifest, paths)
                forged = copy.deepcopy(aggregate)
                forged["status"] = "matched"
                with self.assertRaises(VerificationError):
                    verify_aggregate(forged, self.manifest, paths)
            finally:
                for path in paths:
                    path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
