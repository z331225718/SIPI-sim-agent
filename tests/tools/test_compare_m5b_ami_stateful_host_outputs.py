from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
TOOL = ROOT / "tools" / "compare_m5b_ami_stateful_host_outputs.py"
SPEC = importlib.util.spec_from_file_location("m5b_ami_stateful_host_compare", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_matrix_contains_init_single_and_stateful_sequence_cases():
    assert [name for name, _ in MODULE.CASES] == [
        "init-only",
        "single-get-wave",
        "stateful-two-blocks",
    ]
    assert [len(waves) for _, waves in MODULE.CASES] == [0, 1, 2]
    assert len(MODULE.CASES[-1][1][0]) != len(MODULE.CASES[-1][1][1])


def test_request_v2_uses_only_sequence_field_and_hashes_all_raw_blocks():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        model = {kind: {"path": f"{kind}.bin", "sha256": "0" * 64, "byteLength": 1} for kind in ("ibis", "ami", "dll")}
        path, payload, inputs = MODULE.request_for_case(root, model, "sequence", ((1.0, -1.0), (0.25, 0.5, 1.0)))
        request = json.loads(path.read_text(encoding="utf-8"))
        assert request["schema"] == MODULE.REQUEST_SCHEMA
        assert request["mode"] == "init-get-wave-sequence"
        assert request["expectedMetadata"]["amiVersion"] == "5.1"
        assert "getWave" not in request
        assert len(request["getWaves"]) == 2
        assert len(inputs["waves"]) == 2
        assert payload == path.read_bytes()
        init_path, wave_path = root / "sequence-init.f64le", root / "sequence-wave-1.f64le"
        assert init_path.stat().st_size == 16
        assert wave_path.stat().st_size == 24


def test_reference_helper_observes_strict_status_and_closes_once():
    assert "init.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "get_wave.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "close.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "if init_status != 1" in MODULE.REFERENCE_HELPER
    assert "if status != 1" in MODULE.REFERENCE_HELPER
    assert "init_parameters_out, init_message = text(init_params), text(message)" in MODULE.REFERENCE_HELPER
    assert "if memory.value and not close_called" in MODULE.REFERENCE_HELPER


def main() -> int:
    test_matrix_contains_init_single_and_stateful_sequence_cases()
    test_request_v2_uses_only_sequence_field_and_hashes_all_raw_blocks()
    test_reference_helper_observes_strict_status_and_closes_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
