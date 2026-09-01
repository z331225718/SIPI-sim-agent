from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

try:
    from .aggregate_p5_06_normal_erl_trace import aggregate
except ImportError:
    from aggregate_p5_06_normal_erl_trace import aggregate


class NormalErlTraceAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = json.loads(Path("docs/baselines/p5-06-normal-erl-trace-replay-01.v1.json").read_text(encoding="utf-8"))
        self.second = json.loads(Path("docs/baselines/p5-06-normal-erl-trace-replay-02.v1.json").read_text(encoding="utf-8"))

    def test_two_matching_replays_are_accepted(self) -> None:
        result = aggregate(self.first, self.second, "a" * 64, "b" * 64)
        self.assertEqual(result["status"], "accepted_named_normal_erl_tdr_array_checkpoint")
        self.assertGreater(result["performance"]["minimum_speedup_floor"], 1.0)

    def test_array_digest_drift_is_rejected(self) -> None:
        second = copy.deepcopy(self.second)
        second["records"][0]["comparison"]["ports"][0]["vectors"]["ptdr"]["matlab"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "semantic repeat drift"):
            aggregate(self.first, second, "a" * 64, "b" * 64)

    def test_rust_slower_than_matlab_is_rejected(self) -> None:
        second = copy.deepcopy(self.second)
        second["records"][2]["rust_wall_seconds"] = second["records"][2]["matlab_original_wall_seconds"]
        with self.assertRaisesRegex(ValueError, "Rust no-slower timing"):
            aggregate(self.first, second, "a" * 64, "b" * 64)


if __name__ == "__main__":
    unittest.main()
