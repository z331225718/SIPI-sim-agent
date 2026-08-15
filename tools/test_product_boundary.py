from __future__ import annotations

import copy
import sys
import tempfile
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_product_boundary import _load_document, _paths_sha256, materialize_inventory, tracked_paths, verify_document, write_inventory


def document() -> dict:
    rules = [
        {
            "id": "product",
            "include": ["LICENSE", "src/**"],
            "class": "product_candidate",
            "license": "MIT",
            "provenance": "project_authored",
            "distribution": "product",
            "owner": "release",
        },
        {
            "id": "oracle",
            "include": ["fixtures/**"],
            "class": "oracle_only",
            "license": "LicenseRef-Fixture",
            "provenance": "external",
            "distribution": "non-distributed",
            "owner": "acceptance",
        },
    ]
    paths = ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"]
    base = {"schema": "sipi.product-boundary.v1", "status": "provisional", "rules": rules}
    entries, blockers = materialize_inventory(base, paths)
    assert not blockers
    base["inventory"] = {
        "source": "git_ls_files",
        "tracked_paths_sha256": _paths_sha256(paths),
        "entries": entries,
    }
    return base


class ProductBoundaryTests(unittest.TestCase):
    def test_current_manifest_is_complete(self) -> None:
        report = verify_document(_load_document(ROOT / "product-boundary.v1.yaml"), tracked_paths(ROOT))
        self.assertTrue(report["valid"], report["blockers"])

    def test_inventory_writer_uses_canonical_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "product-boundary.v1.yaml"
            path.write_bytes((ROOT / "product-boundary.v1.yaml").read_bytes())
            write_inventory(path, ROOT)
            self.assertNotIn(b"\r\n", path.read_bytes())

    def test_complete_inventory_is_valid(self) -> None:
        paths = ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"]
        report = verify_document(document(), paths)
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["product_candidate_count"], 2)

    def test_unclassified_and_ambiguous_paths_fail_closed(self) -> None:
        paths = ["LICENSE", "fixtures/legacy.bin", "src/lib.rs", "new.rs"]
        report = verify_document(document(), paths)
        self.assertFalse(report["valid"])
        self.assertTrue(any("unclassified" in item for item in report["blockers"]))

        ambiguous = document()
        ambiguous["rules"].append(copy.deepcopy(ambiguous["rules"][0]))
        ambiguous["rules"][-1]["id"] = "product-duplicate"
        report = verify_document(ambiguous, ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("ambiguous" in item for item in report["blockers"]))

    def test_stale_inventory_and_unsafe_paths_fail_closed(self) -> None:
        report = verify_document(document(), ["LICENSE", "fixtures/legacy.bin", "src/lib.rs", "src/new.rs"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("stale" in item for item in report["blockers"]))

        report = verify_document(document(), ["LICENSE", "fixtures/legacy.bin", "../src/lib.rs"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("unsafe" in item for item in report["blockers"]))

    def test_product_provenance_and_release_mode_fail_closed(self) -> None:
        invalid = document()
        invalid["rules"][0]["provenance"] = "external"
        report = verify_document(invalid, ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("not promotable" in item for item in report["blockers"]))

        report = verify_document(document(), ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"], release=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot authorize a release" in item for item in report["blockers"]))

    def test_generated_rule_and_windows_user_path_fail_closed(self) -> None:
        invalid = document()
        invalid["rules"].append(
            {
                "id": "generated",
                "include": ["generated/**"],
                "class": "generated",
                "license": "MIT",
                "provenance": "generated",
                "distribution": "non-distributed",
                "owner": "release",
            }
        )
        report = verify_document(invalid, ["LICENSE", "fixtures/legacy.bin", "src/lib.rs"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("generated rule missing" in item for item in report["blockers"]))

        report = verify_document(document(), ["LICENSE", "fixtures/legacy.bin", "C:/Users/user/private.bin"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("unsafe" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
