"""Compare independent Python and Rust M1-06 conformance runner decisions."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from verify_m1_rule_ledger import verify as verify_rule_ledger


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "contracts" / "v1"
RUSTUP = Path.home() / ".cargo" / "bin" / "rustup.exe"
TOOLCHAIN = "1.97.0-x86_64-pc-windows-msvc"
PYTHON = Path.home() / "AppData" / "Roaming" / "uv" / "python" / "cpython-3.12.13-windows-x86_64-none" / "python.exe"
UV = "uv"


def _json_output(command: list[str]) -> dict:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(next(line for line in reversed(completed.stdout.splitlines()) if line.startswith("{")))


def _tree_sha256() -> str:
    files = [path for root in (FIXTURES, ROOT / "schemas") for path in root.rglob("*") if path.is_file()]
    files.extend((ROOT / name) for name in ("toolchains.lock", "uv.lock", "tests/contract/rust-consumer/Cargo.lock"))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _index_results(output: dict, language: str, expected_ids: set[str], failures: list[str]) -> dict[str, dict]:
    results = output.get("results", [])
    ids = [result.get("id") for result in results]
    if len(ids) != len(set(ids)):
        failures.append(f"{language}:duplicate_result_id")
    if set(ids) != expected_ids:
        failures.append(f"{language}:result_set_mismatch")
    return {result["id"]: result for result in results if isinstance(result.get("id"), str)}


def main() -> int:
    suite = json.loads((FIXTURES / "suite.json").read_text(encoding="utf-8"))
    if not PYTHON.is_file():
        raise RuntimeError(f"locked Python is unavailable: {PYTHON}")
    case_ids = [case["id"] for case in suite["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("suite has duplicate case ids")
    python = _json_output([UV, "run", "--locked", "--python", str(PYTHON), "python", "-B", "tests/contract/python_runner.py"])
    rust = _json_output([str(RUSTUP), "run", TOOLCHAIN, "cargo", "run", "--locked", "--quiet", "--manifest-path", "tests/contract/rust-consumer/Cargo.toml", "--", "fixtures/contracts/v1"])
    expected = {case["id"]: case for case in suite["cases"] if "deferred_to" not in case}
    failures = []
    language_results = {name: _index_results(output, name, set(case_ids), failures) for name, output in {"python": python, "rust": rust}.items()}
    for case_id, case in expected.items():
        for language in case["required_languages"]:
            result = language_results[language].get(case_id, {})
            requires_preservation = bool(case["expect"].get("preserve"))
            if result.get("decision") != case["expect"]["decision"] or result.get("phase") != case["expect"]["phase"] or ("code" in case["expect"] and result.get("code") != case["expect"]["code"]) or (requires_preservation and result.get("preserved") is not True):
                failures.append(f"{language}:{case_id}")
    ledger = verify_rule_ledger(case_results=language_results)
    failures.extend(ledger["failures"])
    print(json.dumps({"suite": suite["suite"], "status": suite["status"], "fixture_tree_sha256": _tree_sha256(), "ledger": ledger, "failures": failures, "python": language_results["python"], "rust": language_results["rust"]}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
