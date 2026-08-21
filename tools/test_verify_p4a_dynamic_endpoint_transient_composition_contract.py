from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_dynamic_endpoint_contract",
    ROOT / "tools" / "verify_p4a_dynamic_endpoint_transient_composition_contract.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-dynamic-endpoint-transient-composition-contract.v1.yaml"


class DynamicEndpointContractTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_current_contract_is_valid_but_t12_is_blocked(self) -> None:
        result = GATE.validate_contract(self.document())
        self.assertFalse(result["t12_admission"])
        self.assertFalse(result["promotion_eligible"])
        self.assertIn("ibis_constitutive_semantics", result["confirmed_fields"])
        self.assertIn("tolerance", result["blocked_fields"])

    def test_reference_supply_and_initial_state_mutations_fail_closed(self) -> None:
        document = self.document()
        document["reference_node"]["implicit_global_ground"] = "allowed"
        with self.assertRaisesRegex(GATE.ContractError, "reference_node_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["supply"]["source"] = "derive_from_pvt"
        with self.assertRaisesRegex(GATE.ContractError, "supply_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["initial_state"]["inherit_p2_zero_initial_output"] = True
        with self.assertRaisesRegex(GATE.ContractError, "initial_state_invalid"):
            GATE.validate_contract(document)

    def test_integration_channel_bounds_and_tolerance_mutations_fail_closed(self) -> None:
        document = self.document()
        document["integration_timebase_output"]["integration_method"] = "backward_euler_f64"
        with self.assertRaisesRegex(GATE.ContractError, "integration_timebase_output_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["channel_return_stimulus"]["stimulus_kind"] = "pwl"
        with self.assertRaisesRegex(GATE.ContractError, "channel_return_stimulus_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["bounds"]["numeric_caps"]["output_samples"] = 4096
        with self.assertRaisesRegex(GATE.ContractError, "bounds_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["tolerance"]["external_oracle_or_parity"] = "allowed"
        with self.assertRaisesRegex(GATE.ContractError, "tolerance_invalid"):
            GATE.validate_contract(document)

    def test_constitutive_units_failure_and_promotion_mutations_fail_closed(self) -> None:
        document = self.document()
        document["ibis_constitutive_semantics"]["c_comp"]["relation"] = "C_comp_times_d_dt_V_SIG"
        with self.assertRaisesRegex(GATE.ContractError, "ibis_constitutive_semantics_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["units"]["capacitance"] = "pF"
        with self.assertRaisesRegex(GATE.ContractError, "units_invalid"):
            GATE.validate_contract(document)

        document = self.document()
        document["failure_behavior"]["general_netlist_or_spice_fallback"] = "allowed"
        with self.assertRaisesRegex(GATE.ContractError, "failure_behavior_invalid"):
            GATE.validate_contract(document)

        document = copy.deepcopy(self.document())
        document["t12_admission"]["admission"] = True
        with self.assertRaisesRegex(GATE.ContractError, "t12_admission_invalid"):
            GATE.validate_contract(document)


if __name__ == "__main__":
    unittest.main()
