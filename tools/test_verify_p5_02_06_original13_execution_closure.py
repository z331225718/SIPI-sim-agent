"""Mutations for the original-13 execution closure verifier."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import verify_p5_02_06_original13_execution_closure as subject
except ImportError:
    import verify_p5_02_06_original13_execution_closure as subject


ROOT = Path(__file__).resolve().parents[1]


class Original13ClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads((ROOT / subject.MANIFEST).read_text(encoding="utf-8"))

    def copy_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        paths = [subject.MANIFEST, self.document["audit"], *subject.ROOT_REPORTS]
        for relative, _ in subject.EXPECTED_EVIDENCE.values():
            paths.append(relative)
        paths.extend([
            "docs/baselines/p5-06-original13-root-matrix-v6-aggregate.json",
            "docs/baselines/audits/2026-09-01-p5-06-original13-root-matrix-v6-acceptance.md",
            "docs/baselines/p5-06-tdiln-array-b9-replay-01.v1.json",
            "docs/baselines/p5-06-tdiln-array-b9-replay-02.v1.json",
            "docs/baselines/p5-06-tdiln-array-b9-replay-aggregate.v1.json",
            "docs/baselines/audits/2026-09-01-p5-06w7-current-tdiln-rebind.md",
        ])
        for relative in paths:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return root

    def reject_manifest(self, changed: dict[str, object]) -> None:
        root = self.copy_root()
        try:
            (root / subject.MANIFEST).write_text(json.dumps(changed), encoding="utf-8", newline="\n")
            with self.assertRaises(subject.VerificationError):
                subject.verify(root)
        finally:
            shutil.rmtree(root)

    def test_live_record_is_valid(self) -> None:
        self.assertEqual(subject.verify(ROOT)["valid"], "true")

    def test_scope_expansion_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["scope"]["workbooks"] = 14
        self.reject_manifest(changed)

    def test_speed_gate_relaxation_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["performance"]["total_rust_not_slower"] = False
        self.reject_manifest(changed)

    def test_warning_exception_escalation_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["warning_contract"]["bounded_exception"]["source_warning_equivalent"] = True
        self.reject_manifest(changed)

    def test_evidence_digest_drift_is_rejected(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["evidence"]["tdiln_named_arrays"]["sha256"] = "0" * 64
        self.reject_manifest(changed)


if __name__ == "__main__":
    unittest.main()
