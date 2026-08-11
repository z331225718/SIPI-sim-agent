"""Focused safety tests for the external-only dual-AMI observer."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dual_ami_observer", ROOT / "tools/observe_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class DualAmiObserverTests(unittest.TestCase):
    def test_ibis_binding_must_match_exact_allowlist(self) -> None:
        data = b"""[IBIS Ver] 5.1\n[Model] pcie_tx\nExecutable Windows_mingw64-g++_64 wrong.dll ctspcie_tx_gen5.ami\n[Model] pcie_rx\nExecutable Windows_mingw64-g++_64 ctspcie_rx_win64.dll ctspcie_rx_gen5.ami\n"""
        with self.assertRaisesRegex(OBSERVER.ObservationError, "bindings_do_not_match_allowlist"):
            OBSERVER.ibis_bindings(data)

    def test_materialize_rejects_source_change_after_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name in OBSERVER.ASSETS.values():
                (source / name).write_bytes(b"initial")
            original_copyfile = OBSERVER.shutil.copyfile

            def changing_copyfile(origin: Path, destination: Path, *args: object, **kwargs: object) -> Path:
                result = original_copyfile(origin, destination, *args, **kwargs)
                origin.write_bytes(b"changed")
                return result

            with mock.patch.object(OBSERVER.shutil, "copyfile", side_effect=changing_copyfile):
                with self.assertRaisesRegex(OBSERVER.ObservationError, "changed_during_materialization"):
                    OBSERVER.materialize(source)

    def test_main_rejects_product_report_and_invalid_expected_hash(self) -> None:
        product_report = ROOT / "p4b-observer-report-must-not-exist.json"
        self.assertEqual(OBSERVER.main(["--external-root", str(ROOT), "--report", str(product_report)]), 2)
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            with mock.patch.object(OBSERVER, "observe", return_value={"status": "external_only_identity_observed_worker_blocked"}):
                self.assertEqual(
                    OBSERVER.main(["--external-root", str(ROOT), "--report", str(report), "--expected-report-sha256", "invalid"]),
                    2,
                )
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
