"""Mutation tests for PB-05 payload-compare evidence."""

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


def test_pb05_payload_gate_and_claim_mutations() -> None:
    document = yaml.safe_load((ROOT / "docs/baselines/pb-05-direct-port.v1.yaml").read_text(encoding="utf-8"))
    assert verify(document, ROOT, "PB-05")["valid"]
    report_path = ROOT / document["evidence"]["reports"][0]["path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["replay"]["comparison"]["payload_gate"]["status_only_comparison"] is False
    report["replay"]["comparison"]["payload_gate"]["status_only_comparison"] = True
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        shutil.copytree(ROOT / "docs", temp_root / "docs")
        copied = temp_root / document["evidence"]["reports"][0]["path"]
        copied.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        mutated = copy.deepcopy(document)
        mutated["evidence"]["reports"][0]["sha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
        result = verify(mutated, temp_root, "PB-05")
        assert not result["valid"]
        assert any("status-only" in item for item in result["blockers"])
    mutated = copy.deepcopy(document)
    mutated["claims"]["release_approval"] = True
    assert not verify(mutated, ROOT, "PB-05")["valid"]
    mutated = copy.deepcopy(document)
    mutated["status"] = "accepted_scoped_native_core_bound_open"
    assert verify(mutated, ROOT, "PB-05")["valid"]
