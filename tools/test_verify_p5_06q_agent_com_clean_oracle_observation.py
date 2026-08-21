import copy
import unittest

import yaml

try:
    from tools.verify_p5_06q_agent_com_clean_oracle_observation import (
        EVIDENCE,
        ObservationError,
        validate_document,
    )
except ModuleNotFoundError:
    from verify_p5_06q_agent_com_clean_oracle_observation import (
        EVIDENCE,
        ObservationError,
        validate_document,
    )


class P506QVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(ObservationError):
            validate_document(document)

    def test_baseline(self):
        self.assertTrue(validate_document(self.document)["valid"])

    def test_schema_mutation(self):
        self.assert_invalid(lambda doc: doc.__setitem__("schema", "wrong"))

    def test_hash_mutation(self):
        self.assert_invalid(lambda doc: doc["runs"]["payloads"][0].__setitem__("sha256", "0" * 64))

    def test_td_iln_alias_mutation(self):
        self.assert_invalid(lambda doc: doc["runs"]["observed_non_substitutes"]["ICN_mV"].__setitem__("allowed_as_TD_ILN_dB", True))

    def test_tolerance_mutation(self):
        self.assert_invalid(lambda doc: doc["comparison_boundary"]["owner_absolute_tolerance_db"].__setitem__("TD_ILN_dB", 0.2))

    def test_audit_binding_mutation(self):
        self.assert_invalid(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))


if __name__ == "__main__":
    unittest.main()
