from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import parse_engine_lock
from sipi_runtime import EngineRegistry, SelectionError, resolve_selection, selection_hash


def engine_entry(instance_id: str, *, license_status: str = "authorized_public", internal: bool = False) -> dict:
    digest = "a" * 64
    return {
        "instance_id": instance_id,
        "engine_family": "fixture",
        "version": "1.0.0",
        "source_commit": "b" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fixture.whl", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": digest},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": digest,
        "license_provenance": {"distribution_status": license_status, "manifest_sha256": digest},
        "bundle_manifest": {"entrypoint": "bin/fixture.exe", "files": [{"relative_path": "bin/fixture.exe", "role": "entrypoint", "sha256": digest, "byte_length": 1}]},
        "extensions": {"sipi.internal": True} if internal else {},
    }


def registry(*entries: dict) -> EngineRegistry:
    lock = {"schema": "sipi.engine-lock.v1", "engines": list(entries), "operation_defaults": {}, "extensions": {}}
    return EngineRegistry(parse_engine_lock(lock))


class SelectionTests(unittest.TestCase):
    def test_strict_resolves_primary_with_deterministic_hash(self) -> None:
        reg = registry(engine_entry("a"), engine_entry("b"))
        selection = {"mode": "strict", "instance": "b"}
        trace = resolve_selection(selection, reg)
        self.assertEqual(trace.mode, "strict")
        self.assertEqual([(item.role, item.instance_id) for item in trace.resolved], [("primary", "b")])
        self.assertEqual(trace.selection_hash, selection_hash(selection))
        self.assertNotEqual(
            trace.selection_hash,
            selection_hash({"mode": "strict", "instance": "a"}),
        )

    def test_strict_unknown_instance_is_engine_unavailable(self) -> None:
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "strict", "instance": "missing"}, registry(engine_entry("a")))
        self.assertEqual(caught.exception.category, "EngineUnavailable")

    def test_strict_blocked_license_is_unsupported_capability(self) -> None:
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "strict", "instance": "a"}, registry(engine_entry("a", license_status="blocked_unknown")))
        self.assertEqual(caught.exception.category, "UnsupportedCapability")

    def test_internal_gate_requires_allow_internal(self) -> None:
        reg = registry(engine_entry("a", internal=True))
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "strict", "instance": "a"}, reg)
        self.assertEqual(caught.exception.category, "UnsupportedCapability")
        trace = resolve_selection({"mode": "strict", "instance": "a", "allow_internal": True}, reg, allow_internal=True)
        self.assertTrue(trace.internal)

    def test_experimental_opt_in_has_no_certified_evidence_in_m2(self) -> None:
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "strict", "instance": "a", "allow_experimental": True}, registry(engine_entry("a")))
        self.assertEqual(caught.exception.category, "UnsupportedCapability")

    def test_auto_picks_stable_candidate_and_records_fallback(self) -> None:
        reg = registry(engine_entry("a", license_status="blocked_unknown"), engine_entry("b"))
        selection = {"mode": "auto", "candidates": ["a", "missing", "b"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}
        trace = resolve_selection(selection, reg)
        self.assertEqual([(item.role, item.instance_id) for item in trace.resolved], [("primary", "b")])
        self.assertEqual(len(trace.fallback_trace), 2)
        self.assertIn("a:", trace.fallback_trace[0])
        self.assertIn("missing:", trace.fallback_trace[1])

    def test_auto_with_no_stable_candidate_is_engine_unavailable(self) -> None:
        reg = registry(engine_entry("a", license_status="blocked_unknown"))
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "auto", "candidates": ["a"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}, reg)
        self.assertEqual(caught.exception.category, "EngineUnavailable")

    def test_auto_internal_candidate_falls_back(self) -> None:
        reg = registry(engine_entry("a", internal=True), engine_entry("b"))
        trace = resolve_selection({"mode": "auto", "candidates": ["a", "b"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}, reg)
        self.assertEqual([(item.role, item.instance_id) for item in trace.resolved], [("primary", "b")])
        self.assertEqual(len(trace.fallback_trace), 1)
        self.assertIn("internal-only", trace.fallback_trace[0])

    def test_compare_resolves_reference_and_candidate(self) -> None:
        reg = registry(engine_entry("ref"), engine_entry("cand"))
        selection = {"mode": "compare", "reference": "ref", "candidate": "cand", "comparison_profile": "default"}
        trace = resolve_selection(selection, reg)
        self.assertEqual([(item.role, item.instance_id) for item in trace.resolved], [("reference", "ref"), ("candidate", "cand")])
        self.assertEqual(trace.comparison_profile, "default")

    def test_compare_requires_distinct_instances(self) -> None:
        with self.assertRaises(SelectionError) as caught:
            resolve_selection({"mode": "compare", "reference": "a", "candidate": "a", "comparison_profile": "default"}, registry(engine_entry("a")))
        self.assertEqual(caught.exception.category, "EngineUnavailable")

    def test_compare_internal_gate_passes_allow_internal(self) -> None:
        reg = registry(engine_entry("ref", internal=True), engine_entry("cand"))
        selection = {"mode": "compare", "reference": "ref", "candidate": "cand", "comparison_profile": "default", "allow_internal": True}
        with self.assertRaises(SelectionError) as caught:
            resolve_selection(selection, reg)
        self.assertEqual(caught.exception.category, "UnsupportedCapability")
        trace = resolve_selection(selection, reg, allow_internal=True)
        self.assertEqual([(item.role, item.instance_id) for item in trace.resolved], [("reference", "ref"), ("candidate", "cand")])

    def test_selection_hash_is_key_order_independent(self) -> None:
        first = selection_hash({"mode": "strict", "instance": "a"})
        second = selection_hash({"instance": "a", "mode": "strict"})
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
