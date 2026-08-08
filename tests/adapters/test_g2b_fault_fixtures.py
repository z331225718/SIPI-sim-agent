from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters.process import run_process

G2B_EVIDENCE_SCHEMA = "sipi.g2b-fault-evidence.v1"
G2B_FIXTURE_ID = "g2b-windows-managed-worker-v1"


def _evidence(name: str, *, limit: str, observed: str, outcome: str, enforcer: str) -> dict:
    payload = {
        "schema": G2B_EVIDENCE_SCHEMA,
        "fixture": G2B_FIXTURE_ID,
        "case": name,
        "limit": limit,
        "observed": observed,
        "outcome": outcome,
        "enforcer": enforcer,
        "platform": {"os": "windows", "architecture": "x86_64"},
        "execution_mode": "managed_worker",
        "termination_evidence": True,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"payload": payload, "sha256": hashlib.sha256(canonical).hexdigest()}


@unittest.skipUnless(os.name == "nt", "G2b Windows fault fixtures run on Windows managed worker")
class G2bWindowsFaultFixtureTests(unittest.TestCase):
    """G2b lifecycle gate evidence: every advertised hard limit must have a
    real fault-injection hit on the Windows managed worker before it can be
    certified in capabilities.certified.v1.json."""

    def test_g2b_wall_time_timeout_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            result = run_process(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=1,
            )
            elapsed = time.monotonic() - started
            self.assertTrue(result.timed_out)
            self.assertLess(elapsed, 10)
            evidence = _evidence("wall_time", limit="1s", observed=f"{elapsed:.3f}s", outcome="Timeout", enforcer="job_object_job_time")
            self.assertEqual(evidence["payload"]["outcome"], "Timeout")

    def test_g2b_memory_hit_reports_resource_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", "x = bytearray(512 * 1024 * 1024)"],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"memory_bytes": 128 * 1024 * 1024},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.resource_violation, "memory_bytes")
            evidence = _evidence("memory", limit="128MiB", observed="peak>128MiB", outcome="ResourceLimit", enforcer="job_object_job_memory")
            self.assertEqual(evidence["payload"]["outcome"], "ResourceLimit")

    def test_g2b_cpu_hit_reports_resource_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", "while True: pass"],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"cpu_time_s": 1.0},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.resource_violation, "cpu_time_s")
            evidence = _evidence("cpu_time", limit="1s", observed="cpu>1s", outcome="ResourceLimit", enforcer="job_object_job_time")
            self.assertEqual(evidence["payload"]["outcome"], "ResourceLimit")

    def test_g2b_process_count_blocks_child(self) -> None:
        script = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']).wait()"
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", script],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"process_count": 1},
            )
            self.assertNotEqual(result.returncode, 0)
            evidence = _evidence("process_count", limit="1", observed="child block", outcome="ResourceLimit", enforcer="job_object_active_process")
            self.assertEqual(evidence["payload"]["outcome"], "ResourceLimit")

    def test_g2b_evidence_payload_is_machine_readable(self) -> None:
        """The evidence payload must validate against the G2b schema shape and
        carry the exact platform/execution key used for certification."""
        evidence = _evidence("wall_time", limit="1s", observed="1.001s", outcome="Timeout", enforcer="job_object_job_time")
        payload = evidence["payload"]
        self.assertEqual(payload["schema"], G2B_EVIDENCE_SCHEMA)
        self.assertEqual(payload["fixture"], G2B_FIXTURE_ID)
        self.assertEqual(payload["platform"]["os"], "windows")
        self.assertEqual(payload["execution_mode"], "managed_worker")
        self.assertEqual(len(evidence["sha256"]), 64)
        self.assertTrue(payload["termination_evidence"])


if __name__ == "__main__":
    unittest.main()
