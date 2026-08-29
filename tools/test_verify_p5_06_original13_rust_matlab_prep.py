import copy
import math
import unittest
from pathlib import Path

from tools.run_p5_06_original13_rust_matlab_prep import ABS_TOLERANCE, PrepError, array_contract, scalar_equal
from tools import verify_p5_06_original13_rust_matlab_prep as gate

UPSTREAM = Path(r"C:\Users\z3312\code\COM")

def diagnostic():
    assets = [
        {"kind": "channel", "role": role, "path": f"fixtures/synthetic/{role.lower()}.s4p", "bytes": index + 1, "sha256": f"{index + 1:064x}"}
        for index, role in enumerate(("THRU", "FEXT", "NEXT"))
    ]
    return {"schema": "sipi.p5-06.original13-future-diagnostic.v1", "status": gate.STATUS, "runs": [{"implementation": role, "root_id": f"root-{index}", "run_id": f"run-{index}", "nonce": f"{index + 10:064x}", "report_sha256": f"{index + 20:064x}"} for index, role in enumerate(("matlab", "matlab", "rust", "rust"))], "assets": assets, "case_order": list(range(28)), "checkpoints": [{"name": name, "status": "diagnostic_unset_tolerance"} for name in gate.CHECKPOINTS], "instrumentation": {"instrumented_uninstrumented_final_surface_equivalent": False, "acceptance_blocked_until_equivalent": True}, "historical_python_pass_is_rust_acceptance": False, "acceptance": False}

class PrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.document = gate.load()
    def reject_doc(self, mutate):
        document = copy.deepcopy(self.document); mutate(document)
        with self.assertRaises((gate.VerificationError, PrepError)): gate.validate(document, UPSTREAM)
    def reject_future(self, mutate):
        bundle = diagnostic(); mutate(bundle)
        with self.assertRaises(gate.VerificationError): gate.validate_future_diagnostic(bundle)
    def test_baseline(self):
        self.assertEqual(gate.validate(copy.deepcopy(self.document), UPSTREAM), {"valid": True, "status": gate.STATUS, "workbooks": 13, "cases": 28, "scalar_slots": 303})
        gate.validate_future_diagnostic(diagnostic())
    def test_scalar_policy(self):
        self.assertTrue(scalar_equal(1.0, 1.0 + 0.5 * ABS_TOLERANCE))
        self.assertFalse(scalar_equal(1.0, 1.0 + 1.01e-9))
        self.assertTrue(scalar_equal(math.inf, math.inf)); self.assertFalse(scalar_equal(math.inf, -math.inf))
        self.assertFalse(scalar_equal(math.nan, math.nan)); self.assertTrue(scalar_equal(math.nan, math.nan, True))
    def test_array_policy(self):
        value = {"shape": [2], "dtype": "f64", "order": "C", "axis": "sample", "values": [1.0, 2.0]}
        self.assertEqual(array_contract(value, copy.deepcopy(value), None), "diagnostic_unset_tolerance")
        for key, replacement in (("shape", [1, 2]), ("dtype", "f32"), ("order", "F"), ("axis", "frequency")):
            other = copy.deepcopy(value); other[key] = replacement
            with self.assertRaises(PrepError): array_contract(value, other, None)
    def test_case_or_role_swap_and_missing_checkpoint(self):
        self.reject_future(lambda b: b["runs"].__setitem__(0, {**b["runs"][0], "implementation": "rust"}))
        self.reject_future(lambda b: b["case_order"].__setitem__(0, 1))
        self.reject_future(lambda b: b["assets"].reverse())
        self.reject_future(lambda b: b["checkpoints"].pop())
    def test_nan_inf_wildcard_and_axis_drift(self):
        bundle = diagnostic(); bundle["unexpected"] = float("nan")
        with self.assertRaises(gate.VerificationError): gate.validate_future_diagnostic(bundle)
        self.assertFalse(scalar_equal(math.inf, 0.0)); self.assertFalse(scalar_equal(-math.inf, math.inf))
    def test_asset_nonce_and_absolute_path(self):
        self.reject_future(lambda b: b["assets"][0].__setitem__("sha256", "0" * 63))
        self.reject_future(lambda b: b["runs"][1].__setitem__("nonce", b["runs"][0]["nonce"]))
        self.reject_future(lambda b: b["assets"][0].__setitem__("path", r"C:\secret\asset.s4p"))
    def test_instrumentation_and_historical_pass_cannot_promote(self):
        self.reject_future(lambda b: b["instrumentation"].__setitem__("instrumented_uninstrumented_final_surface_equivalent", True))
        self.reject_future(lambda b: b.__setitem__("historical_python_pass_is_rust_acceptance", True))
        self.reject_future(lambda b: b.__setitem__("acceptance", True))
    def test_contract_mutations(self):
        self.reject_doc(lambda d: d["corpus_inventory"]["matrix"].__setitem__("scalar_slot_count", 302))
        self.reject_doc(lambda d: d["stage1_contract"].__setitem__("finite_absolute_tolerance", 1e-6))
        self.reject_doc(lambda d: d["stage1_contract"].__setitem__("matlab_repeat_absolute_tolerance", 1e-9))
        self.reject_doc(lambda d: d["stage2_checkpoint_contract"].__setitem__("array_tolerances", 1e-9))
        self.reject_doc(lambda d: d["supersession"].__setitem__("does_not_close_p5_06", False))

if __name__ == "__main__": unittest.main()
