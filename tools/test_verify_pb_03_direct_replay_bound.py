"""Mutation tests for PB-03 evidence binding."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_pb_03_05_direct_replay_bound import ROOT, verify  # noqa: E402


def test_pb03_baseline_and_mutations() -> None:
    path = ROOT / "docs/baselines/pb-03-direct-port.v1.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert verify(document, ROOT, "PB-03")["valid"]
    mutated = copy.deepcopy(document)
    mutated["claims"]["global_row_closed"] = True
    assert not verify(mutated, ROOT, "PB-03")["valid"]
    mutated = copy.deepcopy(document)
    mutated["evidence"]["reports"][0]["sha256"] = "0" * 64
    assert not verify(mutated, ROOT, "PB-03")["valid"]


def test_pb03_report_status_mutation_is_fail_closed() -> None:
    baseline = yaml.safe_load((ROOT / "docs/baselines/pb-03-direct-port.v1.yaml").read_text(encoding="utf-8"))
    report_path = ROOT / baseline["evidence"]["reports"][0]["path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["status"] = "passed"
    report["blockers"] = []
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        shutil.copytree(ROOT / "docs", temp_root / "docs")
        copied = temp_root / baseline["evidence"]["reports"][0]["path"]
        copied.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        mutated = copy.deepcopy(baseline)
        mutated["evidence"]["reports"][0]["sha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
        result = verify(mutated, temp_root, "PB-03")
        assert not result["valid"]
        # Rebinding a single report without regenerating the aggregate must
        # remain fail-closed.  The verifier may report the stale aggregate
        # binding directly (or, for older evidence, the derived process gate).
        assert any(
            phrase in item
            for item in result["blockers"]
            for phrase in ("aggregate report 1 digest drift", "candidate process gate drift")
        )
