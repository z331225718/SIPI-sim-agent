"""Fail closed on the P4B-07c RX AMI_Init probe-surface exploration.

The exploration evidence records the RX fixture's AMI_Init outcome across
four documented matrix variants in two fresh custodies: all variants
crash reproducibly (0xC0000005). The verifier binds the evidence, the
material registry RX hash, and the PLAN P4B-07c row; no DLL-internal
claim is made.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-07-rx-init-surface-exploration-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-07.rx-init-surface-exploration-evidence.v1"
RX_DLL = "88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63"
VARIANTS = ["identity_like", "decay", "uniform", "decay_coupled"]


class ExplorationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExplorationError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "rx_init_probe_surface_explored_documented_variants":
        raise ExplorationError("evidence_schema_or_status_invalid")
    if evidence.get("dll_sha256") != RX_DLL:
        raise ExplorationError("evidence_dll_hash_drift")
    variants = evidence.get("variants")
    if not isinstance(variants, dict) or set(variants) != set(VARIANTS):
        raise ExplorationError("variants_drift")
    for variant in VARIANTS:
        result = variants.get(variant)
        if not isinstance(result, dict) or not result.get("reproducible"):
            raise ExplorationError(f"variant_not_reproducible:{variant}")
        if result.get("init_succeeded"):
            raise ExplorationError(f"variant_unexpectedly_succeeded:{variant}")
        for custody in ("custody_0", "custody_1"):
            observation = result.get(custody)
            if observation is None or observation.get("status") != "probe_crash" or observation.get("rc") != 3221225477:
                raise ExplorationError(f"variant_crash_mismatch:{variant}:{custody}")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-07c" not in plan_text:
        raise ExplorationError("plan_row_missing")
    return {"valid": True, "variants": len(VARIANTS), "crash_rc": 3221225477}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ExplorationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
