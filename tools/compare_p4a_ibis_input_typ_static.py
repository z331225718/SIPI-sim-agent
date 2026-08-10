"""Externally compare the selected IBIS Input/TYP DC-clamp profile twice.

This oracle-only tool keeps the official IBIS bytes, selector spelling, raw
tables, temporary requests, and product result values outside the worktree.
It invokes a test-only Rust runner and publishes only hashes and comparison
metrics in an operator-selected external report path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-ibis-input-typ-static-acceptance.v1.yaml"
RUNNER = ROOT / "crates" / "sipi-ibis" / "tests" / "p4a_dc_clamp_external_runner.rs"
LOCK = ROOT / "Cargo.lock"
SCHEMA = "sipi.p4a.ibis-input-typ-static-compare.v1"
REQUEST_SCHEMA = "sipi.p4a.dc-clamp-product-runner-request.v1"
RESULT_SCHEMA = "sipi.p4a.dc-clamp-product-runner-result.v1"
FINGERPRINT_DOMAIN = b"sipi.ibis.dc-clamp-table.v1\0"
EXPECTED_PROBE_COUNT = 6


class CompareError(RuntimeError):
    """A fail-closed external profile comparison error."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_charter(path: Path) -> tuple[dict, str]:
    if yaml is None:
        raise CompareError("pyyaml_unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompareError("charter_not_object")
    required = {"schema", "status", "profile", "stimulus", "observable", "comparison", "non_claims"}
    if set(value) != required or value["schema"] != "sipi.p4a-ibis-input-typ-static-acceptance.v1":
        raise CompareError("charter_shape_invalid")
    if value["status"] != "required_pending_i_v_compare":
        raise CompareError("charter_status_invalid")
    source = value["profile"].get("source") if isinstance(value["profile"], dict) else None
    comparison = value.get("comparison")
    probes = value["stimulus"].get("voltage_v") if isinstance(value["stimulus"], dict) else None
    if (
        not isinstance(source, dict)
        or not isinstance(comparison, dict)
        or not isinstance(probes, list)
        or len(probes) != EXPECTED_PROBE_COUNT
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in probes)
        or value["profile"].get("boundary") != "external_oracle_only"
        or value["profile"].get("corner") != "typical"
        or value["observable"].get("c_comp_contribution") != "zero_at_dc"
    ):
        raise CompareError("charter_scope_invalid")
    for key in ("canonical_url", "content_sha256", "byte_length", "selector_utf8_sha256"):
        if key not in source:
            raise CompareError("charter_source_invalid")
    if not all(isinstance(source[key], str) and len(source[key]) == 64 for key in ("content_sha256", "selector_utf8_sha256")):
        raise CompareError("charter_hash_invalid")
    return value, sha256_bytes(canonical_json(value))


def strip_comment(line: str) -> str:
    return line.split("|", 1)[0].strip()


def header(line: str) -> tuple[str, str] | None:
    stripped = strip_comment(line)
    if not stripped.startswith("[") or "]" not in stripped:
        return None
    end = stripped.find("]")
    name = stripped[1:end].strip()
    tail = stripped[end + 1 :].strip()
    if not name:
        raise CompareError("external_empty_header")
    return name, tail


def parse_scaled(token: str, unit: str) -> float:
    lower = token.lower()
    for prefix, scale in (("meg", 1e6), ("g", 1e9), ("k", 1e3), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15), ("", 1.0)):
        suffix = prefix + unit
        if lower.endswith(suffix):
            number = lower[: -len(suffix)] if suffix else lower
            try:
                value = float(number) * scale
            except ValueError as error:
                raise CompareError("external_scaled_value_invalid") from error
            if math.isfinite(value):
                return value
            raise CompareError("external_scaled_value_nonfinite")
    if unit in {"v", "a"}:
        try:
            value = float(token)
        except ValueError as error:
            raise CompareError("external_bare_value_invalid") from error
        if math.isfinite(value):
            return value
    raise CompareError("external_unit_invalid")


