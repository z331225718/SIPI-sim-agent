from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import yaml

import verify_p3c_prbs9_impulse_candidate_bridge as gate


ROOT = Path(__file__).resolve().parents[1]


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-impulse-candidate-bridge.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document) -> int:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            original = gate.DEFAULT
            gate.DEFAULT = path
            try:
                return gate.main()
            finally:
                gate.DEFAULT = original

    def test_baseline(self) -> None:
        self.assertEqual(self.verify(self.document), 0)

    def test_no_unauthorized_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["gates"]["candidate_waveform_generated"] = True
        self.assertEqual(self.verify(document), 1)


if __name__ == "__main__":
    unittest.main()
