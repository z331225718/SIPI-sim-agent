"""Check the pinned portable oracle fixture remains semantically meaningful."""

from __future__ import annotations

import json
import math
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "docs" / "baselines" / "com-portable-upstream-oracle.v1.json"


class PortableOracleTests(unittest.TestCase):
    def test_source_binding_and_real_payloads(self) -> None:
        document = json.loads(ORACLE.read_text(encoding="utf-8"))
        self.assertEqual(document["source"]["commit"], "5272ffe74702cd585054d975559b06f8afae7b6e")
        self.assertEqual(document["source"]["license"], "MIT")
        self.assertEqual(document["oracle_kind"], "upstream_runtime_execution")
        self.assertEqual(document["invocation"], "tools/run_com_portable_upstream_oracle.py")
        self.assertEqual(document["calibration"]["iteration_count"], 4)
        self.assertGreater(document["mmse"]["fom_db"], 0.0)
        self.assertTrue(math.isfinite(document["calibration"]["sigma_bn_v"]))
        self.assertEqual(len(document["rx_ffe_search"]["filtered_waveform_sha256"]), 64)

    def test_pinned_upstream_runtime_invocation(self) -> None:
        environment = os.environ.copy()
        environment["AGENT_COM_ROOT"] = str(ROOT.parent / "COM")
        completed = subprocess.run(
            ["python", str(ROOT / "tools" / "run_com_portable_upstream_oracle.py")],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = json.loads(completed.stdout)
        self.assertEqual(observed["oracle_kind"], "upstream_runtime_execution")
        self.assertEqual(observed["source"]["commit"], document_commit := "5272ffe74702cd585054d975559b06f8afae7b6e")
        self.assertEqual(observed["mmse"]["condition_number"], json.loads(ORACLE.read_text())["mmse"]["condition_number"])


if __name__ == "__main__":
    unittest.main()
