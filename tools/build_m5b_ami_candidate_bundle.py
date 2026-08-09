"""Build an explicit, unpromoted M5B AMI host candidate-bundle manifest.

The executable and this manifest live in a caller-selected artifact directory.
Nothing produced here is an engine.lock input or a distributable runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.m5b-ami-candidate-bundle.v1"
REQUEST_SCHEMA = "agent-spice.ami-host-request.v1"
RESULT_SCHEMA = "agent-spice.ami-host-result.v1"
AGENT_SPICE_REVISION = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def clean_commit(root: Path) -> str:
    status = git(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError(f"candidate source tree must be clean: {root}")
    return git(root, "rev-parse", "HEAD")


def load_json_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("build-info must be a JSON object")
    return value


def candidate_build_info(executable: Path) -> dict[str, Any]:
    value = load_json_command([str(executable), "build-info", "--json"])
    capability = value.get("candidateCapabilities", {}).get("amiHostCandidate")
    if value.get("schema") != "agent-spice.build-info.v1" or not isinstance(capability, dict):
        raise ValueError("candidate executable does not declare ami-host-candidate capability")
    required = {
        "requestSchema": REQUEST_SCHEMA,
        "resultSchema": RESULT_SCHEMA,
        "platform": "windows-x86_64",
        "productionResolvable": False,
    }
    if {key: capability.get(key) for key in required} != required:
        raise ValueError("candidate build-info capability contract does not match v1")
    return value


def source_license_evidence(agent_spice_root: Path) -> dict[str, str]:
    license_bytes = subprocess.check_output(
        ["git", "-C", str(agent_spice_root), "show", f"{AGENT_SPICE_REVISION}:LICENSE"]
    )
    manifest_bytes = subprocess.check_output(
        ["git", "-C", str(agent_spice_root), "show", f"{AGENT_SPICE_REVISION}:LICENSE-MANIFEST.md"]
    )
    return {
        "repositoryCommit": AGENT_SPICE_REVISION,
        "licensePath": "LICENSE",
        "licenseSha256": hashlib.sha256(license_bytes).hexdigest(),
        "classificationPath": "LICENSE-MANIFEST.md",
        "classificationSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sourceScope": "native/agent-spice-sim",
        "distributionStatus": "authorized_public",
    }


def dependency_closure(system_dlls: list[str]) -> dict[str, Any]:
    normalized = sorted({name.strip().lower() for name in system_dlls if name.strip()})
    if not normalized or any("/" in name or "\\" in name or not name.endswith(".dll") for name in normalized):
        raise ValueError("dynamic dependency closure requires one or more system DLL basenames")
    return {
        "status": "declared_system_only_not_release_authorized",
        "source": "operator-declared; PE import scan is not an authorization proof",
        "system": normalized,
        "thirdParty": [],
    }


def manifest(
    *,
    source_root: Path,
    agent_spice_root: Path,
    executable: Path,
    system_dlls: list[str],
    toolchain: str,
    source_commit: str | None = None,
    build_info_loader: Callable[[Path], dict[str, Any]] = candidate_build_info,
) -> dict[str, Any]:
    executable = executable.resolve()
    if not executable.is_file():
        raise ValueError(f"candidate executable is missing: {executable}")
    source_commit = source_commit or clean_commit(source_root)
    lock = source_root / "native" / "crates" / "sipi-circuit" / "Cargo.lock"
    if not lock.is_file():
        raise ValueError(f"candidate Cargo.lock is missing: {lock}")
    return {
        "schema": SCHEMA,
        "candidate": True,
        "productionResolvable": False,
        "platform": "windows-x86_64",
        "nonClaims": [
            "not an engine.lock artifact", "not a default or auto backend",
            "not a real vendor DLL runtime", "not AMI numerical parity",
        ],
        "sipi": {
            "repositoryCommit": source_commit,
            "movedCrateLineage": {
                "hostCrate": "native/crates/sipi-ami",
                "cliCrate": "native/crates/sipi-circuit",
                "cleanRoom": True,
            },
        },
        "agentSpiceLicenseEvidence": source_license_evidence(agent_spice_root),
        "build": {
            "command": "cargo build --locked --release --manifest-path native/crates/sipi-circuit/Cargo.toml",
            "toolchain": toolchain,
            "cargoLockSha256": sha256_file(lock),
            "reproducibility": "input-pinned; executable reproducibility must be independently observed",
        },
        "executable": {
            "sourcePath": str(executable),
            "sha256": sha256_file(executable),
            "byteLength": executable.stat().st_size,
            "buildInfo": build_info_loader(executable),
        },
        "protocol": {"requestSchema": REQUEST_SCHEMA, "resultSchema": RESULT_SCHEMA},
        "dynamicDependencyClosure": dependency_closure(system_dlls),
        "externalVendorAssets": {
            "bundlePolicy": "forbidden",
            "requiredAtInvocation": [
                {"kind": "dll", "distributionStatus": "blocked_unknown"},
                {"kind": "ami", "distributionStatus": "blocked_unknown"},
                {"kind": "ibs", "distributionStatus": "blocked_unknown"},
                {"kind": "dll_dependency_closure", "distributionStatus": "blocked_unknown"},
            ],
        },
    }


def write_bundle(output_dir: Path, document: dict[str, Any], executable: Path) -> Path:
    if output_dir.exists():
        raise ValueError(f"candidate output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    copied = output_dir / executable.name
    shutil.copy2(executable, copied)
    document = json.loads(json.dumps(document))
    document["executable"]["bundlePath"] = copied.name
    document["executable"].pop("sourcePath", None)
    (output_dir / "candidate-manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_dir / "candidate-manifest.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--agent-spice-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--system-dll", action="append", default=[])
    parser.add_argument("--toolchain", default=None)
    args = parser.parse_args(argv)
    try:
        toolchain = args.toolchain or subprocess.check_output(["cargo", "--version"], text=True).strip()
        document = manifest(
            source_root=args.source_root.resolve(), agent_spice_root=args.agent_spice_root.resolve(),
            executable=args.executable, system_dlls=args.system_dll, toolchain=toolchain,
        )
        output = write_bundle(args.output_dir.resolve(), document, args.executable.resolve())
    except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as error:
        print(f"candidate bundle rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "manifest": str(output), "sha256": sha256_file(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
