"""Preflight the authorized example_rx DLL's exact static import closure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from replay_m5b_ami_authorized_runtime import FIXTURE_DOCUMENT, external, replay
from verify_m5b_ami_candidate_assurance import parse_pe, system_resolution
from verify_m5b_ami_vendor_fixture_preflight import blob, verify as verify_fixture


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/m5b-ami-authorized-dll-closure-preflight.v1.json"
SCHEMA = "sipi.m5b-ami-authorized-dll-closure-report.v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def redact_system_resolution(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry in entries:
        name, kind = entry.get("name"), entry.get("kind")
        reject(isinstance(name, str) and isinstance(kind, str), "invalid system import resolution")
        if kind == "api_set":
            result.append({"name": name, "kind": kind, "mapping": "windows_api_set_contract"})
            continue
        reject(kind == "system32" and isinstance(entry.get("sha256"), str), "unresolved non-system DLL import")
        result.append({"name": name, "kind": kind, "path": f"System32/{name}", "sha256": entry["sha256"]})
    return result


def static_closure(document: dict[str, Any], dll: Path, system_root: Path) -> dict[str, Any]:
    expected = document.get("expectedStaticImports")
    reject(isinstance(expected, dict), "expected static imports")
    normal, delay = expected.get("normal"), expected.get("delay")
    reject(isinstance(normal, list) and isinstance(delay, list), "expected static import lists")
    pe = parse_pe(dll)
    reject(pe.get("machine") == "0x8664", "vendor DLL is not Windows x64")
    reject(pe.get("normalImports") == normal, "unexpected normal static imports")
    reject(pe.get("delayImports") == delay, "unexpected delay static imports")
    return {
        "pe": {"machine": pe["machine"], "subsystem": pe["subsystem"]},
        "normal": redact_system_resolution(system_resolution(normal, system_root)),
        "delay": redact_system_resolution(system_resolution(delay, system_root)),
    }


def verify(
    *, bundle: Path, pybert_repo: Path, report: Path, system_root: Path, timeout_seconds: float
) -> dict[str, Any]:
    reject(sys.platform == "win32", "Windows x64 DLL closure preflight is unsupported on this platform")
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    reject(document.get("schema") == "sipi.m5b-ami-authorized-dll-closure-preflight.v1", "schema")
    reject(document.get("platform") == "windows-x86_64", "platform")
    reject(sha256_bytes(FIXTURE_DOCUMENT.read_bytes()) == document.get("fixtureDocumentSha256"), "fixture document identity")
    report = external(report, ROOT, bundle, pybert_repo)
    reject(not report.exists(), "report path already exists")
    fixture_document = json.loads(FIXTURE_DOCUMENT.read_text(encoding="utf-8"))
    fixture = verify_fixture(fixture_document, pybert_repo)
    dll_asset = next(asset for asset in fixture_document["fixture"]["assets"] if asset["kind"] == "dll")
    expected_fixture = document.get("fixture")
    reject(
        isinstance(expected_fixture, dict)
        and expected_fixture == {
            "id": fixture_document["fixture"]["id"],
            "sourceCommit": fixture_document["source"]["commit"],
            "dllSha256": dll_asset["sha256"],
        },
        "fixture identity",
    )
    work = Path(tempfile.mkdtemp(prefix="m5b-ami-dll-closure-"))
    try:
        object_id, dll_bytes = blob(pybert_repo, fixture_document["source"]["commit"], dll_asset["path"])
        reject(object_id == dll_asset["blob"] and sha256_bytes(dll_bytes) == dll_asset["sha256"], "DLL Git object")
        dll_path = work / "example_rx.dll"
        dll_path.write_bytes(dll_bytes)
        closure = static_closure(document, dll_path, system_root)
        lifecycle_report = work / "lifecycle-report.json"
        lifecycle = replay(
            bundle_dir=bundle, pybert_repo=pybert_repo, report_path=lifecycle_report,
            timeout_seconds=timeout_seconds,
        )
        reject(lifecycle.get("accepted") is True, "authorized lifecycle replay")
        result = {
            "schema": SCHEMA,
            "accepted": True,
            "coverage": document["coverage"],
            "platform": "windows-x86_64",
            "fixture": {
                "sourceCommit": fixture_document["source"]["commit"],
                "dll": next(asset for asset in fixture["assets"] if asset["kind"] == "dll"),
            },
            "staticImportClosure": closure,
            "observedLifecycle": {
                "accepted": True,
                "reportSha256": sha256_bytes(lifecycle_report.read_bytes()),
                "requestSha256": lifecycle["request"]["sha256"],
                "lifecycle": lifecycle["result"]["lifecycle"],
            },
            "loaderPolicy": {
                "dll": "Git-object materialized into a fresh private directory",
                "cwd": "same fresh private directory",
                "path": "not supplied to the candidate child environment",
            },
            "nonClaims": document["nonClaims"],
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--pybert-repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--system-root", type=Path, default=Path(r"C:\Windows"))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        result = verify(
            bundle=args.bundle.resolve(), pybert_repo=args.pybert_repo.resolve(), report=args.report.resolve(),
            system_root=args.system_root.resolve(), timeout_seconds=args.timeout_seconds,
        )
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as error:
        print(f"authorized DLL closure preflight rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": result["accepted"], "schema": result["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
