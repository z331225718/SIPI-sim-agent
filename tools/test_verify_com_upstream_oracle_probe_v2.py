import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .verify_com_upstream_oracle_probe_v2 import ROOT, VerificationError, verify
except ImportError:
    from verify_com_upstream_oracle_probe_v2 import ROOT, VerificationError, verify


class UpstreamProbeVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregate = ROOT / "docs/baselines/com-02-upstream-runtime-oracle-v2-aggregate.json"
        self.document = json.loads(self.aggregate.read_text(encoding="utf-8"))

    def verify_mutation(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aggregate.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path, "com-02")

    def test_current_evidence(self) -> None:
        result = verify(self.aggregate, "com-02")
        self.assertFalse(result["full_run_numeric_parity"])

    def test_upstream_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value["upstream"].update(commit="0" * 40))

    def test_overclaim_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value.update(status="numeric_parity"))

    def test_payload_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value["portable_leaf_numeric_payload"].update(mmse={}))

    def test_absolute_path_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value["reports"][0].update(path="C:\\secret.json"))

    def test_timeout_gate_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value["execution_binding"].update(entrypoint_timeout_seconds=30))

    def test_toolchain_mutation_fails(self) -> None:
        self.verify_mutation(lambda value: value["execution_binding"]["toolchain"].update(path_redacted=False))



if __name__ == "__main__":
    unittest.main()
