from __future__ import annotations

import argparse
import hashlib
import importlib.resources
import json
import platform
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from sipi_runtime import EngineLockLoadError, load_engine_lock

TOOLCHAIN_DECLARED = ("rust", "node", "git", "msvc", "external_solvers")
FIXTURE_MANIFEST_SCHEMA_ID = "sipi.fixture-manifest.v1"
FIXTURE_AVAILABILITY = {"present", "missing", "partial", "present_unscanned"}
REQUIRED_SCHEMA_FILES = (
    "artifact-ref.v1.schema.json",
    "backend-execution-request.v1.schema.json",
    "backend-execution-result.v1.schema.json",
    "capabilities-baseline.v1.schema.json",
    "dag-node-record.v1.schema.json",
    "engine-capabilities.v1.schema.json",
    "engine-lock.v1.schema.json",
    "run-event.v1.schema.json",
    "run-record.v1.schema.json",
    "run-request.v1.schema.json",
    "run-result.v1.schema.json",
    "success-manifest.v1.schema.json",
    "validation-report.v1.schema.json",
    "_defs/provenance.v1.schema.json",
    "_defs/runtime-validation.v1.schema.json",
)


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value else Path.cwd().resolve()


def _check(check_id: str, status: str, **details: Any) -> dict[str, Any]:
    return {"id": check_id, "status": status, "details": details}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _toolchains(root: Path) -> dict[str, Any]:
    path = root / "toolchains.lock"
    if not path.is_file():
        return _check("toolchains", "missing", path=str(path))
    try:
        lock = tomllib.loads(path.read_text(encoding="utf-8"))
        selected = lock["python"]["selected_version"]
        expected_platform = lock["platform"]
    except (KeyError, TypeError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return _check("toolchains", "invalid", path=str(path), error=str(error))
    actual_python = platform.python_version()
    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    actual_platform = f"{os_name}-{architecture}"
    python_ok = actual_python == selected
    platform_ok = actual_platform == expected_platform
    tools = [
        {"name": "python", "declared": selected, "observed": actual_python, "checked": True, "status": "ok" if python_ok else "mismatch"},
        {"name": "platform", "declared": expected_platform, "observed": actual_platform, "checked": True, "status": "ok" if platform_ok else "mismatch"},
    ]
    for name in TOOLCHAIN_DECLARED:
        declared = lock.get(name)
        tools.append({"name": name, "declared": declared, "observed": None, "checked": False, "status": "not_checked" if declared is not None else "not_declared"})
    status = "mismatch" if not (python_ok and platform_ok) else "partial"
    return _check("toolchains", status, path=str(path), basis="lock_declared", selected_python=selected, expected_platform=expected_platform, observed={"python": actual_python, "platform": actual_platform}, tools=tools)


def _engine_lock(root: Path) -> dict[str, Any]:
    path = root / "engine.lock"
    if not path.is_file():
        return _check("engine_lock", "missing", path=str(path))
    try:
        lock = load_engine_lock(path)
    except EngineLockLoadError as error:
        return _check("engine_lock", "invalid", path=str(path), error=str(error))

    engines: list[dict[str, Any]] = []
    statuses: list[str] = []
    licenses: list[str] = []
    for entry in lock.wire["engines"]:
        bundle = entry["bundle"]
        common = {
            "instance_id": entry["instance_id"],
            "license_status": entry["license_provenance"]["distribution_status"],
            "capabilities_sha256": entry["capabilities"]["sha256"],
        }
        licenses.append("blocked" if common["license_status"] == "blocked_unknown" else "ok")
        if bundle["kind"] == "https_url":
            engines.append({**common, "status": "not_checked", "kind": "https_url", "locator": bundle["url"], "expected_sha256": bundle["sha256"]})
            statuses.append("not_checked")
            continue
        candidate = (root / str(bundle["path"])).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            engines.append({**common, "status": "mismatch", "reason": "bundle_path_escapes_root"})
            statuses.append("mismatch")
            continue
        if not candidate.is_file():
            engines.append({**common, "status": "missing", "path": str(candidate)})
            statuses.append("missing")
            continue
        actual = _sha256(candidate)
        expected = bundle["sha256"]
        status = "ok" if actual == expected else "mismatch"
        engines.append({**common, "status": status, "locator": str(candidate), "expected_sha256": expected, "actual_sha256": actual})
        statuses.append(status)
    if not statuses:
        top_status = "empty"
    elif any(item in {"mismatch", "missing"} for item in statuses):
        top_status = "mismatch"
    elif "blocked" in licenses:
        top_status = "blocked"
    elif any(item == "not_checked" for item in statuses):
        top_status = "not_checked"
    else:
        top_status = "ok"
    return _check("engine_lock", top_status, path=str(path), engines=engines)


def _iter_json_files(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            if child.is_dir():
                stack.append(child)
            elif child.name.endswith(".json"):
                found.append(child)
    return found


def _missing_required_files(root: Any, required: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for relative in required:
        target = root.joinpath(*relative.split("/"))
        if not target.is_file():
            missing.append(relative)
    return missing


def _schemas(root: Path) -> dict[str, Any]:
    source_root = root / "schemas"
    source_mode = source_root.is_dir()
    try:
        if source_mode:
            active: Any = source_root
        else:
            active = importlib.resources.files("sipi_contracts").joinpath("_schemas")
        bundled = importlib.resources.files("sipi_contracts").joinpath("_schemas")
        active_files = _iter_json_files(active)
        schema_ids: set[str] = set()
        for path in active_files:
            document = json.loads(path.read_text(encoding="utf-8"))
            if path.parent.name == "_defs":
                continue
            schema_id = document.get("$id")
            if not isinstance(schema_id, str):
                raise ValueError(f"schema without $id: {path.name}")
            expected = "sipi." + path.name.removesuffix(".schema.json")
            if schema_id != expected:
                raise ValueError(f"schema $id mismatch: {path.name} -> {schema_id}")
            if schema_id in schema_ids:
                raise ValueError(f"duplicate schema $id: {schema_id}")
            schema_ids.add(schema_id)
        active_missing = _missing_required_files(active, REQUIRED_SCHEMA_FILES)
        bundled_missing = _missing_required_files(bundled, REQUIRED_SCHEMA_FILES)
        bundled_files = _iter_json_files(bundled)
    except (AttributeError, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, ModuleNotFoundError) as error:
        return _check("schemas", "invalid", error=str(error))
    authority_path = active / "authority.v1.yaml"
    source_status = "not_checked"
    missing: list[str] = []
    if getattr(authority_path, "is_file", lambda: False)():
        try:
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            for item in authority["schemas"]:
                source = item["source_of_truth"]
                if source["kind"] != "local_json_schema":
                    continue
                declared_path = source["path"]
                if source_mode:
                    candidate = (root / declared_path).resolve()
                    if not candidate.is_relative_to(root):
                        missing.append(declared_path)
                        continue
                relative = declared_path.removeprefix("schemas/")
                target = active.joinpath(*relative.split("/"))
                if not target.is_file():
                    missing.append(source["path"])
                    continue
                document = json.loads(target.read_text(encoding="utf-8"))
                if document.get("$id") != item["schema_id"]:
                    raise ValueError(f"authority $id mismatch: {declared_path} -> {document.get('$id')}")
            source_status = "ok" if not missing else "missing"
        except (KeyError, TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            return _check("schemas", "invalid", active_schema_root="source" if source_mode else "packaged", bundled_schema_count=len(bundled_files), authority=str(authority_path), error=str(error))
    missing_all = sorted(set(missing) | set(active_missing) | set(bundled_missing))
    status = "missing" if missing_all else "ok"
    return _check(
        "schemas",
        status,
        active_schema_root="source" if source_mode else "packaged",
        bundled_schema_count=len(bundled_files),
        schema_ids=sorted(schema_ids),
        source_authority_status=source_status,
        authority=str(authority_path),
        missing=missing_all,
        bundled_missing=sorted(set(bundled_missing)),
    )


def _fixtures(root: Path) -> dict[str, Any]:
    path = root / "fixtures" / "manifest.v1.json"
    if not path.is_file():
        return _check("fixtures", "missing", path=str(path))
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("schema") != FIXTURE_MANIFEST_SCHEMA_ID:
            return _check("fixtures", "invalid", path=str(path), reason="unexpected manifest schema", observed_schema=manifest.get("schema"))
        assets = manifest["assets"]
        if not isinstance(assets, list) or not all(isinstance(item, dict) and isinstance(item.get("availability"), str) for item in assets):
            raise ValueError("manifest assets must be objects with string availability")
        counts = Counter(item["availability"] for item in assets)
        open_coverage = manifest.get("open_coverage")
        if open_coverage is not None and not isinstance(open_coverage, list):
            raise ValueError("manifest open_coverage must be a list")
    except (KeyError, TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        return _check("fixtures", "invalid", path=str(path), error=str(error))
    unknown = sorted(set(counts) - FIXTURE_AVAILABILITY)
    open_count = len(open_coverage or [])
    has_issues = bool(counts.get("missing") or counts.get("partial") or unknown or open_count)
    status = "partial" if has_issues else "not_checked"
    return _check("fixtures", status, path=str(path), basis="manifest_declared", observed=False, availability=dict(sorted(counts.items())), unknown_availability=unknown, open_coverage=open_count)


def doctor(root: Path) -> dict[str, Any]:
    checks = [_toolchains(root), _engine_lock(root), _schemas(root), _fixtures(root)]
    overall = "ok" if all(item["status"] == "ok" for item in checks) else "issues"
    return {"format_version": 1, "command": "doctor", "overall": overall, "checks": checks}


def capabilities(root: Path, instance: str | None) -> dict[str, Any]:
    catalog = root / "docs" / "baselines" / "capabilities.certified.v1.json"
    if not catalog.is_file():
        source = {"kind": "certified_catalog", "status": "absent"}
    else:
        source = {"kind": "certified_catalog", "status": "invalid", "path": str(catalog), "reason": "no certified catalog contract is available before M2"}
    return {"format_version": 1, "command": "capabilities", "source": source, "filter": {"instance": instance}, "advertised": []}


def _render(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    if payload["command"] == "doctor":
        print(f"doctor: {payload['overall']}")
        for item in payload["checks"]:
            print(f"{item['id']}: {item['status']}")
    else:
        print(f"capabilities: {payload['source']['status']}")
        print("advertised: 0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sipi")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "capabilities"):
        command = subcommands.add_parser(name)
        command.add_argument("--root")
        command.add_argument("--format", choices=("text", "json"), default="text")
    subcommands.choices["capabilities"].add_argument("--instance")
    args = parser.parse_args(argv)
    root = _root(args.root)
    payload = doctor(root) if args.command == "doctor" else capabilities(root, args.instance)
    _render(payload, args.format)
    return 0 if (args.command == "capabilities" and payload["source"]["status"] == "absent") or (args.command == "doctor" and payload["overall"] == "ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
