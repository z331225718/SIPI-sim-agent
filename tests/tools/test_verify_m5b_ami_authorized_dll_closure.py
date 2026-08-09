from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from verify_m5b_ami_authorized_dll_closure import redact_system_resolution, static_closure  # noqa: E402


def assert_value_error(operation, expected: str) -> None:
    try:
        operation()
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_redaction_keeps_only_system32_basename() -> None:
    assert redact_system_resolution([{"name": "kernel32.dll", "kind": "system32", "path": r"C:\\Windows\\System32\\kernel32.dll", "sha256": "a" * 64}]) == [
        {"name": "kernel32.dll", "kind": "system32", "path": "System32/kernel32.dll", "sha256": "a" * 64}
    ]


def test_static_closure_rejects_unexpected_import_before_resolution(monkeypatch) -> None:
    monkeypatch.setattr("verify_m5b_ami_authorized_dll_closure.parse_pe", lambda _: {"machine": "0x8664", "subsystem": 2, "normalImports": ["extra.dll"], "delayImports": []})
    with tempfile.TemporaryDirectory() as name:
        assert_value_error(
            lambda: static_closure({"expectedStaticImports": {"normal": ["kernel32.dll"], "delay": []}}, Path(name) / "dll", Path(name)),
            "unexpected normal",
        )


def main() -> None:
    test_redaction_keeps_only_system32_basename()
    from unittest.mock import patch
    with patch("verify_m5b_ami_authorized_dll_closure.parse_pe", lambda _: {"machine": "0x8664", "subsystem": 2, "normalImports": ["extra.dll"], "delayImports": []}):
        with tempfile.TemporaryDirectory() as name:
            assert_value_error(
                lambda: static_closure({"expectedStaticImports": {"normal": ["kernel32.dll"], "delay": []}}, Path(name) / "dll", Path(name)),
                "unexpected normal",
            )


if __name__ == "__main__":
    main()