def table_fingerprint(tables: tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]) -> str:
    digest = hashlib.sha256(FINGERPRINT_DOMAIN)
    for label, table in zip((b"gnd", b"power"), tables, strict=True):
        digest.update(len(label).to_bytes(8, "big"))
        digest.update(label)
        digest.update(len(table).to_bytes(8, "big"))
        for voltage, current in table:
            digest.update(struct.pack(">Q", struct.unpack(">Q", struct.pack(">d", voltage))[0]))
            digest.update(struct.pack(">Q", struct.unpack(">Q", struct.pack(">d", current))[0]))
    return digest.hexdigest()


def extract_raw_profile(data: bytes, selector_sha256: str) -> tuple[str, str, tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise CompareError("external_asset_not_ascii") from error
    version = None
    models: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        parsed = header(line)
        if parsed is None:
            continue
        name, tail = parsed
        if name.lower() == "ibis ver":
            if version is not None or len(tail.split()) != 1:
                raise CompareError("external_version_ambiguous")
            version = tail
        elif name.lower() == "model":
            tokens = tail.split()
            if len(tokens) != 1:
                raise CompareError("external_model_header_invalid")
            models.append((index, tokens[0]))
    if version is None:
        raise CompareError("external_version_missing")
    selected = [(index, name) for index, name in models if sha256_bytes(name.encode("utf-8")) == selector_sha256]
    if len(selected) != 1:
        raise CompareError("external_selector_not_unique")
    start, selector = selected[0]
    end = next((index for index, _ in models if index > start), len(lines))
    scope = lines[start + 1 : end]
    model_types = [strip_comment(line).split() for line in scope if strip_comment(line).split()[:1] and strip_comment(line).split()[0].lower() == "model_type"]
    if len(model_types) != 1 or len(model_types[0]) != 2 or model_types[0][1].lower() != "input":
        raise CompareError("external_model_type_not_input")
    c_comp_rows = [strip_comment(line).split() for line in scope if strip_comment(line).split()[:1] and strip_comment(line).split()[0].lower() == "c_comp"]
    if len(c_comp_rows) != 1 or len(c_comp_rows[0]) < 2 or parse_scaled(c_comp_rows[0][1], "f") < 0.0:
        raise CompareError("external_c_comp_invalid")
    if any((parsed := header(line)) is not None and parsed[0].lower() == "algorithmic model" for line in scope):
        raise CompareError("external_algorithmic_model_present")

    def read_table(expected: str) -> tuple[tuple[float, float], ...]:
        indices = [index for index, line in enumerate(scope) if (parsed := header(line)) is not None and parsed[0].lower() == expected]
        if len(indices) != 1:
            raise CompareError("external_clamp_section_invalid")
        start_index = indices[0] + 1
        rows: list[tuple[float, float]] = []
        for line in scope[start_index:]:
            if header(line) is not None:
                break
            tokens = strip_comment(line).split()
            if not tokens:
                continue
            if len(tokens) < 2:
                raise CompareError("external_clamp_row_invalid")
            rows.append((parse_scaled(tokens[0], "v"), parse_scaled(tokens[1], "a")))
        if len(rows) < 2 or any(left[0] >= right[0] for left, right in zip(rows, rows[1:], strict=False)):
            raise CompareError("external_clamp_table_invalid")
        return tuple(rows)

    return selector, version, read_table("gnd_clamp"), read_table("power_clamp")


def interpolate(table: tuple[tuple[float, float], ...], voltage: float) -> float:
    if voltage < table[0][0] or voltage > table[-1][0]:
        raise CompareError("external_probe_out_of_domain")
    for (lower_v, lower_i), (upper_v, upper_i) in zip(table, table[1:], strict=False):
        if voltage == lower_v:
            return lower_i
        if voltage <= upper_v:
            return lower_i + ((voltage - lower_v) / (upper_v - lower_v)) * (upper_i - lower_i)
    return table[-1][1]


def raw_observation(gnd: tuple[tuple[float, float], ...], power: tuple[tuple[float, float], ...], probes: list[float]) -> list[dict]:
    return [
        {
            "voltage_v": voltage,
            "gnd_current_a": interpolate(gnd, voltage),
            "power_current_a": interpolate(power, voltage),
            "total_current_a": interpolate(gnd, voltage) + interpolate(power, voltage),
            "capacitive_current_a": 0.0,
        }
        for voltage in probes
    ]


def write_request(root: Path, asset: bytes, selector: str, probes: list[float], charter: dict, charter_sha256: str) -> Path:
    asset_path = root / "asset.ibs"
    selector_path = root / "selector.txt"
    probe_path = root / "probes.f64le"
    request_path = root / "request.txt"
    asset_path.write_bytes(asset)
    selector_path.write_bytes(selector.encode("utf-8"))
    probe_path.write_bytes(b"".join(struct.pack("<d", value) for value in probes))
    source = charter["profile"]["source"]
    request_path.write_text(
        "\n".join(
            [
                f"schema={REQUEST_SCHEMA}",
                "asset=asset.ibs",
                f"asset_sha256={source['content_sha256']}",
                f"asset_byte_length={source['byte_length']}",
                "selector=selector.txt",
                f"selector_sha256={source['selector_utf8_sha256']}",
                "probes=probes.f64le",
                f"charter_sha256={charter_sha256}",
                "result=result.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return request_path


def run_product(root: Path, request: Path, cargo: Path) -> tuple[dict, dict]:
    environment = os.environ.copy()
    environment.update(
        {
            "SIPI_P4A_DC_CLAMP_RUNNER_REQUEST": str(request),
            "CARGO_TARGET_DIR": str(root / "cargo-target"),
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
        }
    )
    completed = subprocess.run(
        [str(cargo), "test", "-p", "sipi-ibis", "--test", "p4a_dc_clamp_external_runner", "--locked", "--", "--ignored", "--exact", "p4a_dc_clamp_external_runner"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=False,
        check=False,
    )
    result_path = root / "result.json"
    if completed.returncode != 0 or not result_path.is_file():
        raise CompareError("product_runner_failed")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompareError("product_result_invalid") from error
    evidence = {
        "returncode": completed.returncode,
        "stdout_sha256": sha256_bytes(completed.stdout),
        "stderr_sha256": sha256_bytes(completed.stderr),
        "result_sha256": sha256_file(result_path),
    }
    return result, evidence


def compare_product(raw: list[dict], product: dict, charter: dict, charter_sha256: str, source: dict, fingerprint: str) -> dict:
    required = {"schema", "status", "asset_sha256", "asset_byte_length", "selector_sha256", "charter_sha256", "table_fingerprint", "probes"}
    if not isinstance(product, dict) or set(product) != required:
        raise CompareError("product_result_shape_invalid")
    if (
        product["schema"] != RESULT_SCHEMA
        or product["status"] != "ok"
        or product["asset_sha256"] != source["content_sha256"]
        or product["asset_byte_length"] != source["byte_length"]
        or product["selector_sha256"] != source["selector_utf8_sha256"]
        or product["charter_sha256"] != charter_sha256
        or product["table_fingerprint"] != fingerprint
        or not isinstance(product["probes"], list)
        or len(product["probes"]) != EXPECTED_PROBE_COUNT
    ):
        raise CompareError("product_provenance_mismatch")
    absolute = float(charter["comparison"]["absolute_tolerance_a"])
    relative = float(charter["comparison"]["relative_tolerance"])
    max_abs = 0.0
    max_rel = 0.0
    worst = 0
    for index, (expected, actual) in enumerate(zip(raw, product["probes"], strict=True)):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise CompareError("product_probe_shape_invalid")
        for key in ("voltage_v", "gnd_current_a", "power_current_a", "total_current_a", "capacitive_current_a"):
            value = actual[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CompareError("product_probe_value_invalid")
        if actual["voltage_v"] != expected["voltage_v"] or actual["capacitive_current_a"] != 0.0:
            raise CompareError("product_probe_alignment_invalid")
        for key in ("gnd_current_a", "power_current_a", "total_current_a"):
            difference = abs(float(actual[key]) - expected[key])
            scale = max(abs(float(actual[key])), abs(expected[key]))
            limit = absolute + relative * scale
            if difference > limit:
                raise CompareError("product_numeric_drift")
            if difference > max_abs:
                max_abs, worst = difference, index
            if scale:
                max_rel = max(max_rel, difference / scale)
    return {"max_abs_error_a": max_abs, "max_rel_error": max_rel, "worst_probe_index": worst}


def fetch_asset(url: str, expected_sha256: str, expected_length: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "ibis.org":
        raise CompareError("canonical_url_not_official_https")
    request = Request(url, headers={"User-Agent": "SIPI-P4A-observer/1"})
    try:
        with urlopen(request, timeout=30) as response:
            final = urlparse(response.geturl())
            if response.status != 200 or final.scheme != "https" or final.hostname != "ibis.org":
                raise CompareError("external_transport_policy_failed")
            data = response.read(expected_length + 1)
    except OSError as error:
        raise CompareError("external_download_failed") from error
    if len(data) != expected_length or sha256_bytes(data) != expected_sha256:
        raise CompareError("external_asset_identity_mismatch")
    return data


def compare_once(charter: dict, charter_sha256: str, cargo: Path) -> dict:
    source = charter["profile"]["source"]
    probes = [float(value) for value in charter["stimulus"]["voltage_v"]]
    with tempfile.TemporaryDirectory(prefix="sipi-p4a-ibis-") as temporary:
        root = Path(temporary)
        asset = fetch_asset(source["canonical_url"], source["content_sha256"], source["byte_length"])
        selector, _version, gnd, power = extract_raw_profile(asset, source["selector_utf8_sha256"])
        fingerprint = table_fingerprint((gnd, power))
        raw = raw_observation(gnd, power, probes)
        request = write_request(root, asset, selector, probes, charter, charter_sha256)
        product, runner = run_product(root, request, cargo)
        metrics = compare_product(raw, product, charter, charter_sha256, source, fingerprint)
        return {
            "asset_sha256": source["content_sha256"],
            "selector_sha256": source["selector_utf8_sha256"],
            "table_fingerprint": fingerprint,
            "raw_observation_sha256": sha256_bytes(canonical_json(raw)),
            "runner": runner,
            "metrics": metrics,
        }


def run_compare(report: Path, cargo: Path, charter_path: Path) -> dict:
    charter, charter_sha256 = load_charter(charter_path)
    if report.resolve().is_relative_to(ROOT.resolve()):
        raise CompareError("report_must_be_outside_worktree")
    if not cargo.is_file() or not RUNNER.is_file() or not LOCK.is_file():
        raise CompareError("product_runner_inputs_missing")
    first = compare_once(charter, charter_sha256, cargo)
    second = compare_once(charter, charter_sha256, cargo)
    replay_keys = ("asset_sha256", "selector_sha256", "table_fingerprint", "raw_observation_sha256")
    if any(first[key] != second[key] for key in replay_keys):
        raise CompareError("custody_replay_mismatch")
    if first["runner"]["result_sha256"] != second["runner"]["result_sha256"]:
        raise CompareError("product_replay_mismatch")
    return {
        "schema": SCHEMA,
        "status": "accepted",
        "profile_id": charter["profile"]["id"],
        "charter_sha256": charter_sha256,
        "asset_sha256": first["asset_sha256"],
        "selector_sha256": first["selector_sha256"],
        "table_fingerprint": first["table_fingerprint"],
        "runner_source_sha256": sha256_file(RUNNER),
        "cargo_lock_sha256": sha256_file(LOCK),
        "runs": [first, second],
        "non_claims": [
            "The external asset, selector, raw tables, requests, and probe values remain outside the worktree.",
            "This covers only the selected Input/TYP static DC clamp profile and not package, PVT, V-T, ramp, AMI, or general IBIS behavior.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--charter", type=Path, default=CHARTER)
    args = parser.parse_args()
    try:
        result = run_compare(args.report, args.cargo, args.charter)
    except (CompareError, OSError, ValueError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    if args.report.resolve().is_relative_to(ROOT.resolve()):
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
