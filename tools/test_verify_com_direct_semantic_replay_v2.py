import tempfile
import unittest
from pathlib import Path

import yaml

try:
    from .verify_com_direct_semantic_replay_v2 import VerificationError, verify
except ImportError:
    from verify_com_direct_semantic_replay_v2 import VerificationError, verify


ROOT = Path(__file__).resolve().parents[1]


class ComV2VerifierTests(unittest.TestCase):
    def mutate_fails(self, manifest: Path, mutate) -> None:
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_current_manifests(self) -> None:
        for mode in ("02", "04"):
            result = verify(ROOT / f"docs/baselines/com-{mode}-direct-port.v2.yaml")
            self.assertTrue(result["archive_derived_binary"])
            self.assertTrue(result["nonce_64_hex"])

    def test_candidate_commit_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-02-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["candidate"].__setitem__("commit", "0" * 40))

    def test_report_hash_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-02-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["evidence"]["reports"][0].__setitem__("sha256", "0" * 64))

    def test_custody_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-04-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["contract"].__setitem__("custody", "status_only"))

    def test_probe_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-04-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["candidate"].__setitem__("archive_sha256", "0" * 64))

    def test_verifier_binding_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-04-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["verification"].__setitem__("verifier_sha256", "0" * 64))

    def test_toolchain_binding_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-02-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["execution_binding"]["toolchain"]["cargo"].__setitem__("path_redacted", False))

    def test_binary_provenance_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-04-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["candidate"]["binary_sha256_by_run"].__setitem__(0, "0" * 64))

    def test_upstream_materialization_mutation_fails(self) -> None:
        manifest = ROOT / "docs/baselines/com-04-direct-port.v2.yaml"
        self.mutate_fails(manifest, lambda document: document["upstream"].__setitem__("runtime_executed", True))


if __name__ == "__main__":
    unittest.main()
