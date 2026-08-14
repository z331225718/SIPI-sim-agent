from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ResidualDiagnosticCoreVerifierTests(unittest.TestCase):
    def test_current_baseline_passes(self) -> None:
        result = subprocess.run(
            ["python", "-B", "tools/verify_p3c_selected_highloss_residual_diagnostic_core.py"],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
