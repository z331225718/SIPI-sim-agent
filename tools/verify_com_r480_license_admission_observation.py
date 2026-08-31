"""Fail closed on the candidate-only COM R4.80 compile-closure observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "docs/baselines/com-r480-license-admission-observation.v1.yaml"
SCHEMA = "sipi.com.r480-license-admission-observation.v1"
EXPECTED_KEYS = {
    "schema",
    "status",
    "candidate",
    "route",
    "local_compile_closure",
    "forbidden_local_packages",
    "evidence",
    "source_origin",
    "boundary",
    "blockers",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(path: object) -> bool:
    if not isinstance(path, str) or not path:
        return False
    candidate = Path(path)
    return not candidate.is_absolute() and "\\" not in path and all(
        part not in {"", ".", ".."} for part in path.split("/")
    )


def git_stdout(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "manifest must be an object")
    return value


def validate_document(document: dict[str, Any]) -> None:
    require(set(document) == EXPECTED_KEYS, "manifest keys")
    require(document["schema"] == SCHEMA, "manifest schema")
    require(
        document["status"] == "candidate_only_internal_license_observation",
        "manifest status",
    )
    candidate = document["candidate"]
    require(isinstance(candidate, dict) and set(candidate) == {"commit", "tree"}, "candidate keys")
    require(all(isinstance(candidate[key], str) and len(candidate[key]) == 40 for key in candidate), "candidate ids")
    route = document["route"]
    require(
        route == {
            "command": "sipi com run",
            "profile": "r4.80 original-13 workbook execution",
            "publicly_admitted": False,
        },
        "route boundary",
    )
    closure = document["local_compile_closure"]
    require(isinstance(closure, list) and closure, "local closure")
    expected_names = [entry["name"] for entry in closure if isinstance(entry, dict) and "name" in entry]
    require(len(expected_names) == len(closure) and len(set(expected_names)) == len(closure), "closure names")
    for entry in closure:
        require(
            isinstance(entry, dict)
            and set(entry) == {"name", "path", "license"}
            and isinstance(entry["name"], str)
            and safe_path(entry["path"])
            and entry["license"] == "MIT",
            "local closure entry",
        )
    forbidden = document["forbidden_local_packages"]
    require(
        forbidden == ["sipi-agent-com-adapter", "sipi-ieee-com-sparam"],
        "forbidden local packages",
    )
    evidence = document["evidence"]
    require(isinstance(evidence, list) and evidence, "evidence")
    seen_paths: set[str] = set()
    for entry in evidence:
        require(
            isinstance(entry, dict)
            and set(entry) == {"path", "sha256"}
            and safe_path(entry["path"])
            and isinstance(entry["sha256"], str)
            and len(entry["sha256"]) == 64,
            "evidence entry",
        )
        require(entry["path"] not in seen_paths, "duplicate evidence path")
        seen_paths.add(entry["path"])
    require(
        document["source_origin"]
        == {
            "agent_com_commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
            "agent_com_tree": "7094ab6e84989b218730c52432c70da10261f8ea",
            "agent_com_license": "MIT",
            "compiled_bsd_3_clause_direct_port": False,
        },
        "source origin",
    )
    require(
        document["boundary"]
        == {
            "distribution_admitted": False,
            "release": False,
            "product_boundary_v1_remains_authoritative": True,
        },
        "boundary non-claim",
    )
    require(
        document["blockers"]
        == [
            "final distributable archive lacks a route-specific NOTICE and SBOM receipt",
            "product-boundary.v1 is provisional and MIT-only",
            "final public CLI candidate requires a fresh immutable MATLAB/Rust replay",
        ],
        "blockers",
    )


def local_closure_from_metadata(metadata: dict[str, Any], root: Path) -> list[dict[str, str]]:
    packages = metadata.get("packages")
    resolve = metadata.get("resolve")
    require(isinstance(packages, list) and isinstance(resolve, dict), "cargo metadata shape")
    root_package_id = metadata.get("resolve", {}).get("root")
    require(isinstance(root_package_id, str), "cargo metadata root")
    nodes = resolve.get("nodes")
    require(isinstance(nodes, list), "cargo metadata nodes")
    edges = {node.get("id"): node.get("dependencies", []) for node in nodes if isinstance(node, dict)}
    reachable: set[str] = set()
    pending = [root_package_id]
    while pending:
        package_id = pending.pop()
        if package_id in reachable:
            continue
        reachable.add(package_id)
        dependencies = edges.get(package_id)
        require(isinstance(dependencies, list), f"metadata dependency list: {package_id}")
        pending.extend(dependency for dependency in dependencies if isinstance(dependency, str))
    local: list[dict[str, str]] = []
    for package in packages:
        require(isinstance(package, dict), "cargo metadata package")
        if package.get("id") not in reachable:
            continue
        manifest = package.get("manifest_path")
        if not isinstance(manifest, str):
            continue
        path = Path(manifest)
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        local.append(
            {
                "name": package.get("name"),
                "path": relative,
                "license": package.get("license"),
            }
        )
    return sorted(local, key=lambda entry: entry["name"])


def verify(root: Path, cargo: str) -> dict[str, str]:
    document = load_manifest(root / MANIFEST)
    validate_document(document)
    candidate = document["candidate"]
    require(git_stdout(root, "rev-parse", f"{candidate['commit']}^{{tree}}") == candidate["tree"], "candidate tree")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", candidate["commit"], "HEAD"], check=True)
    for entry in document["evidence"]:
        path = root / entry["path"]
        require(path.is_file() and sha256(path) == entry["sha256"], f"evidence drift: {entry['path']}")
    raw_metadata = subprocess.run(
        [
            cargo,
            "metadata",
            "--locked",
            "--offline",
            "--format-version",
            "1",
            "--manifest-path",
            str(root / "crates/sipi-agent-com-direct/Cargo.toml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    actual = local_closure_from_metadata(json.loads(raw_metadata), root)
    expected = sorted(document["local_compile_closure"], key=lambda entry: entry["name"])
    require(actual == expected, "local compile closure drift")
    actual_names = {entry["name"] for entry in actual}
    require(not actual_names.intersection(document["forbidden_local_packages"]), "forbidden local package reached")
    return {"valid": "true", "status": document["status"], "closure_count": str(len(actual))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root.resolve(), args.cargo), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": "false", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
