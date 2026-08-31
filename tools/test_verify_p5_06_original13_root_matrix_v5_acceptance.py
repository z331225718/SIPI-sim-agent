from __future__ import annotations

import json
import unittest

from tools.verify_p5_06_original13_root_matrix_v5_acceptance import MANIFEST, ROOT, VerificationError, verify


class AcceptanceTests(unittest.TestCase):
    def test_live_acceptance_record_is_valid(self):
        self.assertTrue(verify(ROOT)["valid"])

    def test_manifest_is_json_object(self):
        document = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(document["claims"]["public_root_route_exercised"], True)
        self.assertEqual(document["claims"]["release"], False)
        self.assertEqual(document["gates"]["s_parameter_fit"], False)
        self.assertNotEqual(VerificationError, ValueError)


if __name__ == "__main__":
    unittest.main()
