from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


TOOL = Path(__file__).resolve().parents[2] / "tools" / "verify_m5b_pybert_history_preflight.py"
SPEC = importlib.util.spec_from_file_location("m5b_history_preflight", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_vendor_and_legacy_paths_never_enter_candidate_retain_set():
    for path in ("PyAMI/src/pyibisami/ami/model.py", "models/ibisami/example_rx.dll", "tests/examples/model.dll"):
        decision, _, target, _ = MODULE.classify(path)
        assert decision != "retain"
        assert target is None


def test_native_core_has_two_declared_destinations():
    decision, _, import_target, license_status = MODULE.classify("native/pybert-core/src/lib.rs")
    assert decision == "retain"
    assert import_target == "engines/py-bert-agent/native/pybert-core/src/lib.rs"
    assert "BSD-derived" in license_status


def test_digest_is_deterministic_for_expanded_policy_entries():
    entry = {"path": "src/pybert/pybert.py", "decision": "retain", "blob": "a" * 40}
    assert MODULE.digest([entry]) == hashlib.sha256(b'[{"blob":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","decision":"retain","path":"src/pybert/pybert.py"}]').hexdigest()
