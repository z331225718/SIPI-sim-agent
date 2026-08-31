"""Focused contract tests for the MATLAB-only source-warning runner."""

from __future__ import annotations

import copy
import unittest

from tools.run_com_source_warning_observation import _source_events


def summary(events: list[dict]) -> dict:
    return {
        "source_warning_calls": {
            "schema": "sipi.com.pinned-source-warning-call-observation.v1",
            "capture_incomplete": False,
            "events": events,
        }
    }


def event(sequence: int, identifier: str, line: int) -> dict:
    stack = {"schema": "sipi.com.source-warning-stack.v1", "status": "not_requested"}
    if line == 6337:
        stack = {
            "schema": "sipi.com.source-warning-stack.v1", "status": "captured",
            "frames": [{"name": "warning", "line": 55}],
        }
    return {
        "sequence": sequence,
        "identifier": identifier,
        "message": "not retained",
        "source_line": line,
        "source_stack": stack,
        "source_trace": {"schema": "sipi.com.interp-sparam-input-trace.v1", "status": "not_requested"},
    }


class SourceWarningObservationRunnerTests(unittest.TestCase):
    def test_projects_only_bounded_source_warning_fields(self) -> None:
        actual = _source_events(summary([event(1, "COM:read_s4p:MaxFreqTooLow", 9715)]))
        self.assertEqual(actual, [{
            "sequence": 1,
            "identifier": "COM:read_s4p:MaxFreqTooLow",
            "source_line": 9715,
            "source_stack": {"schema": "sipi.com.source-warning-stack.v1", "status": "not_requested"},
            "source_trace": {"schema": "sipi.com.interp-sparam-input-trace.v1", "status": "not_requested"},
        }])

    def test_capture_or_line_drift_is_rejected(self) -> None:
        value = summary([event(1, "", 6337)])
        value["source_warning_calls"]["capture_incomplete"] = True
        with self.assertRaisesRegex(ValueError, "incomplete"):
            _source_events(value)
        value = summary([event(1, "", 6337)])
        value["source_warning_calls"]["events"][0]["source_line"] = 123
        with self.assertRaisesRegex(ValueError, "shape drift"):
            _source_events(value)

    def test_sequence_drift_is_rejected(self) -> None:
        value = summary([event(1, "", 6337)])
        drift = copy.deepcopy(value)
        drift["source_warning_calls"]["events"][0]["sequence"] = 2
        with self.assertRaisesRegex(ValueError, "sequence drift"):
            _source_events(drift)


if __name__ == "__main__":
    unittest.main()
