import copy
import unittest

import yaml

try:
    from tools.verify_p3c_03c_com_metric_checkpoint_boundary import (
        BoundaryError,
        EVIDENCE,
        validate_document,
    )
except ModuleNotFoundError:
    from verify_p3c_03c_com_metric_checkpoint_boundary import (
        BoundaryError,
        EVIDENCE,
        validate_document,
    )


class P3C03CVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(BoundaryError):
            validate_document(document)

    def test_baseline(self):
        self.assertTrue(validate_document(self.document)["valid"])

    def test_checkpoint_alignment_mutation(self):
        self.assert_invalid(lambda doc: doc["comparison"].__setitem__("alignment_policy", "nearest"))

    def test_tolerance_mutation(self):
        self.assert_invalid(lambda doc: doc["comparison"]["owner_absolute_tolerance_db"].__setitem__("ERL_dB", 0.2))

    def test_td_iln_surface_mutation(self):
        self.assert_invalid(lambda doc: doc["implementation"].__setitem__("metrics", ["COM_dB", "ERL_dB", "ICN_mV"]))

    def test_icn_alias_mutation(self):
        self.assert_invalid(lambda doc: doc["comparison"].__setitem__("icn_alias", True))

    def test_audit_binding_mutation(self):
        self.assert_invalid(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))


if __name__ == "__main__":
    unittest.main()
