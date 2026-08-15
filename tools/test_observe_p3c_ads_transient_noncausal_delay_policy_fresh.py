from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_delay_fresh", ROOT / "tools" / "observe_p3c_ads_transient_noncausal_delay_policy_fresh.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AdsTransientNoncausalDelayFreshCustodyTests(unittest.TestCase):
    def child(self) -> dict[str, object]:
        return {
            "schema": MODULE.CHILD_SCHEMA,
            "custody": "external_only_hash_only",
            "runtime_invoked": False,
            "conclusion": {"selected_run_delay_action_observed": False, "delay_seconds_derived": False},
        }

    def test_accepts_nonpromoting_child_result(self) -> None:
        self.assertEqual(MODULE.assert_child_result(self.child()), self.child())

    def test_rejects_runtime_delay_or_path_leaks(self) -> None:
        for mutation in (
            lambda value: value.__setitem__("runtime_invoked", True),
            lambda value: value["conclusion"].__setitem__("selected_run_delay_action_observed", True),
            lambda value: value.__setitem__("path", "C:\\\\external"),
        ):
            with self.subTest(mutation=mutation):
                value = self.child()
                mutation(value)
                with self.assertRaises(MODULE.FreshObservationError):
                    MODULE.assert_child_result(value)

    def test_rejects_invalid_clean_archive_identifier(self) -> None:
        with self.assertRaisesRegex(MODULE.FreshObservationError, "commit_invalid"):
            MODULE.clean_archive_tree("not-a-commit")


if __name__ == "__main__":
    unittest.main()
