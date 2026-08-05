from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import ContractViolation, RunRequestV1, parse_artifact_ref, parse_engine_capabilities, parse_provenance, parse_run_request, parse_run_result
from sipi_contracts.models import validate_run_result
from sipi_contracts.validation import resolve_artifact_path, validate_event


def request(payload=None):
    return {"schema":"sipi.run-request.v1","run_id":"run-1","project_id":"project-1","analysis_id":"analysis-1","attempt_id":"attempt-1","operation":"link.simulate.v1","payload_schema":"pybert.simulation.v1","payload":payload if payload is not None else {"source":"fixture"},"backend_selection":{"mode":"strict","instance":"pybert-python"},"resource_limits":{"enforcement":"monitor","wall_time_s":None,"cpu_time_s":None,"memory_bytes":None,"process_count":None,"artifact_bytes":None},"randomness":{},"artifact_policy":{},"extensions":{}}


def artifact(**changes):
    value={"schema":"sipi.artifact-ref.v1","content_schema":"pybert.output.v1","relative_path":"backends/backend-1/artifacts/result.json","mime_type":"application/json","sha256":"a"*64,"byte_length":1,"producer":"fixture.adapter","role":"domain_result","extensions":{}}
    value.update(changes)
    return value


def provenance():
    producer=lambda identity, kind, parents: {"id":identity,"kind":kind,"name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":parents}
    return {"producers":[producer("fixture.platform","platform",[]),producer("fixture.adapter","adapter",["fixture.platform"]),producer("fixture.engine","engine",["fixture.adapter"]),producer("fixture.algorithm","algorithm",["fixture.engine"])],"request":{"schema":"pybert.simulation.v1","behavior_profile":"fixture","inputs":[],"resolved_config_sha256":"a"*64},"environment":{"python":None,"rust":None,"os":"windows","cpu":"fixture","blas":None,"thread_count":1,"dependency_locks":[]},"randomness":{"seed":None,"array_sources":[]},"policies":{"fallback":[],"conditioning":[],"repairs":[],"truncations":[],"approximations":[]},"extensions":{}}


def result(req):
    return {"schema":"sipi.run-result.v1","run_id":req["run_id"],"analysis_id":req["analysis_id"],"attempt_id":req["attempt_id"],"operation":req["operation"],"payload_schema":req["payload_schema"],"status":"succeeded","selection_requested":req["backend_selection"],"backend_executions":[{"backend_execution_id":"backend-1","role":"primary","engine_instance_id":"pybert-python","bundle_hash":"sha256:bundle","status":"succeeded","domain_result_schema":"pybert.simulation.v1","artifacts":[artifact()],"error":None}],"fallback_trace":[],"comparison":{},"metrics_summary":{},"artifacts":[],"events":[],"warnings":[],"provenance":provenance(),"timings":{},"resource_usage":{"actual_enforcement":{"wall_time_s":"unsupported","cpu_time_s":"unsupported","memory_bytes":"unsupported","process_count":"unsupported","artifact_bytes":"unsupported"}},"error":None,"extensions":{}}


