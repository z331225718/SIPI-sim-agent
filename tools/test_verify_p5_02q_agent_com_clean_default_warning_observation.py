import copy
import unittest

import yaml

try:
    from tools.verify_p5_02q_agent_com_clean_default_warning_observation import (
        EVIDENCE,
        ObservationError,
        validate_document,
    )
except ModuleNotFoundError:
    from verify_p5_02q_agent_com_clean_default_warning_observation import (
        EVIDENCE,
        ObservationError,
        validate_document,
    )


class P502QVerifierTests(unittest.TestCase):
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

    def test_payload_hash_mutation(self):
        self.assert_invalid(lambda doc: doc["runs"]["payloads"][0].__setitem__("sha256", "0" * 64))

    def test_warning_code_mutation(self):
        self.assert_invalid(lambda doc: doc["warning"].__setitem__("code", "OTHER"))

    def test_default_mutation(self):
        self.assert_invalid(lambda doc: doc["observed_values"]["materialized_parameters"].__setitem__("trunc", 129.0))

    def test_audit_binding_mutation(self):
        self.assert_invalid(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))


if __name__ == "__main__":
    unittest.main()
