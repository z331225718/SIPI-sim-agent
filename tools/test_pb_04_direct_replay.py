"""Focused PB-04 selection semantic tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pb_03_replay_common import selection_summary  # noqa: E402


def test_pb04_selection_summary_preserves_fallback_gate() -> None:
    summary = selection_summary(
        {
            "diagnostics": {
                "engine_selection": {
                    "requested": "auto",
                    "selected": "python",
                    "implementation": "external_python_reference_required",
                    "fallback_reason": "native Web result contract parity is incomplete",
                    "parity_gate": {
                        "version": "pybert.native-auto-parity.v1",
                        "status": "blocked",
                        "reason": "native Web result contract parity is incomplete",
                    },
                }
            }
        }
    )
    assert summary is not None
    assert summary["requested"] == "auto"
    assert summary["selected"] == "python"
    assert summary["implementation"] == "external_python_reference_required"
    assert summary["parity_gate"]["status"] == "blocked"
