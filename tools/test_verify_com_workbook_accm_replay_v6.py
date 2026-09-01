from __future__ import annotations
import shutil
import tempfile
import unittest
from pathlib import Path
import yaml
from tools import verify_com_workbook_accm_replay_v6 as verifier


class ReplayV6VerifierTests(unittest.TestCase):
    def clone(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp()) / "repo"
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        shutil.copytree(verifier.ROOT / "docs", root / "docs")
        shutil.copytree(verifier.ROOT / "tools", root / "tools")
        return root, root / "docs/baselines/com-workbook-accm-replay-v6.manifest.yaml"

    def test_valid_record(self) -> None:
        self.assertTrue(verifier.validate()["valid"])

    def test_hash_status_and_freshness_mutations_fail(self) -> None:
        for mutate in (lambda d: d["runs"][0].__setitem__("sha256", "0" * 64), lambda d: d.__setitem__("status", "blocked"), lambda d: d["runs"][1].__setitem__("nonce", d["runs"][0]["nonce"])):
            root, path = self.clone()
            data = yaml.safe_load(path.read_text())
            mutate(data)
            path.write_text(yaml.safe_dump(data, sort_keys=False))
            with self.assertRaises(verifier.VerificationError):
                verifier.validate(path, root=root)


if __name__ == "__main__":
    unittest.main()
