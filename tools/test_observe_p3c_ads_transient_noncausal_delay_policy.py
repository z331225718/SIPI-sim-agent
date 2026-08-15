from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_delay_policy", ROOT / "tools" / "observe_p3c_ads_transient_noncausal_delay_policy.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AdsTransientNoncausalDelayPolicyTests(unittest.TestCase):
    def test_documentation_requires_all_exact_policy_fragments(self) -> None:
        document = "\n".join(MODULE.REQUIRED_DOC_FRAGMENTS).encode("utf-8")
        MODULE.observe_documentation(document)
        for fragment in MODULE.REQUIRED_DOC_FRAGMENTS:
            with self.subTest(fragment=fragment):
                with self.assertRaisesRegex(MODULE.ObservationError, "documentation_surface"):
                    MODULE.observe_documentation(document.replace(fragment.encode("utf-8"), b""))

    def test_fixed_netlist_requires_explicit_grid_and_no_override(self) -> None:
        netlist = " ".join(("ImpMaxFreq=40000000000 Hz", "ImpDeltaFreq=39062500 Hz", "ImpMode=1", "ImpEnforcePassivity=yes", "OutputAllPoints=yes"))
        MODULE.observe_fixed_pwl_netlist(netlist)
        with self.assertRaisesRegex(MODULE.ObservationError, "noncausal_length_override"):
            MODULE.observe_fixed_pwl_netlist(netlist + " ImpNoncausalLength=32")
        with self.assertRaisesRegex(MODULE.ObservationError, "netlist_policy"):
            MODULE.observe_fixed_pwl_netlist(netlist.replace("ImpMode=1", ""))

    def test_product_contract_rejects_missing_no_delay_controls(self) -> None:
        contract = b"delay_extraction_implemented: false\ncaller_overrides: prohibited\nnot delay extraction\n"
        MODULE.observe_product_contract(contract)
        with self.assertRaisesRegex(MODULE.ObservationError, "product_no_delay"):
            MODULE.observe_product_contract(contract.replace(b"not delay extraction", b""))


if __name__ == "__main__":
    unittest.main()
