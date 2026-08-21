from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_01_rights", ROOT / "tools/verify_p4a_01_official_object_rights_recheck.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def stage(manifest: dict | None = None, include_complete_asset: bool = False) -> Path:
    root = Path(tempfile.mkdtemp())
    for source in (GATE.PREDECESSOR, GATE.AUDIT):
        target = root / source.relative_to(GATE.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = root / GATE.MANIFEST.relative_to(GATE.ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(manifest or GATE.load_yaml(GATE.MANIFEST), sort_keys=False), encoding="utf-8")
    if include_complete_asset:
        asset = root / "fixtures/ibis/complete.ibs"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(GATE.OFFICIAL_SOURCE.read_bytes())
    return root


class OfficialObjectRightsRecheckTests(unittest.TestCase):
    def test_current_external_only_recheck_is_valid(self) -> None:
        self.assertTrue(GATE.validate()["valid"])

    def test_external_byte_mutation_fails_closed(self) -> None:
        data = bytearray(GATE.OFFICIAL_SOURCE.read_bytes())
        data[-8] ^= 1
        with tempfile.NamedTemporaryFile(delete=False) as temporary:
            temporary.write(data)
            path = Path(temporary.name)
        with self.assertRaisesRegex(GATE.RightsRecheckError, "official_identity_drift"):
            GATE.validate(official_source=path)

    def test_notice_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["embedded_notices"]["copyright_block"]["normalized_text_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.RightsRecheckError, "copyright_block_drift"):
            GATE.validate(stage(manifest))

    def test_redistribution_claim_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["rights_disposition"]["redistribution_authorized"] = True
        with self.assertRaisesRegex(GATE.RightsRecheckError, "rights_boundary_drift"):
            GATE.validate(stage(manifest))

    def test_complete_bytes_in_worktree_fail_closed(self) -> None:
        with self.assertRaisesRegex(GATE.RightsRecheckError, "complete_official_bytes_present_in_worktree"):
            GATE.validate(stage(include_complete_asset=True))


if __name__ == "__main__":
    unittest.main()
