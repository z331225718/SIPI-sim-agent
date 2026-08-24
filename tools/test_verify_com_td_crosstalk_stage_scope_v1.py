import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.verify_com_td_crosstalk_stage_scope_v1 import ScopeVerificationError, verify_paths, verify_scope


ROOT = Path(__file__).resolve().parents[1]


def load():
    manifest = json.loads((ROOT / "docs/baselines/com-td-crosstalk-stage-replay-v1.manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "docs/baselines/com-td-crosstalk-stage-replay-v1.audit.json").read_text(encoding="utf-8"))
    reports = [json.loads((ROOT / path).read_text(encoding="utf-8")) for path in manifest["reports"]]
    aggregate = json.loads((ROOT / manifest["aggregate"]["path"]).read_text(encoding="utf-8"))
    return manifest, audit, reports, aggregate


class ScopeMutations(unittest.TestCase):
    def test_current_scope_is_accepted(self):
        verify_scope(*load())

    def test_formal_mode_is_rejected(self):
        values = list(load())
        values[1]["mode"] = "formal_reproducible"
        with self.assertRaises(ScopeVerificationError):
            verify_scope(*values)

    def test_hidden_venv_claim_is_rejected(self):
        values = list(load())
        values[1]["python_environment"]["complete_environment_bound"] = True
        with self.assertRaises(ScopeVerificationError):
            verify_scope(*values)

    def test_wrapper_drift_is_rejected(self):
        values = list(load())
        values[2] = copy.deepcopy(values[2])
        values[2][0]["toolchain"]["uv"]["file_sha256"] = "0" * 64
        with self.assertRaises(ScopeVerificationError):
            verify_scope(*values)

    def test_audit_swap_is_rejected(self):
        manifest, _, _, _ = load()
        manifest = copy.deepcopy(manifest)
        manifest["audit"]["path"] = manifest["reports"][0]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(manifest, handle)
            path = Path(handle.name)
        try:
            with self.assertRaises(ScopeVerificationError):
                verify_paths(path, Path("docs/baselines/com-td-crosstalk-stage-replay-v1.audit.json"), Path(manifest["aggregate"]["path"]))
        finally:
            path.unlink()

    def test_scope_tool_drift_is_rejected(self):
        values = list(load())
        values[1] = copy.deepcopy(values[1])
        values[1]["scope_gate"]["verifier"]["sha256"] = "0" * 64
        with self.assertRaises(ScopeVerificationError):
            verify_scope(*values)

    def test_delegated_tool_drift_is_rejected(self):
        values = list(load())
        values[1] = copy.deepcopy(values[1])
        values[1]["launcher_shims"]["uv"]["delegated_sha256"] = "0" * 64
        with self.assertRaises(ScopeVerificationError):
            verify_scope(*values)


if __name__ == "__main__":
    unittest.main()
