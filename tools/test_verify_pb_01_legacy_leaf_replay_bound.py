import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_01_legacy_leaf_replay_bound as verifier  # noqa: E402


class Pb01LegacyLeafReplayBoundVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest_relative = Path("docs/baselines/pb-01-legacy-leaf-replay-bound.v1.yaml")
        manifest = yaml.safe_load((ROOT / self.manifest_relative).read_text(encoding="utf-8"))
        paths = [binding["path"] for binding in manifest["replays"]]
        paths += [manifest["aggregate"]["path"], manifest["audit"]["path"]]
        paths += [binding["path"] for binding in manifest["tools"].values()]
        paths.append(self.manifest_relative.as_posix())
        for relative in paths:
            source, target = ROOT / relative, self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def tearDown(self):
        self.temporary.cleanup()

    @property
    def manifest_path(self):
        return self.root / self.manifest_relative

    def load_manifest(self):
        return yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, value):
        self.manifest_path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")

    def mutate_json(self, relative, mutator):
        path = self.root / relative
        value = json.loads(path.read_text(encoding="utf-8"))
        mutator(value)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def assert_invalid(self):
        self.assertFalse(verifier.verify(self.manifest_path, self.root)["valid"])

    def rebind_report(self, manifest, index):
        binding = manifest["replays"][index]
        binding["sha256"] = verifier._sha(self.root / binding["path"])
        self.write_manifest(manifest)

    def assert_error(self, text):
        result = verifier.verify(self.manifest_path, self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any(text in error for error in result["errors"]), result["errors"])

    def test_valid(self):
        self.assertTrue(verifier.verify(self.manifest_path, self.root)["valid"])

    def test_report_content_drift(self):
        manifest = self.load_manifest()
        self.mutate_json(manifest["replays"][0]["path"], lambda value: value.update(status="blocked"))
        self.assert_invalid()

    def test_same_nonce_rejected_even_with_rebound_hashes(self):
        manifest = self.load_manifest()
        first, second = manifest["replays"]
        nonce = first["fresh_run_nonce"]
        self.mutate_json(second["path"], lambda value: value.update(fresh_run_nonce=nonce))
        second["fresh_run_nonce"] = nonce
        second["sha256"] = verifier._sha(self.root / second["path"])
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_toolchain_path_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["toolchain"]["cargo"].update(executable=r"C:\\cargo.exe"))
        report["sha256"] = verifier._sha(self.root / report["path"])
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_extra_artifact_key_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["replay"]["candidate_artifact_schema"]["array_keys"].append("ctle_out"))
        report["sha256"] = verifier._sha(self.root / report["path"])
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_open_branch_removal_rejected(self):
        manifest = self.load_manifest()
        manifest["open_branches"].remove("imported_S2P")
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_tool_hash_drift_rejected(self):
        manifest = self.load_manifest()
        manifest["tools"]["runner"]["sha256"] = "0" * 64
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_aggregate_hash_drift_rejected(self):
        manifest = self.load_manifest()
        manifest["aggregate"]["sha256"] = "0" * 64
        self.write_manifest(manifest)
        self.assert_invalid()

    def test_harness_content_hash_drift_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["harness"]["runner"].update(sha256="0" * 64))
        self.rebind_report(manifest, 0)
        self.assert_error("runner harness content hash drift")

    def test_tolerance_scale_drift_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["replay"]["comparison"]["arrays"][0].update(scale=2.0))
        self.rebind_report(manifest, 0)
        self.assert_error("comparison row tolerance contract failed")

    def test_nonfinite_comparison_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["replay"]["comparison"]["arrays"][0].update(max_abs=float("nan")))
        self.rebind_report(manifest, 0)
        self.assert_error("comparison row numeric facts malformed")

    def test_nonzero_build_exit_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["replay"]["build"].update(exit_code=1))
        self.rebind_report(manifest, 0)
        self.assert_error("candidate build facts are not successful")

    def test_missing_candidate_artifact_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["replay"]["candidate"]["artifact"].update(present=False))
        self.rebind_report(manifest, 0)
        self.assert_error("candidate process/artifact facts are not successful")

    def test_binary_reproducibility_claim_rejected(self):
        manifest = self.load_manifest()
        report = manifest["replays"][0]
        self.mutate_json(report["path"], lambda value: value["reproducibility"].update(binary_bit_reproducible=True))
        self.rebind_report(manifest, 0)
        self.assert_error("binary bit reproducibility must remain false")

    def test_aggregate_harness_drift_rejected_with_rebound_hash(self):
        manifest = self.load_manifest()
        path = manifest["aggregate"]["path"]
        self.mutate_json(path, lambda value: value["harness"]["runner"].update(sha256="0" * 64))
        manifest["aggregate"]["sha256"] = verifier._sha(self.root / path)
        self.write_manifest(manifest)
        self.assert_error("aggregate harness binding drift")

    def test_verifier_does_not_import_runner_constants(self):
        source = (ROOT / "tools/verify_pb_01_legacy_leaf_replay_bound.py").read_text(encoding="utf-8")
        self.assertNotIn("from run_pb_01_legacy_leaf_replay import", source)


if __name__ == "__main__":
    unittest.main()
