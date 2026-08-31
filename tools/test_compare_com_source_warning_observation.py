"""Focused regression tests for the source-warning observation gate."""

from __future__ import annotations

import copy
import unittest

from tools.compare_com_source_warning_observation import compare


def matlab(events: list[dict]) -> dict:
    return {"source_warning_calls": {"schema": "sipi.com.pinned-source-warning-call-observation.v1", "capture_incomplete": False, "events": events}}


def event(sequence: int, identifier: str, line: int) -> dict:
    return {"sequence": sequence, "identifier": identifier, "message": "source", "source_line": line}


def rust(roles: list[str]) -> dict:
    return {
        "provenance": {"warning_coverage": {"source_commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "source_file_sha256": "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad", "complete_catalog": False, "scope": "implemented_source_mapped_calls_only"}},
        "warnings": [{"namespace": "agent_com_r480", "code": "COM:read_s4p:MaxFreqTooLow", "source_callsite_id": "read_s4p.max_frequency_below_fb", "source_line": 9715, "channel_role": role, "source_sha256": "a" * 64, "maximum_frequency_hz": 80.0, "signaling_rate_hz": 100.0} for role in roles],
    }


class SourceWarningObservationTests(unittest.TestCase):
    def test_exact_supported_sequence_passes(self) -> None:
        report = compare(
            matlab([
                event(1, "COM:read_s4p:MaxFreqTooLow", 9715),
                event(2, "COM:read_s4p:MaxFreqTooLow", 9715),
                event(3, "COM:read_s4p:MaxFreqTooLow", 9715),
            ]),
            rust(["THRU", "FEXT", "NEXT"]),
        )
        self.assertEqual(report["status"], "passed_diagnostic")

    def test_unmapped_source_event_blocks_without_claiming_catalog(self) -> None:
        report = compare(matlab([event(1, "", 6337), event(2, "COM:read_s4p:MaxFreqTooLow", 9715)]), rust(["THRU"]))
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["unimplemented_source_events"], [{"sequence": 1, "identifier": "", "source_line": 6337}])

    def test_runtime_warning_at_root_is_rejected(self) -> None:
        candidate = rust([])
        candidate["warnings"].append({"code": "SIPI-COM-ANTI-CAUSAL-PHASE-SLOPE-BYPASSED"})
        with self.assertRaisesRegex(ValueError, "shape drift"):
            compare(matlab([]), candidate)

    def test_equal_or_greater_frequency_is_rejected(self) -> None:
        candidate = rust(["THRU"])
        candidate["warnings"][0]["maximum_frequency_hz"] = 100.0
        with self.assertRaisesRegex(ValueError, "predicate"):
            compare(matlab([event(1, "COM:read_s4p:MaxFreqTooLow", 9715)]), candidate)

    def test_repeated_warning_order_is_not_deduplicated(self) -> None:
        events = [event(index + 1, "COM:read_s4p:MaxFreqTooLow", 9715) for index in range(3)]
        report = compare(matlab(events), rust(["THRU", "NEXT", "FEXT"]))
        self.assertFalse(report["mapped_max_frequency"]["matched"])

    def test_source_capture_shape_fails_closed(self) -> None:
        source = matlab([event(1, "COM:read_s4p:MaxFreqTooLow", 9715)])
        source["source_warning_calls"]["capture_incomplete"] = True
        with self.assertRaisesRegex(ValueError, "schema/status"):
            compare(source, rust(["THRU"]))

    def test_coverage_provenance_fails_closed(self) -> None:
        candidate = copy.deepcopy(rust([]))
        candidate["provenance"]["warning_coverage"]["complete_catalog"] = True
        with self.assertRaisesRegex(ValueError, "coverage provenance"):
            compare(matlab([]), candidate)

    def test_source_warning_shape_fails_closed(self) -> None:
        candidate = rust(["THRU"])
        candidate["warnings"][0]["matlab_warning_parity"] = False
        with self.assertRaisesRegex(ValueError, "shape drift"):
            compare(matlab([event(1, "COM:read_s4p:MaxFreqTooLow", 9715)]), candidate)


if __name__ == "__main__":
    unittest.main()
