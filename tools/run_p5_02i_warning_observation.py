"""P5-02i external-only warning-call observation.

Records every warning / fprintf(<strong> Warning / msgbox('...','warning')
call site in the owner-authorized MATLAB r4.80 source, hash-bound, as the
oracle basis for the R480 warning contract. Observations only; the
product warning contract itself awaits the behavior profile.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
OBSERVATION = ROOT / "docs" / "baselines" / "p5-r480-warning-observation.v1.yaml"
OBSERVATION_SCHEMA = "sipi.p5-02.warning-observation.v1"
MATLAB_ID = "com-r480-matlab-source"
WARNING_RE = re.compile(r"warning\s*\(\s*'([^']*)'")
FPRINTF_RE = re.compile(r"fprintf\s*\(\s*'<strong>\s*([^']*?)</strong>'")
MSGBOX_RE = re.compile(r"msgbox\s*\(\s*'([^']*)'\s*,\s*'warning'")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    material = next((m for m in registry["materials"] if m["id"] == MATLAB_ID), None)
    if material is None:
        raise SystemExit("matlab source not registered")
    source = Path(str(material["path"]).replace("/", "\\"))
    actual = sha256_file(source)
    if actual != material["sha256"].lower():
        raise SystemExit("source hash drift")
    lines = source.read_text(encoding="utf-8").splitlines()
    warnings = []
    for line_number, line in enumerate(lines, 1):
        for pattern, kind in ((WARNING_RE, "warning"), (FPRINTF_RE, "fprintf_strong"), (MSGBOX_RE, "msgbox_warning")):
            match = pattern.search(line)
            if match is not None:
                warnings.append({"line": line_number, "kind": kind, "message": match.group(1)})
    observation = {
        "schema": OBSERVATION_SCHEMA,
        "status": "warning_calls_observed_hash_bound",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "source_sha256": actual,
        "warning_call_count": len(warnings),
        "warnings": warnings,
        "non_claims": [
            "not_a_product_warning_contract",
            "not_warning_conditions_derived",
            "not_release_evidence",
        ],
    }
    OBSERVATION.write_text(yaml.safe_dump(observation, sort_keys=False), encoding="utf-8")
    print("warning calls observed: " + str(len(warnings)))
    print("observation written: " + str(OBSERVATION))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
