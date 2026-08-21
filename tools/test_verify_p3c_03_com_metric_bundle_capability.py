from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_03_com_metric_bundle_capability as GATE


class P3C03ComMetricBundleCapabilityTests(unittest.TestCase):
    def _mutate(self, mutation) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        mutation(document)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C03BundleError):
                    GATE.validate(ROOT)

    def test_current_record_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["metric_count"], 3)
        self.assertFalse(result["main_item_closed"])

    def test_rejects_icn_substitution(self) -> None:
        self._mutate(lambda value: value["substitution_guard"].update(icn_to_td_iln_alias=True))

    def test_rejects_default_tolerance(self) -> None:
        self._mutate(lambda value: value["implementation"].update(default_tolerance=0.01))

    def test_rejects_main_item_promotion(self) -> None:
        self._mutate(lambda value: value["scope"].update(main_item_closed=True))

    def test_rejects_source_hash_mutation(self) -> None:
        self._mutate(lambda value: value["implementation"]["source"].update(sha256="0" * 64))


if __name__ == "__main__":
    unittest.main()
