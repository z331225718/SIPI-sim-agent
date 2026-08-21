from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_01_disposition",
    ROOT / "tools/verify_p4a_01_selected_ibis_truncation_disposition.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def stage(manifest: dict | None = None, asset: bytes | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    for source in (GATE.AUDIT, GATE.ASSET):
        target = root / source.relative_to(GATE.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    manifest = manifest or GATE.load_yaml(GATE.MANIFEST)
    target = root / GATE.MANIFEST.relative_to(GATE.ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    if asset is not None:
        (root / GATE.ASSET.relative_to(GATE.ROOT)).write_bytes(asset)
    return root


class SelectedIbisDispositionTests(unittest.TestCase):
    def test_current_exact_prefix_disposition_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_byte_count"], 1_922_075)

    def test_tracked_byte_mutation_fails_closed(self) -> None:
        data = bytearray(GATE.ASSET.read_bytes())
        data[100] ^= 1
        root = stage(asset=bytes(data))
        with self.assertRaisesRegex(GATE.DispositionError, "tracked_identity_drift"):
            GATE.validate(root)

    def test_official_suffix_mutation_fails_closed(self) -> None:
        data = bytearray(GATE.OFFICIAL_SOURCE.read_bytes())
        data[-10] ^= 1
        with tempfile.NamedTemporaryFile(delete=False) as temporary:
            temporary.write(data)
            path = Path(temporary.name)
        with self.assertRaisesRegex(GATE.DispositionError, "official_identity_drift"):
            GATE.validate(official_source=path)

    def test_audit_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.DispositionError, "audit_hash_drift"):
            GATE.validate(stage(manifest=manifest))

    def test_promotion_or_rights_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["rights_boundary"]["product_fixture"] = True
        with self.assertRaisesRegex(GATE.DispositionError, "rights_boundary_drift"):
            GATE.validate(stage(manifest=manifest))


if __name__ == "__main__":
    unittest.main()