class ImmutableModelTests(unittest.TestCase):
    def test_input_mutation_and_nested_mutation_cannot_change_model(self):
        with self.assertRaises(TypeError): RunRequestV1({"payload": {}})
        raw=request({"nested":[1]})
        model=parse_run_request(raw)
        raw["payload"]["nested"].append(2)
        self.assertEqual(model.to_wire()["payload"], {"nested":[1]})
        with self.assertRaises(TypeError): model.wire["payload"]["nested"] += (2,)
        with self.assertRaises(FrozenInstanceError): model._data = {}  # type: ignore[misc]
        exported=model.to_wire()
        exported["payload"]["nested"].append(3)
        self.assertEqual(model.to_wire()["payload"], {"nested":[1]})

    def test_non_finite_json_is_rejected_at_both_entries(self):
        with self.assertRaisesRegex(ContractViolation,"non_finite"):
            parse_run_request(request({"number":math.nan}))
        raw=json.dumps(request()).replace('"fixture"', 'NaN', 1)
        with self.assertRaisesRegex(ContractViolation,"invalid_json"):
            parse_run_request(raw)

    def test_unknown_schema_and_artifact_paths_are_rejected(self):
        invalid=request()
        invalid["schema"]="sipi.run-request.v2"
        with self.assertRaises(ContractViolation): parse_run_request(invalid)
        with self.assertRaises(ContractViolation): parse_artifact_ref(artifact(relative_path="../escape"))

    def test_consumer_preserves_future_result_fields_but_producer_rejects_them(self):
        raw=result(request())
        raw["future_optional"]={"kept":True}
        model=parse_run_result(raw, producer=False)
        self.assertEqual(model.extra["future_optional"], {"kept":True})
        self.assertEqual(model.to_wire()["future_optional"], {"kept":True})
        with self.assertRaises(ContractViolation): validate_run_result(parse_run_request(request()), model, producer=True)

    def test_provenance_and_terminal_state_relations(self):
        parse_provenance(provenance(), producer=True)
        req=parse_run_request(request())
        raw=result(req.to_wire())
        raw["error"]={"category":"InternalInvariant","message":"bad","resource":None,"cause":None,"details":{}}
        with self.assertRaises(ContractViolation): parse_run_result(raw)

    def test_result_parse_closes_artifact_and_producer_invariants(self):
        raw=result(request())
        raw["backend_executions"][0]["artifacts"][0].update({"shape":[1],"dtype":"uint8","byte_order":"little","layout":"C"})
        with self.assertRaisesRegex(ContractViolation, "single-byte"):
            parse_run_result(raw)
        raw=result(request())
        raw["backend_executions"][0]["artifacts"][0]["producer"]="missing"
        with self.assertRaisesRegex(ContractViolation, "absent from provenance"):
            parse_run_result(raw)
        raw=result(request())
        raw["backend_executions"][0]["domain_result_schema"]=None
        raw["backend_executions"][0]["artifacts"]=[]
        with self.assertRaisesRegex(ContractViolation, "successful execution"):
            parse_run_result(raw, producer=True)

    def test_nested_events_obey_identity_and_consumer_compatibility(self):
        raw=result(request())
        event={"schema":"sipi.run-event.v1","run_id":"run-1","sequence":0,"scope":"project","stage":"started","elapsed_s":0,"analysis_id":None,"attempt_id":None,"backend_execution_id":None,"future_optional":{"kept":True},"extensions":{}}
        raw["events"]=[event]
        model=parse_run_result(raw, producer=False)
        self.assertTrue(model.to_wire()["events"][0]["future_optional"]["kept"])
        with self.assertRaisesRegex(ContractViolation, "unnamespaced"):
            parse_run_result(raw, producer=True)
        raw=result(request())
        raw["events"]=[{**event,"run_id":"other"}]
        with self.assertRaisesRegex(ContractViolation, "run_id mismatch"):
            parse_run_result(raw)

    def test_capability_parse_rejects_duplicate_stable_key(self):
        enforcement={"wall_time_s":"hard","cpu_time_s":"unsupported","memory_bytes":"unsupported","process_count":"unsupported","artifact_bytes":"unsupported"}
        capability={"operation":"link.simulate.v1","payload_schema":"pybert.simulation.v1","domain_result_schemas":["pybert.output.v1"],"behavior_profile":"default","role":"reference","execution_mode":"process","resource_enforcement":enforcement,"external_model_capabilities":{},"maximum_scale":{"vendor.max":1}}
        value={"schema":"sipi.engine-capabilities.v1","producer":"fixture","version":"1","build":"x","engine_instance_id":"pybert-python","bundle_hash":"sha256:x","platform":{"os":"windows","architecture":"x86_64"},"capabilities":[capability,dict(capability)],"extensions":{}}
        with self.assertRaisesRegex(ContractViolation, "duplicate"):
            parse_engine_capabilities(value)

    def test_event_cursor_and_resolved_path(self):
        prior={}
        event={"schema":"sipi.run-event.v1","run_id":"run-1","sequence":0,"scope":"project","stage":"started","elapsed_s":0,"analysis_id":None,"attempt_id":None,"backend_execution_id":None,"extensions":{}}
        validate_event(event, prior)
        with self.assertRaises(ContractViolation): validate_event({**event,"sequence":0}, prior)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            resolved=resolve_artifact_path(root, artifact(relative_path="safe/result.json"))
            self.assertEqual(resolved, root / "safe" / "result.json")
            with self.assertRaises(ContractViolation): resolve_artifact_path(root, artifact(relative_path="C:/escape"))
            target=root / "safe" / "target.json"
            target.parent.mkdir()
            target.write_text("fixture")
            link=root / "safe" / "linked.json"
            try:
                outside=Path(directory).parent / "outside.json"
                outside.write_text("outside")
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(ContractViolation, "outside"):
                resolve_artifact_path(root, artifact(relative_path="safe/linked.json"), must_exist=True)


if __name__ == "__main__":
    unittest.main()
