"""Verify the bounded P4B-02b external self-crosscheck runner inventory."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "crates" / "sipi-ami-text"
CARGO = CRATE / "Cargo.toml"
RUNNERS = CRATE / "tests"
DISPATCHER = CRATE / "src" / "bin" / "p4b_02b_crosscheck_runner.rs"
TOOLS = ROOT / "tools"
EVIDENCE = ROOT / "docs" / "baselines"
SCHEMA = "sipi.p4b-02b.runner-consolidation.v1"
EXPECTED_RUNNERS = 191
BIN_NAME = "p4b_02b_crosscheck_runner"


class RunnerConsolidationError(RuntimeError):
    pass


def _validate_cargo(text: str) -> None:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise RunnerConsolidationError("cargo_invalid") from error
    package = document.get("package", {})
    if package.get("autotests") is not False:
        raise RunnerConsolidationError("cargo_autotests_not_disabled")
    if document.get("test"):
        raise RunnerConsolidationError("cargo_external_test_targets_present")
    if document.get("features") != {"default": [], "p4b-self-crosscheck": []}:
        raise RunnerConsolidationError("cargo_quarantine_feature_drift")
    bins = document.get("bin")
    expected = [{
        "name": BIN_NAME,
        "path": "src/bin/p4b_02b_crosscheck_runner.rs",
        "test": False,
        "bench": False,
        "required-features": ["p4b-self-crosscheck"],
    }]
    if bins != expected:
        raise RunnerConsolidationError("cargo_dispatcher_target_drift")


def _validate_dispatcher(text: str, stems: list[str]) -> None:
    for stem in stems:
        module = f'#[path = "../../tests/{stem}.rs"]\nmod {stem};'
        arm = re.compile(
            rf'"{re.escape(stem)}"\s*=>\s*'
            rf'(?:\{{\s*)?{re.escape(stem)}::main(?:\s*\}})?\s*,?'
        )
        if text.count(module) != 1 or len(arm.findall(text)) != 1:
            raise RunnerConsolidationError(f"dispatcher_binding_drift:{stem}")
    if text.count("=>") != len(stems) + 1:
        raise RunnerConsolidationError("dispatcher_unknown_arm_count")
    if 'std::env::var("SIPI_P4B_RUNNER")' not in text:
        raise RunnerConsolidationError("dispatcher_selector_missing")


def _script_runner(text: str) -> str:
    match = re.search(r'os\.environ\["SIPI_P4B_RUNNER"\] = "([^"]+)"', text)
    if match is None:
        raise RunnerConsolidationError("script_selector_missing")
    normalized = " ".join(text.split())
    if '"--bin", "p4b_02b_crosscheck_runner"' not in normalized:
        raise RunnerConsolidationError("script_dispatcher_build_missing")
    if '"--features", "p4b-self-crosscheck"' not in normalized:
        raise RunnerConsolidationError("script_quarantine_feature_missing")
    if '"--test"' in text or "'--test'" in text:
        raise RunnerConsolidationError("script_legacy_test_target_present")
    return match.group(1)


def validate(root: Path = ROOT) -> dict[str, object]:
    crate = root / "crates" / "sipi-ami-text"
    runners = sorted((crate / "tests").glob("p4b_02b*_runner.rs"))
    stems = [path.stem for path in runners]
    if len(stems) != EXPECTED_RUNNERS or len(stems) != len(set(stems)):
        raise RunnerConsolidationError("runner_inventory_drift")
    _validate_cargo((crate / "Cargo.toml").read_text(encoding="utf-8"))
    _validate_dispatcher(
        (crate / "src" / "bin" / "p4b_02b_crosscheck_runner.rs").read_text(encoding="utf-8"),
        stems,
    )
    library = (crate / "src" / "lib.rs").read_text(encoding="utf-8")
    cfg_line = '#[cfg(any(test, feature = "p4b-self-crosscheck"))]'
    module_count = len(re.findall(r"(?m)^mod (?:ami_|catalog_|parameter_)[A-Za-z0-9_]+;$", library))
    export_count = len(re.findall(r"(?m)^pub use (?:ami_|catalog_|parameter_)[A-Za-z0-9_]+::", library))
    if module_count != EXPECTED_RUNNERS + 2 or export_count != EXPECTED_RUNNERS + 2:
        raise RunnerConsolidationError("quarantined_api_inventory_drift")
    if library.count(cfg_line) != module_count + export_count:
        raise RunnerConsolidationError("quarantined_api_cfg_drift")

    for manifest in (root / "crates").glob("*/Cargo.toml"):
        if manifest == crate / "Cargo.toml":
            continue
        text = manifest.read_text(encoding="utf-8")
        if "p4b-self-crosscheck" in text:
            raise RunnerConsolidationError(f"production_feature_consumer:{manifest.parent.name}")
    for path in runners:
        text = path.read_text(encoding="utf-8")
        if text.count("pub(crate) fn main()") != 1 or re.search(r"(?m)^fn main\(\)", text):
            raise RunnerConsolidationError(f"runner_entrypoint_drift:{path.stem}")

    scripts = sorted((root / "tools").glob("run_p4b_02b*_crosscheck.py"))
    if len(scripts) != EXPECTED_RUNNERS:
        raise RunnerConsolidationError("script_inventory_drift")
    selected = [_script_runner(path.read_text(encoding="utf-8-sig")) for path in scripts]
    if sorted(selected) != stems:
        raise RunnerConsolidationError("script_runner_bijection_drift")

    evidence = sorted((root / "docs" / "baselines").glob("p4b-02b*-crosscheck-evidence.v1.yaml"))
    if len(evidence) != EXPECTED_RUNNERS:
        raise RunnerConsolidationError("evidence_inventory_drift")
    for path in evidence:
        if "status: product_owned_self_crosscheck_unbound" not in path.read_text(encoding="utf-8"):
            raise RunnerConsolidationError(f"evidence_status_drift:{path.name}")

    return {
        "valid": True,
        "runner_sources": len(stems),
        "cargo_targets": 1,
        "scripts": len(scripts),
        "evidence": len(evidence),
        "execution_claim": "not_executed_by_this_verifier",
        "evidence_authority": "product_owned_self_crosscheck_unbound",
        "api_surface": "feature_quarantined_no_production_consumer",
        "quarantined_modules": module_count,
    }


def main() -> int:
    try:
        result = validate(ROOT)
    except RunnerConsolidationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
