from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m5b_ami_candidate_assurance import parse_pe, system_resolution  # noqa: E402


def test_pe_parser_rejects_non_pe_input(tmp_path: Path) -> None:
    path = tmp_path / "not-an-exe.bin"
    path.write_bytes(b"not a PE")
    with pytest.raises(ValueError, match="DOS/PE"):
        parse_pe(path)


def test_system_resolution_rejects_non_system_import(tmp_path: Path) -> None:
    (tmp_path / "System32").mkdir()
    with pytest.raises(ValueError, match="non-system"):
        system_resolution(["unreviewed.dll"], tmp_path)


def test_system_resolution_records_system_hash(tmp_path: Path) -> None:
    system32 = tmp_path / "System32"
    system32.mkdir()
    (system32 / "kernel32.dll").write_bytes(b"system")
    value = system_resolution(["kernel32.dll", "api-ms-win-core-test-l1-1-0.dll"], tmp_path)
    assert value[0]["kind"] == "system32"
    assert value[1] == {
        "name": "api-ms-win-core-test-l1-1-0.dll",
        "kind": "api_set",
        "resolution": "windows_api_set_contract",
    }
