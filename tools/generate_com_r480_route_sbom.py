"""Generate a bounded CycloneDX SBOM for the non-default COM direct feature."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FEATURE = "com-direct-integration"
SCHEMA = "CycloneDX"
SPEC_VERSION = "1.5"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def cargo_metadata(root: Path, cargo: str) -> dict[str, Any]:
    raw = subprocess.run(
        [
            cargo,
            "metadata",
            "--locked",
            "--offline",
            "--format-version",
            "1",
            "--manifest-path",
            str(root / "crates/sipi-cli/Cargo.toml"),
            "--features",
            FEATURE,
        ],
        check=True,
        capture_output=True,
    ).stdout
    value = json.loads(raw)
    require(isinstance(value, dict), "cargo metadata object")
    return value


def reachable(metadata: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], str]:
    resolve = metadata.get("resolve")
    packages = metadata.get("packages")
    require(isinstance(resolve, dict) and isinstance(resolve.get("root"), str), "metadata root")
    require(isinstance(resolve.get("nodes"), list) and isinstance(packages, list), "metadata shape")
    edges: dict[str, list[str]] = {}
    for node in resolve["nodes"]:
        require(isinstance(node, dict) and isinstance(node.get("id"), str), "metadata node")
        dependencies = node.get("dependencies")
        require(isinstance(dependencies, list) and all(isinstance(item, str) for item in dependencies), "metadata dependencies")
        edges[node["id"]] = dependencies
    pending = [resolve["root"]]
    visited: set[str] = set()
    while pending:
        package_id = pending.pop()
        if package_id in visited:
            continue
        visited.add(package_id)
        pending.extend(edges.get(package_id, []))
    selected: dict[str, dict[str, Any]] = {}
    for package in packages:
        require(isinstance(package, dict) and isinstance(package.get("id"), str), "metadata package")
        if package["id"] in visited:
            selected[package["id"]] = package
    require(set(selected) == visited, "reachable package identity")
    return selected, {key: [item for item in value if item in visited] for key, value in edges.items() if key in visited}, resolve["root"]


def bom_ref(package: dict[str, Any]) -> str:
    package_id = package.get("id")
    require(isinstance(package_id, str) and package_id, "package id")
    return f"urn:sipi:cargo-metadata:{sha256(package_id.encode())}"


def package_component(package: dict[str, Any], root: Path) -> dict[str, Any]:
    name = package.get("name")
    version = package.get("version")
    license_value = package.get("license")
    source = package.get("source")
    manifest_path = package.get("manifest_path")
    require(
        isinstance(name, str)
        and isinstance(version, str)
        and isinstance(license_value, str)
        and license_value,
        "package identity/license",
    )
    properties = [{"name": "sipi:declared-license", "value": license_value}]
    if isinstance(source, str) and source:
        purl = f"pkg:cargo/{name}@{version}"
        properties.append({"name": "sipi:cargo-source", "value": source})
    else:
        require(isinstance(manifest_path, str), "workspace manifest path")
        path = Path(manifest_path)
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as error:
            raise ValueError(f"workspace package escapes root: {name}") from error
        purl = f"pkg:generic/sipi/{name}@{version}"
        properties.append({"name": "sipi:workspace-manifest", "value": relative})
    return {
        "type": "library",
        "bom-ref": bom_ref(package),
        "name": name,
        "version": version,
        "purl": purl,
        "properties": properties,
    }


def build_bom(metadata: dict[str, Any], root: Path) -> dict[str, Any]:
    packages, edges, root_id = reachable(metadata)
    root_package = packages[root_id]
    components = sorted((package_component(package, root) for package in packages.values()), key=lambda item: item["bom-ref"])
    refs = {package_id: bom_ref(package) for package_id, package in packages.items()}
    dependencies = [
        {"ref": refs[package_id], "dependsOn": sorted(refs[item] for item in edges[package_id])}
        for package_id in sorted(packages)
    ]
    root_ref = refs[root_id]
    serial_seed = sha256(canonical({"feature": FEATURE, "root": root_ref, "components": components, "dependencies": dependencies}))
    return {
        "bomFormat": SCHEMA,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid.UUID(serial_seed[:32])}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": root_package["name"],
                "version": root_package["version"],
                "properties": [
                    {"name": "sipi:feature", "value": FEATURE},
                    {"name": "sipi:distribution-status", "value": "non-distributed"},
                    {"name": "sipi:license-decision", "value": "not-concluded"},
                ],
            },
            "properties": [
                {"name": "sipi:generator", "value": "tools/generate_com_r480_route_sbom.py"},
                {"name": "sipi:scope", "value": "root-cli feature closure only"},
            ],
        },
        "components": components,
        "dependencies": dependencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output.exists():
            raise ValueError("output must be new")
        bom = build_bom(cargo_metadata(args.root.resolve(), args.cargo), args.root.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical(bom) + b"\n")
        print(json.dumps({"status": "generated_non_distributed", "sha256": sha256(output.read_bytes()), "component_count": len(bom["components"])}))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
