from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4b_loader_declarations", ROOT / "tools/verify_p4b_dual_ami_pe_loader_declarations.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

class LoaderDeclarationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml").read_text(encoding="utf-8"))
    def verify(self, document: dict) -> dict:
        return GATE.verify(document, hashes=set())
    def test_current_record_keeps_runtime_and_worker_blocked(self) -> None:
        result = self.verify(self.document)
        self.assertFalse(result["worker_admitted"])
        self.assertFalse(result["runtime_invoked"])
    def test_declaration_and_promotion_drift_reject(self) -> None:
        document = copy.deepcopy(self.document)
        document["dlls"]["pcie-tx-dll"]["dynamic_loader_capability_indicators"] = ["LoadLibraryW"]
        with self.assertRaisesRegex(GATE.GateError, "dll_static_declaration_drift"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["gates"]["worker_admission"] = "admitted"
        with self.assertRaisesRegex(GATE.GateError, "gate_promotion"):
            self.verify(document)
    def test_external_leak_source_drift_and_load_surface_reject(self) -> None:
        with self.assertRaisesRegex(GATE.GateError, "external_asset_or_report_leak"):
            GATE.verify(GATE.yaml.safe_load((ROOT / "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml").read_text(encoding="utf-8")), hashes={GATE.REPORT_SHA256})
        with mock.patch.object(GATE, "sha", return_value="0" * 64):
            with self.assertRaisesRegex(GATE.GateError, "p4b05b_source_drift"):
                self.verify(self.document)
        with mock.patch.object(GATE.Path, "read_text", return_value="import ctypes"):
            with self.assertRaisesRegex(GATE.GateError, "observer_binding_drift|observer_load_surface_detected"):
                self.verify(self.document)

if __name__ == "__main__": unittest.main()
