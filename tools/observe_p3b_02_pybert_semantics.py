"""Observe pinned PyBERT equalizer semantics without copying source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
SCHEMA = "sipi.p3b-02.pybert-source-semantic-observation.v1"
PRODUCT = ROOT / "crates/sipi-link/src/rx_ctle_ffe_v1.rs"

OBJECT_MARKERS: dict[str, tuple[str, ...]] = {
    "src/pybert/models/bert.py": (
        "def _get_native_ctle_impulse",
        "make_ctle(rx_bw, peak_freq, peak_mag, w)",
        "impulse = irfft(ctle_H)",
        "kernel = interp1d(t_irfft, impulse, bounds_error=False, fill_value=0)",
        "ctle_h *= sum(impulse) / sum(ctle_h)",
        "ctle_h, _ = trim_impulse(ctle_h, front_porch=False, min_len=min_len, max_len=max_len)",
        "def _run_rx_ffe_stage",
        "ffe_out = _sparse_tapped_convolve(ctle_out, ffe_h, len(ctle_out))",
        "ffe_out = _linear_convolve(ctle_out, ffe_h)[:len(ctle_out)]",
    ),
    "src/pybert/pybert.py": (
        "gPeakFreq",
        "gPeakMag",
        "gNtaps",
    ),
    "src/pybert_web/models.py": (
        "ffe_weights: list[float]",
        "cursor_pos: int",
        "peak_mag: float = Field(default=4.0",
        "ctle_enable: bool = True",
    ),
    "src/pybert_web/engine_adapter.py": (
        '"peakMagnitudeDb": rx.peak_mag',
        '"cursorPosition": 5',
        '"ffe": {',
        "receive FFE",
    ),
    "native/pybert-core/src/equalization.rs": (
        "pub struct CtleConfig",
        "pub fn ctle_frequency_response",
        "pub fn ctle_impulse_response",
        "pub fn ffe_impulse_response",
        "pub fn apply_ffe",
    ),
    "native/pybert-core/src/input.rs": (
        "pub struct FfeConfigV1",
        "pub cursor_position: usize",
        "pub struct CtleConfigV1",
        "pub native_ctle_enabled: bool",
    ),
    "native/pybert-core/src/simulation.rs": (
        "let rx_filter",
        "let ctle_output",
        "let rx_ffe_weights",
        "sparse_tapped_convolve_truncated(&ctle_output",
    ),
}
LICENSE_BLOB = "64d198ba43675ede5fbdef1ec918a63954951640"


class ObservationError(ValueError):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    if result.returncode != 0:
        raise ObservationError("external_git_object_unavailable")
    return result.stdout


def _blob(repo: Path, path: str) -> str:
    return _git(repo, "rev-parse", f"{COMMIT}:{path}").strip()


def _source(repo: Path, path: str) -> str:
    return _git(repo, "show", f"{COMMIT}:{path}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(source: str, pattern: str, label: str) -> float:
    match = re.search(pattern, source, flags=re.DOTALL)
    if match is None:
        raise ObservationError(f"source_value_missing:{label}")
    return float(match.group(1))


def observe(pybert_root: Path) -> dict[str, Any]:
    try:
        pybert_root.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ObservationError("external_repo_must_not_be_inside_repository")
    if _git(pybert_root, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise ObservationError("external_repo_invalid")
    if _git(pybert_root, "rev-parse", f"{COMMIT}^{{tree}}").strip() != TREE:
        raise ObservationError("external_tree_drift")

    objects: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    for path, markers in OBJECT_MARKERS.items():
        blob = _blob(pybert_root, path)
        source = _source(pybert_root, path)
        missing = [marker for marker in markers if marker not in source]
        if missing:
            raise ObservationError(f"source_marker_missing:{path}:{missing[0]}")
        objects[path] = {
            "git_blob_sha1": blob,
            "markers": list(markers),
            "marker_presence_verified": True,
        }
        sources[path] = source

    legacy = sources["src/pybert/pybert.py"]
    web = sources["src/pybert_web/models.py"]
    adapter = sources["src/pybert_web/engine_adapter.py"]
    return {
        "schema": SCHEMA,
        "status": "observed_product_semantics_external_profile_required",
        "product": {
            "path": "crates/sipi-link/src/rx_ctle_ffe_v1.rs",
            "sha256": _sha256(PRODUCT),
            "policy": "sipi.p3b-02.rx-ctle-ffe-explicit-semantics-v1",
            "wire_v1": "bypass_only_unchanged",
            "runtime_surface": "in_memory_caller_supplied_only",
        },
        "semantics": {
            "chain_order": ["RX CTLE", "RX FFE"],
            "stage_selection": "explicit_per_stage_bypass_or_caller_profile",
            "ctle": {
                "transfer_representation": "caller_supplied_causal_time_domain_impulse",
                "grid": "explicit_uniform_sample_interval_count_and_input_sample_zero_origin",
                "normalization": "explicit_none_unit_sum_or_peak_abs_target",
                "state": "explicit_zero_initial",
            },
            "ffe": {
                "tap_order": "explicit_ascending_or_descending_time",
                "cursor": "explicit_index_and_output_origin_convention",
                "units": "explicit_normalized_voltage_ratio",
                "sign": "explicit_direct_or_negated",
                "domain": "explicit_sample_spaced_or_ui_spaced",
                "state": "explicit_zero_initial",
            },
            "shared": {
                "timebase": "uniform_zero_origin_input_and_exact_stage_interval_match",
                "output": "full_linear_causal_convolution_with_negative_precursor_axis_when_selected",
                "bounds": "caller_supplied_output_and_mac_limits_fail_closed",
                "kernel": "sipi_link_convolve_causal_fir_v1_via_named_prerequisite",
                "tuning": "no_auto_tune_or_silent_fallback",
            },
        },
        "external_source": {
            "repository": "Py-bert-agent",
            "commit": COMMIT,
            "tree": TREE,
            "custody": "external_only_hash_bound",
            "license": {"spdx": "BSD-3-Clause", "path": "LICENSE", "git_blob": LICENSE_BLOB},
            "objects": objects,
        },
        "source_observations": {
            "legacy_ctle": {
                "source": "src/pybert/models/bert.py",
                "semantic": "make_ctle_to_irfft_to_interp1d_to_sum_normalization_to_trim",
            },
            "legacy_ffe": {
                "source": "src/pybert/models/bert.py",
                "semantic": "sample_spaced_taps_after_ctle_with_sparse_or_linear_convolution_truncated_to_input",
            },
            "default_conflict": {
                "legacy_peak_magnitude_db": _number(legacy, r"gPeakMag\s*=\s*([0-9.]+)", "legacy_peak"),
                "web_peak_magnitude_db": _number(web, r"peak_mag:\s*float\s*=\s*Field\(default=([0-9.]+)", "web_peak"),
                "web_rx_cursor_position": _number(
                    adapter,
                    r'"rx":\s*\{.*?"cursorPosition":\s*([0-9]+)',
                    "web_rx_cursor",
                ),
                "profile_selection": None,
                "selection_by_oracle_closeness": False,
            },
        },
        "profile_status": {
            "selected_profile": None,
            "required": "external_asset_oracle",
            "reason": "pinned source semantics are observed but conflicting defaults do not mechanically select one profile",
        },
        "non_claims": [
            "No PyBERT source bytes are stored or redistributed by this report.",
            "The observation is not external numeric parity or acceptance.",
            "The product does not select a profile by oracle closeness.",
            "The v1 bypass-only wire contract is unchanged.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pybert-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = observe(arguments.pybert_root.resolve())
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="ascii",
            newline="\n",
        )
    except (OSError, ObservationError, ValueError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "report_sha256": _sha256(arguments.report)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
