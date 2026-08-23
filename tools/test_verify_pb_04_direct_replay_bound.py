"""Mutation tests for PB-04 selection evidence."""

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


def test_pb04_selection_and_claim_mutations() -> None:
    document = yaml.safe_load((ROOT / "docs/baselines/pb-04-direct-port.v1.yaml").read_text(encoding="utf-8"))
    assert verify(document, ROOT, "PB-04")["valid"]
    report_path = ROOT / document["evidence"]["reports"][0]["path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["replay"]["selection"]["oracle"]["selected"] = "rust"
    assert report["replay"]["selection"]["oracle"]["selected"] != "python"
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        shutil.copytree(ROOT / "docs", temp_root / "docs")
        copied = temp_root / document["evidence"]["reports"][0]["path"]
        copied.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        mutated = copy.deepcopy(document)
        mutated["evidence"]["reports"][0]["sha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
        result = verify(mutated, temp_root, "PB-04")
        assert not result["valid"]
        assert any("selected semantic drift" in item for item in result["blockers"])
    mutated = copy.deepcopy(document)
    mutated["claims"]["selection_semantics_observed"] = False
    assert verify(mutated, ROOT, "PB-04")["valid"]
    mutated["claims"]["global_row_closed"] = True
    assert not verify(mutated, ROOT, "PB-04")["valid"]
