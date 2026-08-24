"""Prep tests for the PB-03 scoped aggregate contract."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_pb_03_05_direct_replay as aggregate  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REPORTS = [
    ROOT / "docs/baselines/pb-03-direct-ed7b12d2-run-01.json",
    ROOT / "docs/baselines/pb-03-direct-ed7b12d2-run-02.json",
]


def copied_reports(root: Path, first_mutation=None, second_mutation=None) -> tuple[Path, Path]:
    paths = []
    for index, source in enumerate(REPORTS):
        value = json.loads(source.read_text(encoding="utf-8"))
        mutation = (first_mutation, second_mutation)[index]
        if mutation is not None:
            mutation(value)
        target = root / f"report-{index + 1}.json"
        target.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(target)
    return paths[0], paths[1]


def test_pb03_aggregate_has_scoped_claims_and_binary_gate() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        first, second = copied_reports(Path(temporary))
        result = aggregate.aggregate(first, second, Path(temporary) / "aggregate.json", "PB-03")
    assert result["status"] == "passed", result
    assert result["claims"] == {
        "payload_parity": True,
        "payload_scope": "fixed_pb03_stable_array_subset",
        "whole_payload_parity": False,
        "independent_implementation": False,
        "global_row_closed": False,
        "release_approval": False,
    }
    assert result["binary_gate"]["candidate_binary_matches_raw"] is True
    assert result["binary_gate"]["raw_binary_sha256_distinct"] is True
    assert result["binary_gate"]["canonical_binary_sha256_equal"] is False
    assert result["binary_gate"]["no_bit_reproducible_build_claim"] is True
    assert "fixed stable array subset" in result["non_claims"][1]


def test_pb03_aggregate_claim_and_custody_mutations_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first, second = copied_reports(root, lambda value: value["claims"].update({"whole_payload_parity": True}), None)
        result = aggregate.aggregate(first, second, root / "claims.json", "PB-03")
        assert result["status"] == "blocked"
        first, second = copied_reports(root, lambda value: value.update({"custody": None}), None)
        result = aggregate.aggregate(first, second, root / "custody.json", "PB-03")
        assert result["status"] == "blocked"


def test_pb03_aggregate_build_and_pe_mutations_block_without_exception() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first, second = copied_reports(root, lambda value: value["build"].update({"binary_sha256": "0" * 64}), None)
        result = aggregate.aggregate(first, second, root / "raw-drift.json", "PB-03")
        assert result["status"] == "blocked"
        first, second = copied_reports(root, lambda value: value.update({"build": None}), None)
        result = aggregate.aggregate(first, second, root / "missing-build.json", "PB-03")
        assert result["status"] == "blocked"
        first, second = copied_reports(root, lambda value: value["build"]["binary_custody"]["normalization"]["ranges"][0].update({"canonical_hex": "ffffffff"}), None)
        result = aggregate.aggregate(first, second, root / "normalization.json", "PB-03")
        assert result["status"] == "blocked"


def test_pb03_aggregate_malformed_payload_is_blocked_not_thrown() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first, second = copied_reports(root, lambda value: value["replay"].update({"payload": None}), None)
        result = aggregate.aggregate(first, second, root / "payload.json", "PB-03")
        assert result["status"] == "blocked"


def test_pb03_aggregate_output_is_create_new() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first, second = copied_reports(root)
        output = root / "aggregate.json"
        aggregate.aggregate(first, second, output, "PB-03")
        with pytest.raises(ValueError, match="create-new"):
            aggregate.aggregate(first, second, output, "PB-03")


def test_pb04_pb05_aggregate_schema_is_unchanged() -> None:
    expected = {"blockers", "candidate", "claims", "distinct_gate", "fixture", "non_claims", "payload", "reports", "row", "schema", "status", "toolchain", "upstream", "workflow_semantics"}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first, second = copied_reports(root)
        for row, schema in (("PB-04", "sipi.pb-04-direct-replay.v1"), ("PB-05", "sipi.pb-05-direct-replay.v1")):
            for path in (first, second):
                value = json.loads(path.read_text(encoding="utf-8"))
                value["row"] = row
                value["schema"] = schema
                path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
            result = aggregate.aggregate(first, second, root / f"{row}.json", row)
            assert set(result) == expected, result
