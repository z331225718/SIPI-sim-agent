"""Focused custody tests for the shared PB replay helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pb_03_replay_common as common  # noqa: E402


class ReplayCommonTests(unittest.TestCase):
    def test_build_summary_has_closed_keys_and_binary_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "candidate.bin"
            binary.write_bytes(b"candidate")
            summary = common.build_summary(
                {"exit_code": 0, "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64, "unexpected": True},
                binary,
            )
        self.assertEqual(set(summary), {"exit_code", "stdout_sha256", "stderr_sha256", "binary_sha256"})
        self.assertEqual(len(summary["binary_sha256"]), 64)

    def test_run_command_clears_wrappers_and_sets_rustc(self) -> None:
        executable = Path(sys.executable)
        with patch.object(common.subprocess, "run") as run:
            run.return_value = common.subprocess.CompletedProcess([], 0, b"", b"")
            common.run_command(
                ["cargo", "--version"],
                Path.cwd(),
                1,
                {"cargo": executable, "rustc": executable},
            )
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["RUSTC"], str(executable))
        self.assertNotIn("RUSTC_WRAPPER", environment)
        self.assertNotIn("RUSTC_WORKSPACE_WRAPPER", environment)


if __name__ == "__main__":
    unittest.main()
