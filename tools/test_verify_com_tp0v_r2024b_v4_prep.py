from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


PATH = Path(__file__).with_name("verify_com_tp0v_r2024b_v4_prep.py")
SPEC = importlib.util.spec_from_file_location("verify_com_tp0v_r2024b_v4_prep", PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class V4PreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(verify.MANIFEST.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(ValueError):
            verify.validate(document)

    def test_manifest_shape_is_valid(self) -> None:
        if any(item["sha256"] == "pending" for item in self.document["tools"].values()):
            self.skipTest("physical hashes are filled after the additive files land")
        verify.validate(self.document)

    def test_release_must_be_exact_r2024b(self) -> None:
        self.assert_invalid(lambda d: d["matlab"].update(required_release="R2026a"))

    def test_path_lookup_is_forbidden(self) -> None:
        self.assert_invalid(lambda d: d["matlab"].update(executable_mode="path_lookup"))

    def test_vector_tolerance_cannot_widen(self) -> None:
        self.assert_invalid(lambda d: d["comparison"]["vectors"]["tolerances"]["time_s"].update(absolute=5.0e-12))

    def test_transform_cannot_be_removed(self) -> None:
        self.assert_invalid(lambda d: d["comparison"]["vectors"].update(prohibited_transforms=[]))

    def test_vector_order_is_fixed(self) -> None:
        self.assert_invalid(lambda d: d["comparison"]["vectors"].update(names=["impedance_ohm", "time_s", "ptdr", "gated"]))

    def test_vector_case_port_binding_is_fixed(self) -> None:
        self.assert_invalid(lambda d: d["comparison"]["vectors"].update(case_to_port=[{"case_index": 0, "port": 2, "package_testcase_index": 0}]))

    def test_shape_and_first_sample_are_required(self) -> None:
        self.assert_invalid(lambda d: d["comparison"]["vectors"].update(first_sample_strict=False))

    def test_d3_must_remain_global_and_selected_disabled(self) -> None:
        self.assert_invalid(lambda d: d["d3_policy"].update(global_d3_enabled=False))
        self.assert_invalid(lambda d: d["d3_policy"].update(selected_configs_compute_tdiln=1))

    def test_all_four_replays_are_required(self) -> None:
        self.assert_invalid(lambda d: d.update(replays=["matlab-01", "matlab-02"]))

    def test_formal_path_must_be_absent(self) -> None:
        self.assert_invalid(lambda d: d["formal_paths_absent"].__setitem__(0, "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v4.yaml"))

    def test_tool_hash_and_path_are_bound(self) -> None:
        self.assert_invalid(lambda d: d["tools"]["runner"].update(path="tools/run_com_tp0v_r2024b_v3_diagnostic.py"))
        self.assert_invalid(lambda d: d["tools"]["runner"].update(sha256="0" * 64))

    def test_unsafe_tool_path_is_rejected(self) -> None:
        self.assert_invalid(lambda d: d["tools"]["runner"].update(path="../outside.py"))

    def test_base_manifest_is_pinned(self) -> None:
        self.assert_invalid(lambda d: d["base_v3_manifest"].update(path="docs/baselines/other.yaml"))

    def test_trace_timing_cannot_enter_performance_gate(self) -> None:
        self.assert_invalid(lambda d: d["performance"].update(instrumented_trace_included=True))
        self.assert_invalid(lambda d: d["performance"].update(semantic_timing_source="whole_worker"))


if __name__ == "__main__":
    unittest.main()
