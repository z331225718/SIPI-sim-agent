"""Verify the M0 platform-target record without depending on a project environment."""

from __future__ import annotations

import hashlib
import json
import ntpath
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "docs" / "baselines" / "platform-support.v1.json"
EXPECTED_EVIDENCE_PATHS = {
    "toolchains.lock",
    "docs/baselines/toolchain-verification.v1.json",
    "docs/baselines/agent-spice-baseline.json",
    "docs/baselines/agent-com-baseline.json",
    "docs/baselines/pybert-baseline.json",
}
EXPECTED_ENGINES = {"agent-spice", "agent-com", "pybert"}
EXPECTED_ENGINE_ENVIRONMENT_STATES = {
    "agent-spice": "isolated_python_diagnostic_unlocked_rust_locked",
    "agent-com": "isolated_requirements_parity_lock",
    "pybert": "isolated_python_lock_with_rust_source_lock_provenance_gap",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def repository_file(relative_path: str) -> Path:
    candidate = Path(relative_path)
    require(
        not candidate.is_absolute() and not ntpath.isabs(relative_path) and ".." not in candidate.parts,
        f"evidence path must be repository-relative: {relative_path}",
    )
    resolved = (ROOT / candidate).resolve()
    require(resolved.is_relative_to(ROOT), f"evidence path escapes repository: {relative_path}")
    return resolved


def main() -> int:
    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    require(record["schema"] == "sipi.platform-support.v1", "unexpected schema")
    require(record["status"] == "selected_for_m0_not_certified", "record must remain uncertified")

    tier = record["support_tiers"]["tier_1_certification_target"]
    require(tier["evidence_state"] == "unverified", "managed worker must remain unverified in M0")
    require(tier["certification_status"] == "not_certified", "tier must remain uncertified")
    require(
        tier["platform_key"]
        == {
            "os_family": "windows",
            "architecture": "x86_64",
            "python_implementation": "CPython",
            "python_abi": "cp312",
            "execution_mode": "managed_worker",
        },
        "unexpected M0 platform key",
    )
    require(
        record["evidence_realization"]["engine_environment_policy"]
        == "independent_lock_and_environment_per_engine",
        "engine environments must remain independent",
    )

    lock = tomllib.loads((ROOT / "toolchains.lock").read_text(encoding="utf-8"))
    realization = record["evidence_realization"]
    require(realization["toolchain_probe_state"] == "baseline_passed", "toolchain probe evidence lost")
    require(realization["python"]["version"] == lock["python"]["selected_version"], "Python version mismatch")
    require(realization["rust"]["toolchain"] == lock["rust"]["toolchain"], "Rust toolchain mismatch")
    require(realization["rust"]["rustc_commit"] == lock["rust"]["rustc_commit"], "Rust commit mismatch")
    require(realization["msvc"]["build_tools"] == lock["msvc"]["visual_studio_build_tools"], "MSVC version mismatch")
    require(realization["msvc"]["installation_version"] == lock["msvc"]["installation_version"], "MSVC install mismatch")

    evidence_refs = record["evidence_refs"]
    evidence_paths = [ref["path"] for ref in evidence_refs]
    require(set(evidence_paths) == EXPECTED_EVIDENCE_PATHS, "unexpected evidence-ref set")
    require(len(evidence_paths) == len(set(evidence_paths)), "duplicate evidence refs")
    for ref in evidence_refs:
        path = repository_file(ref["path"])
        require(path.is_file(), f"missing evidence: {ref['path']}")
        require(sha256(path) == ref["sha256"], f"evidence hash mismatch: {ref['path']}")

    engine_evidence = record["engine_evidence"]
    engine_ids = [item["engine"] for item in engine_evidence]
    require(set(engine_ids) == EXPECTED_ENGINES, "unexpected engine-evidence set")
    require(len(engine_ids) == len(set(engine_ids)), "duplicate engine evidence")
    for item in engine_evidence:
        baseline = json.loads((ROOT / "docs" / "baselines" / f"{item['engine']}-baseline.json").read_text(encoding="utf-8"))
        require(item["baseline_status"] == baseline["status"], f"baseline status mismatch: {item['engine']}")
        require("certified" not in baseline["status"], f"baseline promoted: {item['engine']}")
        require(item["python_version"] == baseline["environment"]["python"], f"Python mismatch: {item['engine']}")
        require(
            item["environment_state"] == EXPECTED_ENGINE_ENVIRONMENT_STATES[item["engine"]],
            f"environment state mismatch: {item['engine']}",
        )
        if "rust_toolchain" in item:
            require(item["rust_toolchain"] == baseline["environment"]["rust"], f"Rust mismatch: {item['engine']}")

    solver_evidence = record["solver_evidence"]
    solver_ids = [solver["solver"] for solver in solver_evidence]
    expected_solvers = set(lock["external_solvers"])
    require(set(solver_ids) == expected_solvers, "unexpected solver-evidence set")
    require(len(solver_ids) == len(set(solver_ids)), "duplicate solver evidence")
    for solver in solver_evidence:
        lock_solver = lock["external_solvers"][solver["solver"]]
        require(solver["advertise"] is False, f"solver may not advertise in M0: {solver['solver']}")
        require(solver["state"] in {"observed_local", "unavailable"}, f"unexpected solver state: {solver['solver']}")
        expected_state = "observed_local" if lock_solver["availability"] == "observed" else "unavailable"
        require(solver["state"] == expected_state, f"solver state mismatch: {solver['solver']}")
        if expected_state == "observed_local":
            require(solver["version"] == lock_solver["version"], f"solver version mismatch: {solver['solver']}")

    non_claims = set(record["non_claims"])
    require(any("not release support" in claim for claim in non_claims), "release-support non-claim missing")
    require(any("No operation or engine capability" in claim for claim in non_claims), "capability non-claim missing")
    require("C:/Users/" not in json.dumps(record), "record must not contain user-specific paths")
    print("platform-support.v1.json: valid M0 selection; not certified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"platform-support.v1.json: invalid: {error}", file=sys.stderr)
        raise SystemExit(1)
