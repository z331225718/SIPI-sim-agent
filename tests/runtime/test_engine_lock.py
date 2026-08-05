from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import ContractViolation, parse_engine_lock
from sipi_runtime import EngineLockLoadError, EngineRegistry, UnknownEngineInstance, load_engine_lock


def engine(instance_id="fixture-python"):
    digest = "a" * 64
    return {"instance_id":instance_id,"engine_family":"fixture","version":"1.0.0","source_commit":"b"*40,"bundle":{"kind":"local_path","path":"bundles/fixture.whl","sha256":digest},"protocol":{"request_schema":"sipi.backend-execution-request.v1","result_schema":"sipi.backend-execution-result.v1"},"capabilities":{"schema":"sipi.engine-capabilities.v1","sha256":digest},"runtime":{"kind":"python","os":"windows","architecture":"x86_64","python_abi":"cp312","rust_target":None},"dependency_lock_sha256":digest,"license_provenance":{"distribution_status":"blocked_unknown","manifest_sha256":digest},"bundle_manifest":{"entrypoint":"bin/fixture.exe","files":[{"relative_path":"bin/fixture.exe","role":"entrypoint","sha256":digest,"byte_length":1}]},"extensions":{}}


def lock(engines=None, defaults=None):
    return {"schema":"sipi.engine-lock.v1","engines":engines or [],"operation_defaults":defaults or {},"extensions":{}}


class EngineLockTests(unittest.TestCase):
    def test_empty_lock_fixture_and_exact_registry(self):
        empty = parse_engine_lock((ROOT / "fixtures" / "engine-lock.empty.v1.json").read_text())
        with self.assertRaises(UnknownEngineInstance): EngineRegistry(empty).lookup("fixture")
        value = parse_engine_lock(lock([engine()], {"link.simulate.v1":{"mode":"strict","instance":"fixture-python"}}))
        registry = EngineRegistry(value)
        self.assertEqual(registry.lookup("fixture-python")["engine_family"], "fixture")
        with self.assertRaises(TypeError): registry.lookup("fixture-python")["bundle"]["path"] = "changed"
        self.assertEqual(registry.default_for("link.simulate.v1"), {"mode":"strict","instance":"fixture-python"})
        self.assertIsNone(registry.default_for("network.fit.v1"))

    def test_cross_field_validation_rejects_aliases_and_bad_defaults(self):
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([engine(), engine()]))
        bad = engine(); bad["bundle_manifest"]["entrypoint"] = "bin/missing.exe"
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([engine()], {"link.simulate.v1":{"mode":"auto","candidates":["fixture-python","missing"],"fallback_on":["EngineUnavailable","UnsupportedCapability"]}}))
        bad = engine(); bad["bundle"]["path"] = "../escape"
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["source_commit"] = "b" * 41
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["source_commit"] = 123
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["bundle_manifest"]["files"][0]["relative_path"] = "bin/"
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["runtime"] = {"kind":"hybrid","os":"windows","architecture":"x86_64","python_abi":None,"rust_target":None}
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["runtime"]["python_abi"] = ""
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        bad = engine(); bad["runtime"] = {"kind":"native","os":"windows","architecture":"x86_64","python_abi":None,"rust_target":""}
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([bad]))
        with self.assertRaises(ContractViolation): parse_engine_lock(lock([engine()], {"link.simulate.v1":{"mode":"compare","reference":"fixture-python","candidate":"fixture-python","comparison_profile":"fixture"}}))

    def test_runtime_loader_distinguishes_missing_and_malformed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            with self.assertRaises(EngineLockLoadError): load_engine_lock(path)
            path.write_text("not-json")
            with self.assertRaises(EngineLockLoadError): load_engine_lock(path)
            path.write_text(json.dumps(lock()))
            self.assertEqual(load_engine_lock(path).schema_id, "sipi.engine-lock.v1")


if __name__ == "__main__": unittest.main()
