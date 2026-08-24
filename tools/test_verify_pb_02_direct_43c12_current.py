import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_02_direct_43c12_current as verifier  # noqa: E402


class Pb02CurrentEvidenceTests(unittest.TestCase):
    def _manifest(self):
        return json.loads(verifier.MANIFEST.read_text(encoding="utf-8"))

    def _isolated_tree(self, temporary):
        root = Path(temporary)
        manifest_rel = "docs/baselines/pb-02-direct-43c12-current.v2.yaml"
        paths = [
            manifest_rel,
            "docs/baselines/pb-02-direct-43c12-current-run-01.json",
            "docs/baselines/pb-02-direct-43c12-current-run-02.json",
            "docs/baselines/pb-02-direct-43c12-current-aggregate.json",
            "docs/baselines/audits/2026-08-24-pb-02-direct-43c12.v2.json",
            "tools/run_pb_02_direct_replay.py",
            "tools/aggregate_pb_02_direct_replay.py",
            "tools/verify_pb_02_direct_43c12_current.py",
            "tools/test_verify_pb_02_direct_43c12_current.py",
        ]
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        return root, root / manifest_rel

    def _verify_mutated_copy(self, mutate):
        with tempfile.TemporaryDirectory() as temporary:
            root, manifest_path = self._isolated_tree(temporary)
            mutate(root)
            with mock.patch.object(verifier, "ROOT", root), mock.patch.object(verifier, "MANIFEST", manifest_path):
                self.assertTrue(verifier.verify(manifest_path))

    def _refresh_report_graph(self, root):
        manifest_path = root / "docs/baselines/pb-02-direct-43c12-current.v2.yaml"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reports = []
        for index in (1, 2):
            path = root / f"docs/baselines/pb-02-direct-43c12-current-run-0{index}.json"
            raw = path.read_bytes()
            document = json.loads(raw)
            reports.append((path, raw, document))
            reference = manifest["replay_policy"]["reports"][index - 1]
            reference["sha256"] = __import__("hashlib").sha256(raw).hexdigest()
            reference["run_id"] = document["run_id"]
            reference["fresh_run_nonce"] = document["fresh_run_nonce"]
        aggregate_path = root / verifier.AGGREGATE_PATH
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
        for index, (_, raw, document) in enumerate(reports):
            aggregate["reports"][index]["sha256"] = __import__("hashlib").sha256(raw).hexdigest()
            aggregate["reports"][index]["run_id"] = document["run_id"]
            aggregate["reports"][index]["fresh_run_nonce"] = document["fresh_run_nonce"]
        aggregate_raw = json.dumps(aggregate, sort_keys=True, indent=2).encode()
        aggregate_path.write_bytes(aggregate_raw)
        manifest["replay_policy"]["aggregate"]["sha256"] = __import__("hashlib").sha256(aggregate_raw).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _refresh_full_graph(self, root):
        self._refresh_report_graph(root)
        manifest_path = root / "docs/baselines/pb-02-direct-43c12-current.v2.yaml"
        audit_path = root / verifier.AUDIT_PATH
        aggregate_path = root / verifier.AGGREGATE_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
        aggregate["candidate"] = json.loads((root / verifier.REPORT_PATHS[0]).read_text(encoding="utf-8"))["candidate"]
        aggregate_raw = json.dumps(aggregate, sort_keys=True, indent=2).encode()
        aggregate_path.write_bytes(aggregate_raw)
        aggregate_sha = __import__("hashlib").sha256(aggregate_raw).hexdigest()
        manifest["replay_policy"]["aggregate"]["sha256"] = aggregate_sha
        audit["exact_file_bindings"]["report_01"] = manifest["replay_policy"]["reports"][0]
        audit["exact_file_bindings"]["report_02"] = manifest["replay_policy"]["reports"][1]
        audit["exact_file_bindings"]["aggregate"] = manifest["replay_policy"]["aggregate"]
        audit["exact_file_bindings"]["manifest"]["binding_sha256"] = "<binding>"
        manifest["audit"]["sha256"] = "<audit-sha256>"
        binding_copy = json.loads(json.dumps(manifest))
        binding_copy["audit"]["sha256"] = "<audit-sha256>"
        binding_sha = __import__("hashlib").sha256(json.dumps(binding_copy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        audit["manifest_binding_sha256"] = binding_sha
        audit["exact_file_bindings"]["manifest"]["binding_sha256"] = binding_sha
        audit_raw = json.dumps(audit, sort_keys=True, indent=2).encode()
        audit_path.write_bytes(audit_raw)
        manifest["audit"]["sha256"] = __import__("hashlib").sha256(audit_raw).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_current_evidence_passes(self):
        self.assertEqual(verifier.verify(), [])

    def test_policy_path_or_promotion_mutation_blocks(self):
        manifest = self._manifest()
        manifest["replay_policy"]["reports"][0]["path"] = "evil.json"
        manifest["replay_policy"]["reports"][0]["sha256"] = "0" * 64
        manifest["replay_policy"]["release_ready"] = True
        manifest["non_claims"] = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verifier.verify(path))

    def test_logical_shape_exit_and_aggregate_mutation_blocks(self):
        def mutate(root):
            report = root / verifier.REPORT_PATHS[0]
            value = json.loads(report.read_text(encoding="utf-8"))
            value["replay"]["candidate"]["artifacts"]["arrays"]["logical_members"][verifier.EXPECTED_MEMBER_NAMES[0]]["count"] = 99
            report.write_text(json.dumps(value), encoding="utf-8")

        self._verify_mutated_copy(mutate)

    def test_aggregate_schema_and_audit_anchor_mutations_block(self):
        def mutate(root):
            aggregate = root / verifier.AGGREGATE_PATH
            value = json.loads(aggregate.read_text(encoding="utf-8"))
            value.pop("blockers")
            aggregate.write_text(json.dumps(value), encoding="utf-8")
            audit = root / verifier.AUDIT_PATH
            value = json.loads(audit.read_text(encoding="utf-8"))
            value["source_map"] = "release_accepted"
            audit.write_text(json.dumps(value), encoding="utf-8")

        self._verify_mutated_copy(mutate)

    def test_harness_path_mutation_blocks_even_with_synchronized_file_hash(self):
        def mutate(root):
            evil = root / "tools" / "evil.py"
            evil.write_text("# replacement\n", encoding="utf-8")
            manifest_path = root / "docs/baselines/pb-02-direct-43c12-current.v2.yaml"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["harness"]["runner"] = {"path": "tools/evil.py", "sha256": __import__("hashlib").sha256(evil.read_bytes()).hexdigest()}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        self._verify_mutated_copy(mutate)

    def test_run_nonce_and_report_graph_coordinated_mutation_blocks(self):
        def mutate(root):
            for index in (1, 2):
                path = root / f"docs/baselines/pb-02-direct-43c12-current-run-0{index}.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["run_id"] = "same-run"
                value["fresh_run_nonce"] = "a" * 64
                path.write_text(json.dumps(value), encoding="utf-8")
            self._refresh_full_graph(root)

        self._verify_mutated_copy(mutate)

    def test_logical_member_digest_mutation_blocks_after_graph_refresh(self):
        def mutate(root):
            for index in (1, 2):
                path = root / f"docs/baselines/pb-02-direct-43c12-current-run-0{index}.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                member = value["replay"]["candidate"]["artifacts"]["arrays"]["logical_members"][verifier.EXPECTED_MEMBER_NAMES[0]]
                member["f64_sha256"] = "f" * 64
                path.write_text(json.dumps(value), encoding="utf-8")
            self._refresh_full_graph(root)

        self._verify_mutated_copy(mutate)

    def test_inventory_canonical_drift_mutation_blocks(self):
        def mutate(root):
            for index in (1, 2):
                path = root / f"docs/baselines/pb-02-direct-43c12-current-run-0{index}.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["candidate"]["inventory"]["entries"][0]["sha256"] = "f" * 64
                path.write_text(json.dumps(value), encoding="utf-8")

        self._verify_mutated_copy(mutate)

    def test_malformed_audit_and_report_reference_block_without_throwing(self):
        manifest = self._manifest()
        manifest["audit"] = None
        manifest["replay_policy"]["reports"][0] = None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verifier.verify(path))

    def test_toolchain_absolute_path_and_nonclaim_mutations_block(self):
        def mutate(root):
            for index in (1, 2):
                path = root / f"docs/baselines/pb-02-direct-43c12-current-run-0{index}.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["toolchain"]["cargo"]["executable"] = "C:\\secret\\cargo.exe"
                value["non_claims"] = []
                path.write_text(json.dumps(value), encoding="utf-8")
            self._refresh_full_graph(root)

        self._verify_mutated_copy(mutate)

    def test_malformed_null_member_and_missing_aggregate_audit_block_without_throwing(self):
        manifest = self._manifest()
        manifest["payload"]["member_names"] = None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verifier.verify(path))
        with mock.patch.object(verifier, "AGGREGATE_PATH", "missing-aggregate.json"), mock.patch.object(verifier, "AUDIT_PATH", "missing-audit.json"):
            self.assertTrue(verifier.verify(verifier.MANIFEST))

    def test_coordinated_promotion_and_report_graph_drift_blocks(self):
        manifest = self._manifest()
        manifest["claims"]["promotion"] = True
        manifest["claims"]["external_asset_parity"] = True
        manifest["status"] = "passed"
        manifest["replay_policy"]["fresh_runs_required"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verifier.verify(path))


if __name__ == "__main__":
    unittest.main()
