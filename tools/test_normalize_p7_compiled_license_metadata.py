from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("normalize", ROOT / "tools" / "normalize_p7_compiled_license_metadata.py")
assert SPEC and SPEC.loader
NORMALIZE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(NORMALIZE)

class NormalizeTests(unittest.TestCase):
    def test_record_preserves_literal_without_spdx_rewrite(self) -> None:
        record = NORMALIZE._record({"identity":"registry:demo@1#" + "a" * 64,"kind":"registry","name":"demo","version":"1","manifest_sha256":"b" * 64,"literal_license":"MIT/Apache-2.0","literal_license_file":None,"license_materials":[],"license_concluded":"NOASSERTION","notice_requirement":"not_evaluated"})
        self.assertEqual(record["literal_license"], "MIT/Apache-2.0")
        self.assertEqual(record["category"], "declared_string_unparsed")

    def test_license_file_without_bounded_material_is_a_gap(self) -> None:
        record = NORMALIZE._record({"identity":"registry:demo@1#" + "a" * 64,"kind":"registry","name":"demo","version":"1","manifest_sha256":"b" * 64,"literal_license":None,"literal_license_file":"COPYING","license_materials":[],"license_concluded":"NOASSERTION","notice_requirement":"not_evaluated"})
        self.assertTrue(record["observer_material_coverage_gap"])

if __name__ == "__main__": unittest.main()
