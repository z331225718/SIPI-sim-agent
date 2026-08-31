from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.run_com_tdiln_original13_diagnostic import _run_rust, _stable_result_sha256


class RustPerformanceInvocationTests(unittest.TestCase):
    def _capture_environment(self, sidecar_root: Path | None) -> dict[str, str]:
        captured: dict[str, str] = {}

        def fake_bounded(command: list[str], cwd: Path, timeout: int, environment: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
            self.assertEqual(command[1], "run")
            self.assertEqual(cwd, Path("source"))
            self.assertEqual(timeout, 30)
            captured.update(environment)
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch("tools.run_com_tdiln_original13_diagnostic.bounded", side_effect=fake_bounded):
            _run_rust(
                Path("rust.exe"),
                Path("workbook.xlsx"),
                [Path("thru.s4p"), Path("fext.s4p"), Path("next.s4p")],
                Path("output"),
                30,
                16,
                sidecar_root,
                Path("source"),
            )
        return captured

    def test_production_timing_clears_an_inherited_diagnostic_sink(self) -> None:
        with patch.dict(os.environ, {"SIPI_COM_TDILN_DIAGNOSTIC_SIDECAR_DIR": "inherited"}, clear=False):
            environment = self._capture_environment(None)
        self.assertEqual(environment["RAYON_NUM_THREADS"], "16")
        self.assertNotIn("SIPI_COM_TDILN_DIAGNOSTIC_SIDECAR_DIR", environment)

    def test_diagnostic_run_receives_only_its_explicit_sidecar_sink(self) -> None:
        environment = self._capture_environment(Path("sidecar"))
        self.assertEqual(environment["RAYON_NUM_THREADS"], "16")
        self.assertEqual(environment["SIPI_COM_TDILN_DIAGNOSTIC_SIDECAR_DIR"], "sidecar")

    def test_stable_result_hash_ignores_only_bound_replay_materialization_paths(self) -> None:
        root = Path(self._testMethodName)
        first = root / "first.json"
        second = root / "second.json"
        first.parent.mkdir(exist_ok=True)
        first.write_text(json.dumps({
            "input_manifest": {"pulse": r"C:\Temp\sipi-com-package-cases-12-" + "a" * 64 + r"\case-0\thru.s4p"},
            "channels": [r"C:\Temp\sipi-p5-06-tdiln-array-formal-" + "b" * 32 + r"\run1-output\upstream\fixture.s4p"],
            "provenance": {"config_sha256": "c" * 64, "input_sha256": "d" * 64},
            "metric": 1.0,
        }), encoding="utf-8")
        second.write_text(json.dumps({
            "input_manifest": {"pulse": r"C:\Temp\sipi-com-package-cases-34-" + "a" * 64 + r"\case-0\thru.s4p"},
            "channels": [r"C:\Temp\sipi-p5-06-tdiln-array-formal-" + "b" * 32 + r"\run2-output\upstream\fixture.s4p"],
            "provenance": {"config_sha256": "e" * 64, "input_sha256": "d" * 64},
            "metric": 1.0,
        }), encoding="utf-8")
        try:
            self.assertEqual(_stable_result_sha256(first), _stable_result_sha256(second))
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)
            first.parent.rmdir()

    def test_stable_result_hash_retains_non_ephemeral_provenance(self) -> None:
        root = Path(self._testMethodName)
        first = root / "first.json"
        second = root / "second.json"
        first.parent.mkdir(exist_ok=True)
        first.write_text(json.dumps({"provenance": {"input_sha256": "a" * 64}}), encoding="utf-8")
        second.write_text(json.dumps({"provenance": {"input_sha256": "b" * 64}}), encoding="utf-8")
        try:
            self.assertNotEqual(_stable_result_sha256(first), _stable_result_sha256(second))
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)
            first.parent.rmdir()

    def test_stable_result_hash_normalizes_only_the_supplied_replay_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            first_root = temporary_root / "current-replay-01"
            second_root = temporary_root / "current-replay-02"
            first = first_root / "result.json"
            second = second_root / "result.json"
            first_root.mkdir()
            second_root.mkdir()
            first.write_text(
                json.dumps({"channel": str(first_root / "upstream" / "fixture.s4p"), "metric": 1.0}),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps({"channel": str(second_root / "upstream" / "fixture.s4p"), "metric": 1.0}),
                encoding="utf-8",
            )
            self.assertEqual(
                _stable_result_sha256(first, first_root),
                _stable_result_sha256(second, second_root),
            )
            second.write_text(
                json.dumps({"channel": str(temporary_root / "outside" / "fixture.s4p"), "metric": 1.0}),
                encoding="utf-8",
            )
            self.assertNotEqual(
                _stable_result_sha256(first, first_root),
                _stable_result_sha256(second, second_root),
            )


if __name__ == "__main__":
    unittest.main()
