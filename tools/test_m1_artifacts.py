import copy
import unittest

from verify_m1_artifacts import (
    map_com_artifact,
    map_pybert_artifact_ref,
    validate_artifact_collection,
    validate_artifact_ref,
    validate_provenance,
)

def artifact(**changes):
    value={"schema":"sipi.artifact-ref.v1","content_schema":"pybert.output.v1","relative_path":"artifacts/result.json","mime_type":"application/json","sha256":"a"*64,"byte_length":1,"producer":"fixture.adapter","role":"domain_result","extensions":{}}
    value.update(changes); return value

def provenance(**changes):
    value={"producers":[{"id":"fixture.platform","kind":"platform","name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":[]},{"id":"fixture.adapter","kind":"adapter","name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":["fixture.platform"]},{"id":"fixture.engine","kind":"engine","name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":["fixture.adapter"]},{"id":"fixture.algorithm","kind":"algorithm","name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":["fixture.engine"]}],"request":{"schema":"pybert.simulation.v1","behavior_profile":"fixture","inputs":[],"resolved_config_sha256":"a"*64},"environment":{"python":None,"rust":None,"os":"windows","cpu":"fixture","blas":None,"thread_count":1,"dependency_locks":[]},"randomness":{"seed":None,"array_sources":[]},"policies":{"fallback":[],"conditioning":[],"repairs":[],"truncations":[],"approximations":[]},"extensions":{}}
    value.update(changes); return value

class ArtifactTests(unittest.TestCase):
    def test_valid_and_provenance(self):
        value=provenance()
        validate_provenance(value)
        validate_artifact_ref(artifact(), provenance=value)
    def test_path_and_array_rules(self):
        with self.assertRaises(Exception): validate_artifact_ref(artifact(relative_path="../bad"))
        with self.assertRaisesRegex(ValueError,"single-byte"): validate_artifact_ref(artifact(shape=[1],dtype="uint8",byte_order="little",layout="C"))
    def test_collection_rejects_duplicates(self):
        with self.assertRaisesRegex(ValueError,"duplicate"): validate_artifact_collection([artifact(),artifact()])
    def test_provenance_rejects_missing_parent_and_cycle(self):
        with self.assertRaisesRegex(ValueError,"absent"):
            value=provenance()
            value["producers"][0]["parent_ids"]=["missing"]
            validate_provenance(value)
        value=provenance()
        value["producers"][0]["parent_ids"]=["fixture.algorithm"]
        with self.assertRaisesRegex(ValueError,"cycle"):
            validate_provenance(value)
    def test_provenance_enforces_schema_and_strict_producer_fields(self):
        missing=provenance()
        del missing["request"]["schema"]
        with self.assertRaises(Exception): validate_provenance(missing)
        future=provenance()
        future["request"]["future_optional"] = True
        validate_provenance(future, producer=False)
        with self.assertRaisesRegex(ValueError,"provenance request"):
            validate_provenance(future)
    def test_provenance_requires_every_core_producer_kind(self):
        missing=provenance()
        missing["producers"][-1]["kind"]="comparator"
        with self.assertRaisesRegex(ValueError,"required producer kind"):
            validate_provenance(missing)
        extra=provenance()
        extra["producers"].append({"id":"fixture.comparator","kind":"comparator","name":"fixture","version":"1","commit":None,"build_profile":None,"dirty":False,"bundle_hash":None,"parent_ids":["fixture.algorithm"]})
        validate_provenance(extra)
    def test_pybert_and_com_mappings_are_explicit_and_immutable(self):
        domain={"name":"trace","schema":"pybert.trace.v1","relativePath":"artifacts/trace.json","mimeType":"application/json","sha256":"b"*64,"byteLength":2}
        original=copy.deepcopy(domain)
        mapped=map_pybert_artifact_ref(domain,producer="fixture.adapter",role="trace")
        self.assertEqual(domain,original)
        self.assertEqual(mapped["content_schema"],"pybert.trace.v1")
        self.assertEqual(mapped["extensions"]["pybert.artifact-ref-v1"]["artifact"],domain)
        com=map_com_artifact({"relative_path":"artifacts/com.bin","sha256":"c"*64,"byte_length":3},content_schema="com.result.v1",mime_type="application/octet-stream",producer="fixture.adapter",role="domain_result")
        self.assertEqual(com["content_schema"],"com.result.v1")
        with self.assertRaisesRegex(ValueError,"incomplete"):
            map_com_artifact({},content_schema="com.result.v1",mime_type="application/octet-stream",producer="fixture.adapter",role="domain_result")
if __name__=="__main__": unittest.main()
