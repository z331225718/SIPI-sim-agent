import copy, importlib.util, tempfile, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", Path(__file__).with_name("verify_com_tp0v_current_asset_v2.py")); gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
class GateTests(unittest.TestCase):
    def setUp(self): self.doc = gate.load(gate.MANIFEST)
    def reject(self, mutate):
        doc = copy.deepcopy(self.doc); mutate(doc)
        with self.assertRaises(ValueError): gate.validate(doc)
    def test_valid_prep(self): gate.validate(self.doc)
    def test_candidate_binding_rejected_before_clean_commit(self): self.reject(lambda d: d["candidate"].update(commit="0" * 40))
    def test_vector_resampling_rejected(self): self.reject(lambda d: d["comparison"].update(prohibited=[]))
    def test_warning_parity_claim_rejected(self): self.reject(lambda d: d["comparison"]["anti_causal_warning"].update(source_warning_equivalent=True))
    def test_performance_reference_only_rejected(self): self.reject(lambda d: d["performance_gate"].update(required=False))
    def test_scalar_surface_shrink_rejected(self): self.reject(lambda d: d["comparison"].update(scalar_surface=d["comparison"]["scalar_surface"][:-1]))
    def test_repeat_matrix_shrink_rejected(self): self.reject(lambda d: d.update(replays=d["replays"][:-1]))
    def test_runner_hash_drift_rejected(self): self.reject(lambda d: d["tools"]["runner"].update(sha256="0" * 64))
    def test_prep_parent_drift_rejected(self): self.reject(lambda d: d["prep_harness_commit"].update(parent="0" * 40))
    def test_live_prep_receipt(self): gate.validate_prep_commit(self.doc, "2f5b4d99a4a567e9ecf2938c0e90f20e6190c181")
if __name__ == "__main__": unittest.main()
