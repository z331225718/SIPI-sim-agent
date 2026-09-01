"""Focused mutations for the current TDILN replay acceptance."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import verify_p5_06_tdiln_array_b9 as subject
except ImportError:
    import verify_p5_06_tdiln_array_b9 as subject


ROOT = Path(__file__).resolve().parents[1]


class TdIlnB9Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads((ROOT / subject.MANIFEST).read_text(encoding="utf-8"))

    def reject(self, document: dict[str, object]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            required = [subject.MANIFEST, *(path for path, _ in subject.ARTIFACTS.values()), self.document["audit"]["path"]]
            for relative in required:
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            (root / subject.MANIFEST).write_text(json.dumps(document), encoding="utf-8", newline="\n")
            with self.assertRaises(subject.VerificationError):
                subject.verify(root)

    def test_live_record_is_valid(self) -> None:
        self.assertEqual(subject.verify(ROOT)["valid"], "true")

    def test_candidate_drift_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["scope"]["candidate"]["commit"] = "0" * 40
        self.reject(changed)

    def test_speed_gate_relaxation_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["gates"]["total_rust_not_slower"] = False
        self.reject(changed)

    def test_artifact_replacement_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["artifacts"]["replay_01"]["sha256"] = "0" * 64
        self.reject(changed)

    def test_claim_escalation_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["claims"]["full_result_graph"] = True
        self.reject(changed)


if __name__ == "__main__":
    unittest.main()
