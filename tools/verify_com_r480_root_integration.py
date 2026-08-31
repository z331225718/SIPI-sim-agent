"""Verify the non-distributed root-CLI link to the Agent-COM direct port."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "docs/baselines/com-r480-root-integration.v1.yaml"
SCHEMA = "sipi.com.r480-root-integration.v1"
DIRECT = "sipi-agent-com-direct"
EXPECTED_KEYS = {
    "schema",
    "status",
    "candidate",
    "feature",
    "default_cli_excludes_direct",
    "root_feature_closure",
    "candidate_evidence",
    "non_claims",
}
NON_CLAIMS = [
    "no_public_com_run_route",
    "no_public_request_or_result_wire",
    "no_distribution_admission",
    "no_release_admission",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_path(path: object) -> bool:
    return isinstance(path, str) and bool(path) and "\\" not in path and not Path(path).is_absolute() and all(
        part not in {"", ".", ".."} for part in path.split("/")
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest object")
    return document


def validate_document(document: dict[str, Any]) -> None:
    require(set(document) == EXPECTED_KEYS, "manifest keys")
    require(document["schema"] == SCHEMA, "schema")
    require(document["status"] == "internal_feature_linked_non_distributed", "status")
    candidate = document["candidate"]
    require(
        isinstance(candidate, dict)
        and set(candidate) == {"commit", "tree"}
        and all(isinstance(value, str) and len(value) == 40 for value in candidate.values()),
        "candidate",
    )
    require(document["feature"] == "com-direct-integration", "feature")
    require(document["default_cli_excludes_direct"] is True, "default route boundary")
    closure = document["root_feature_closure"]
    require(
        isinstance(closure, dict)
        and set(closure) == {"package_count", "sha256"}
        and isinstance(closure["package_count"], int)
        and closure["package_count"] > 0
        and isinstance(closure["sha256"], str)
        and len(closure["sha256"]) == 64,
        "closure receipt",
    )
    evidence = document["candidate_evidence"]
    require(isinstance(evidence, list) and evidence, "candidate evidence")
    paths: set[str] = set()
    for item in evidence:
        require(
            isinstance(item, dict)
            and set(item) == {"path", "sha256"}
            and safe_path(item["path"])
            and isinstance(item["sha256"], str)
            and len(item["sha256"]) == 64,
            "candidate evidence item",
        )
        require(item["path"] not in paths, "duplicate candidate evidence")
        paths.add(item["path"])
    require(document["non_claims"] == NON_CLAIMS, "non-claims")


def reachable_packages(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    resolve = metadata.get("resolve")
    require(isinstance(resolve, dict) and isinstance(resolve.get("root"), str), "metadata root")
    nodes = resolve.get("nodes")
    packages = metadata.get("packages")
    require(isinstance(nodes, list) and isinstance(packages, list), "metadata shape")
    edges = {node.get("id"): node.get("dependencies") for node in nodes if isinstance(node, dict)}
    pending = [resolve["root"]]
    reachable: set[str] = set()
    while pending:
        package_id = pending.pop()
        if package_id in reachable:
            continue
        reachable.add(package_id)
        dependencies = edges.get(package_id)
        require(isinstance(dependencies, list), f"metadata dependencies: {package_id}")
        pending.extend(item for item in dependencies if isinstance(item, str))
    result = []
    for package in packages:
        require(isinstance(package, dict), "metadata package")
        if package.get("id") not in reachable:
            continue
        entry = {key: package.get(key) for key in ("id", "name", "version", "license", "source")}
        require(
            all(isinstance(entry[key], str) and entry[key] for key in ("id", "name", "version", "license")),
            f"incomplete package license receipt: {entry.get('name')}",
        )
        result.append(entry)
    return sorted(result, key=lambda item: item["id"])


def metadata(root: Path, cargo: str, *, features: list[str]) -> list[dict[str, Any]]:
    command = [
        cargo,
        "metadata",
        "--locked",
        "--offline",
        "--format-version",
        "1",
        "--manifest-path",
        str(root / "crates/sipi-cli/Cargo.toml"),
    ]
    for feature in features:
        command.extend(["--features", feature])
    raw = subprocess.run(command, check=True, capture_output=True).stdout
    return reachable_packages(json.loads(raw))


def verify(root: Path, cargo: str) -> dict[str, str]:
    document = load(root / MANIFEST)
    validate_document(document)
    candidate = document["candidate"]
    tree = git(root, "rev-parse", f"{candidate['commit']}^{{tree}}").decode().strip()
    require(tree == candidate["tree"], "candidate tree")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", candidate["commit"], "HEAD"], check=True)
    for item in document["candidate_evidence"]:
        value = git(root, "show", f"{candidate['commit']}:{item['path']}")
        require(digest(value) == item["sha256"], f"candidate evidence drift: {item['path']}")
    require(
        subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{candidate['commit']}:crates/sipi-agent-com-direct/Cargo.lock"],
            capture_output=True,
        ).returncode != 0,
        "nested direct lock must be absent",
    )
    default = metadata(root, cargo, features=[])
    require(DIRECT not in {item["name"] for item in default}, "default CLI reaches direct port")
    feature = metadata(root, cargo, features=[document["feature"]])
    require(DIRECT in {item["name"] for item in feature}, "feature CLI omits direct port")
    canonical = json.dumps(feature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = document["root_feature_closure"]
    require(len(feature) == expected["package_count"], "feature closure package count")
    require(digest(canonical) == expected["sha256"], "feature closure receipt")
    return {"valid": "true", "status": document["status"], "feature_package_count": str(len(feature))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root.resolve(), args.cargo), sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"valid": "false", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
