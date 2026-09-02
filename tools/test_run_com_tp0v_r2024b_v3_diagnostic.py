"""Focused tests for the archive-only TP0V v3 diagnostic wrapper."""
from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("run_com_tp0v_r2024b_v3_diagnostic.py")
SPEC = importlib.util.spec_from_file_location("tp0v_v3_runner", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class Tp0vV3RunnerTests(unittest.TestCase):
    def test_archive_identity_binds_bytes_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.tar"
            path.write_bytes(b"candidate")
            expected = {"archive_bytes": 9, "archive_sha256": RUNNER.sha256_bytes(b"candidate")}
            receipt = RUNNER.archive_receipt(path, expected, "candidate")
            self.assertEqual(receipt["archive_bytes"], 9)
            self.assertEqual(receipt["archive_sha256"], expected["archive_sha256"])
            with self.assertRaises(RuntimeError):
                RUNNER.archive_receipt(path, {"archive_bytes": 8, "archive_sha256": expected["archive_sha256"]}, "candidate")

    def test_safe_materialize_rejects_parent_and_link_members(self) -> None:
        for member_name, kind in (("../escape", "file"), ("C:/escape", "file"), ("link", "symlink")):
            with self.subTest(member_name=member_name):
                with tempfile.TemporaryDirectory() as directory:
                    archive = Path(directory) / "input.tar"
                    with tarfile.open(archive, "w") as stream:
                        info = tarfile.TarInfo(member_name)
                        if kind == "symlink":
                            info.type = tarfile.SYMTYPE
                            info.linkname = "target"
                            stream.addfile(info)
                        else:
                            payload = b"x"
                            info.size = len(payload)
                            stream.addfile(info, io.BytesIO(payload))
                    with self.assertRaises(RuntimeError):
                        RUNNER.safe_materialize(archive, Path(directory) / "out")

    def test_explicit_tool_never_uses_path_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "cargo.exe"
            with self.assertRaises(RuntimeError):
                RUNNER.explicit_file(missing, "cargo")

    def test_matlab_receipt_requires_exact_r2024b_and_isolated_env(self) -> None:
        completed = RUNNER.subprocess.CompletedProcess(
            ["matlab.exe"],
            0,
            b"2024b\n26.2.0\nwin64\n",
            b"",
        )
        with tempfile.TemporaryDirectory() as directory:
            matlab = Path(directory) / "matlab.exe"
            matlab.write_bytes(b"matlab")
            with mock.patch.object(RUNNER, "run_command", return_value=(completed, 0.1)) as command:
                receipt = RUNNER.matlab_receipt(matlab, Path(directory))
            self.assertEqual(receipt["release"], "R2024b")
            env = command.call_args.args[3]
            self.assertEqual(env["MW_DISABLE_CONNECTOR"], "1")
            self.assertEqual(env["MATLABPATH"], "")
            self.assertTrue(Path(env["MATLAB_PREFDIR"]).is_dir())
            self.assertNotIn("which", RUNNER.explicit_file.__doc__.lower())

    def test_matlab_receipt_rejects_other_release(self) -> None:
        completed = RUNNER.subprocess.CompletedProcess(["matlab.exe"], 0, b"2026a\n26.1.0\nwin64\n", b"")
        with tempfile.TemporaryDirectory() as directory:
            matlab = Path(directory) / "matlab.exe"
            matlab.write_bytes(b"matlab")
            with mock.patch.object(RUNNER, "run_command", return_value=(completed, 0.1)):
                with self.assertRaises(RuntimeError):
                    RUNNER.matlab_receipt(matlab, Path(directory))

    def test_root_command_is_public_route(self) -> None:
        command = RUNNER.root_command(
            Path("candidate/target/release/sipi.exe"),
            Path("source/config.xlsx"),
            Path("source/thru.s4p"),
            Path("source/fext.s4p"),
            Path("source/next.s4p"),
            Path("output"),
        )
        self.assertEqual(command[1:3], ["com", "run"])
        self.assertIn("--config", command)
        self.assertIn("--thru", command)
        self.assertIn("--fext", command)
        self.assertIn("--next", command)
        self.assertIn("--output-dir", command)
        self.assertNotIn("sipi-com-direct-run", " ".join(command))

    def test_scalar_comparison_uses_only_frozen_shared_projection(self) -> None:
        shared = {name: 1.0 for name in RUNNER.CANONICAL_SCALAR_METRICS}
        rust = {**shared, "COM_dB": 1.0 + 1e-12, "candidate_only": 9.0}
        result = RUNNER.scalar_comparison([shared], [rust])
        self.assertTrue(result["passed"])
        self.assertEqual(result["metrics"], list(RUNNER.CANONICAL_SCALAR_METRICS))
        self.assertEqual(result["finite_absolute_tolerance"], 1e-9)

    def test_scalar_comparison_rejects_missing_or_nan_shared_metric(self) -> None:
        shared = {name: 1.0 for name in RUNNER.CANONICAL_SCALAR_METRICS}
        missing = dict(shared)
        missing.pop("ERL")
        self.assertFalse(RUNNER.scalar_comparison([shared], [missing])["passed"])
        nan = dict(shared)
        nan["ERL"] = float("nan")
        self.assertFalse(RUNNER.scalar_comparison([shared], [nan])["passed"])

    def test_bridge_comparison_requires_exact_slots(self) -> None:
        payload = {"shape": [1, 2], "slots": [{"row": 0, "column": 0, "kind": "number", "value": 1.0}, {"row": 0, "column": 1, "kind": "blank", "value": ""}]}
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "expected.json"
            observed = Path(directory) / "observed.json"
            expected.write_text(__import__("json").dumps(payload), encoding="utf-8")
            observed.write_text(__import__("json").dumps(payload), encoding="utf-8")
            self.assertTrue(RUNNER.bridge_comparison(expected, observed)["passed"])
            payload["slots"][1]["kind"] = "string"
            observed.write_text(__import__("json").dumps(payload), encoding="utf-8")
            self.assertFalse(RUNNER.bridge_comparison(expected, observed)["passed"])

    def test_d3_policy_does_not_alias_td_iln(self) -> None:
        metrics = [{"COM_dB": 1.0, "ERL": 2.0, "FOM_TDILN": 3.0}]
        result = RUNNER.d3_checkpoint_policy(metrics, metrics)
        self.assertFalse(result["passed"])
        self.assertFalse(result["entries"][2]["present"])

    def test_matlab_and_rust_case_extractors_require_two_case_shape(self) -> None:
        matlab = RUNNER.matlab_cases({"case_metrics": [{"output_metrics": {"ERL": {"kind": "inf"}}}, {"output_metrics": {"ERL": {"kind": "finite", "value": 1.25}}}]})
        rust = RUNNER.rust_cases({"cases": [{"metrics": {"ERL": None}}, {"metrics": {"ERL": 1.25}}]})
        self.assertEqual(matlab, [{"ERL": "+Inf"}, {"ERL": 1.25}])
        self.assertEqual(rust, [{"ERL": None}, {"ERL": 1.25}])


if __name__ == "__main__":
    unittest.main()
