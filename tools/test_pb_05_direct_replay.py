"""Focused PB-05 payload comparison semantic tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pb_03_replay_common import comparison_summary  # noqa: E402


def test_pb05_comparison_summary_is_payload_based() -> None:
    summary = comparison_summary(
        {
            "diagnostics": {
                "comparison": {
                    "schema": "pybert.engine-compare.v1",
                    "passed": False,
                    "arrays": {"passed": False},
                    "metadata": {"passed": False},
                }
            }
        }
    )
    assert summary == {
        "schema": "pybert.engine-compare.v1",
        "passed": False,
        "status_only_comparison": None,
        "arrays_passed": False,
        "metrics_passed": None,
        "metadata_passed": False,
        "reason": None,
        "reference_required": None,
        "source": None,
    }
