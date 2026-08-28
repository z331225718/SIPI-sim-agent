"""Shared bounded fixtures for the COM-02/COM-04 direct semantic replays.

The fixture is deliberately generated in a fresh temporary directory for each
replay.  Reports retain only semantic result fields and SHA-256 identities,
never caller paths or full waveform/result payloads.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCENARIO_TIMEOUT_SECONDS = 30
MAX_SCENARIO_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_RESULT_JSON_BYTES = 16 * 1024 * 1024
MAX_LEGACY_CSV_BYTES = 1024 * 1024
MAX_DFE_TAPS = 256
SOURCE_PATHS = {
    "com-02": [
        "src/agent_com/api.py",
        "src/agent_com/pipeline.py",
        "src/agent_com/network/mixed_mode.py",
        "src/agent_com/signal/interpolation.py",
        "src/agent_com/signal/fd_to_td.py",
        "src/agent_com/equalization/apply.py",
        "src/agent_com/equalization/ctle.py",
        "src/agent_com/equalization/rx_ffe.py",
        "src/agent_com/equalization/search.py",
        "src/agent_com/equalization/mmse.py",
        "src/agent_com/equalization/fvlms_rxffe.py",
        "src/agent_com/equalization/tx_ffe.py",
        "src/agent_com/equalization/dfe.py",
        "src/agent_com/signal/filters.py",
        "src/agent_com/noise/discrete_pdf.py",
        "src/agent_com/metrics/com.py",
        "src/agent_com/metrics/tdiln.py",
        "src/agent_com/runtime.py",
        "src/agent_com/calibration.py",
        "src/agent_com/legacy_csv.py",
        "src/agent_com/reporting.py",
    ],
    "com-04": [
        "src/agent_com/__init__.py",
        "src/agent_com/api.py",
        "src/agent_com/models.py",
        "src/agent_com/config/excel.py",
        "src/agent_com/config/materialize.py",
        "src/agent_com/pipeline.py",
        "src/agent_com/network/mixed_mode.py",
        "src/agent_com/signal/interpolation.py",
        "src/agent_com/signal/fd_to_td.py",
        "src/agent_com/equalization/apply.py",
        "src/agent_com/equalization/ctle.py",
        "src/agent_com/equalization/rx_ffe.py",
        "src/agent_com/equalization/search.py",
        "src/agent_com/equalization/mmse.py",
        "src/agent_com/equalization/fvlms_rxffe.py",
        "src/agent_com/equalization/tx_ffe.py",
        "src/agent_com/equalization/dfe.py",
        "src/agent_com/signal/filters.py",
        "src/agent_com/noise/discrete_pdf.py",
        "src/agent_com/metrics/com.py",
        "src/agent_com/metrics/tdiln.py",
        "src/agent_com/reporting.py",
        "src/agent_com/runtime.py",
        "src/agent_com/calibration.py",
        "src/agent_com/legacy_csv.py",
        "src/agent_com/_orchestration.py",
    ],
}

# Keep the evidence corpus small enough for a bounded replay while exercising
# every portable branch that the COM-02/COM-04 contracts advertise, including
# the pure-Rust MMSE, RxFFE, and calibration leaves.
PORTABLE_SCENARIOS = (
    "base",
    "fd_to_td",
    "mixed_mode",
    "fext_next",
    "equalization",
    "tdiln",
    "search",
    "calibration",
    "mmse",
    "rx_ffe_search",
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bounded_regular_bytes(path: Path, limit: int) -> bytes:
    before = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise RuntimeError("bounded file admission failed")
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise RuntimeError("bounded file budget exceeded")
    after = path.stat(follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError("bounded file identity drift")
    return payload


def bounded_json(path: Path, limit: int) -> Any:
    payload = bounded_regular_bytes(path, limit)
    return json.loads(payload)


def legacy_csv_projection(path: Path) -> dict[str, Any]:
    legacy = bounded_regular_bytes(path, MAX_LEGACY_CSV_BYTES).decode("utf-8")
    lines = legacy.splitlines()
    if not lines or not lines[0]:
        raise RuntimeError("legacy CSV must have a non-empty header")
    return {
        "column_count": len(lines[0].split(",")),
        "header_sha256": digest(lines[0].encode()),
        "row_count": max(0, len(lines) - 1),
    }


def run_scenario_bounded(command: list[str]):
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        deadline = time.monotonic() + SCENARIO_TIMEOUT_SECONDS
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise RuntimeError("scenario subprocess timeout")
            if stdout.tell() > MAX_SCENARIO_OUTPUT_BYTES or stderr.tell() > MAX_SCENARIO_OUTPUT_BYTES:
                process.kill()
                process.wait()
                raise RuntimeError("scenario subprocess output budget exceeded")
            time.sleep(0.01)
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(MAX_SCENARIO_OUTPUT_BYTES + 1)
        err = stderr.read(MAX_SCENARIO_OUTPUT_BYTES + 1)
        if len(out) > MAX_SCENARIO_OUTPUT_BYTES or len(err) > MAX_SCENARIO_OUTPUT_BYTES:
            raise RuntimeError("scenario subprocess output budget exceeded")
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            out.decode("utf-8", "replace"),
            err.decode("utf-8", "replace"),
        )


def parameters() -> dict[str, Any]:
    return {
        "parameters": {
            "samples_per_ui": 8.0,
            "LEVELS": 4.0,
            "bin_size": 0.01,
            "A_v": 0.5,
            "R_LM": 50.0,
            "SNR_TX": 30.0,
            "sigma_X": 0.03,
            "sigma_RJ": 1.0e-4,
            "h_J": [0.3, 0.5, 0.2],
            "sigma_N": 0.01,
            "A_DD": 0.4,
            "spec_ber": 1.0e-4,
            "f2": 50.0e9,
        }
    }


def pulse() -> list[float]:
    return [0.02 * math.sin(index * 0.21) for index in range(64)]


def frequency_domain_trace() -> tuple[list[float], list[list[float]]]:
    """Return a finite one-sided DFT of the fixed impulse fixture.

    The frequency step and sample interval are chosen so FD-to-TD has no
    extrapolation grid.  This keeps the replay focused on interpolation/IFFT
    semantics rather than a second, unrelated fixture generator.
    """
    values = pulse() + [0.0] * 64
    size = len(values)
    frequencies = [index * 1.0e9 for index in range(size // 2 + 1)]
    spectrum = []
    for index in range(size // 2 + 1):
        angle_scale = -2.0 * math.pi * index / size
        real = sum(value * math.cos(angle_scale * sample) for sample, value in enumerate(values))
        imaginary = sum(value * math.sin(angle_scale * sample) for sample, value in enumerate(values))
        spectrum.append([real, imaginary])
    return frequencies, spectrum


def tdiln_trace() -> tuple[list[float], list[list[float]]]:
    frequencies = [index * 1.0e9 for index in range(64)]
    values = []
    for frequency in frequencies:
        magnitude = math.exp(-(frequency / 8.0e10)) * (1.0 + 0.2 * math.sin(frequency / 5.0e9))
        phase = -frequency / 2.0e10
        values.append([magnitude * math.cos(phase), magnitude * math.sin(phase)])
    return frequencies, values


def search_fixture() -> tuple[list[float], dict[str, Any]]:
    """Return the bounded source-shaped fixture for the portable search loop."""
    impulse = [0.0] * 300
    for index in range(300 - 5 * 10):
        impulse[5 * 10 + index] = math.exp(-index / 16.0)
    impulse[5 * 10] = 1.0
    frequencies = [index * 1.0e7 for index in range(200)]
    search = {
        "frequency_hz": frequencies,
        "samples_per_ui": 10,
        "fb_hz": 26.5625e9,
        "tx_ffe_values": {
            "tx_ffe_cm1_values": [0.3],
            "tx_ffe_c0_values": [0.6, 0.8],
            "tx_ffe_cp1_values": [-0.1],
        },
        "tx_ffe_c0_min": 0.2,
        "ts_anchor": 0,
        "local_search": 0.0,
        "ts_sample_adj_range": [-1, 1],
        "include_ctle": True,
        "gdc_min": 0.0,
        "gqual": [[0.0]],
        "g2qual": [0.0],
        "dfe_first_max": 0.5,
        "ctle": {
            "ctle_gdc_values": [6.0],
            "ctle_fz": [10.0e9],
            "ctle_fp1": [30.0e9],
            "ctle_fp2": [40.0e9],
            "ctle_type": "CTLE",
            "f_hp": [0.0],
            "f_hp_z": [5.0e9],
            "f_hp_p": [1.0e9],
        },
        "receiver": {
            "fb_hz": 26.5625e9,
            "btorder": 3,
            "fb_bt_cutoff": 0.75,
            "fb_bw_cutoff": 0.75,
            "rc_start_hz": 8.0e9,
            "rc_end_hz": 12.0e9,
            "eta_0": 1.0e-3,
            "accm_max_freq_hz": 30.0e9,
            "ac_cm_rms": [0.0],
        },
        "candidate": {
            "samples_per_ui": 10,
            "r_lm": 50.0,
            "levels": 4,
            "sigma_x": 0.03,
            "dfe_delta": 1.0e-3,
            "n_tail_start": 0,
            "b_float_rss_max": 0.0,
            "a_dd": 0.1,
            "sigma_rj": 1.0e-4,
            "t_o": 0.0,
            "min_veo_test": 0.0,
            "noise_crest_factor": 0.0,
            "spec_ber": 1.0e-4,
            "samples_for_c2m": 8,
            "ql": 1.0,
            "floating_dfe": False,
            "ndfe": 2,
            "n_bmax": 2,
            "n_bf": 1,
            "n_bg": 1,
            "bmaxg": 0.3,
            "bmax": [0.5, 0.5],
            "bmin": [-0.5, -0.5],
        },
        "options": {
            "ffe_opt_method": "MMSE",
            "rx_ffe_enabled": False,
            "ts_srch_mode": "full-sweep",
            "cdr": "MM",
            "receiver": {
                "bessel_thomson": False,
                "butterworth": False,
                "raised_cosine": False,
                "use_eta0_psd": False,
                "wc_portz": False,
                "pkg_len_select": [1],
            },
            "candidate": {
                "snr_txw_c0": False,
                "wc_portz": False,
                "tx_rd_sel": 1,
                "pkg_len_select": [1],
                "sndr": [30.0],
                "limit_jitter_contrib_to_dfe_span": False,
                "force_pdf_bin_size": False,
                "bin_size": 1.0e-3,
                "force_bbn_q_factor": False,
                "bbn_q_factor": 0.0,
                "histogram_window_weight": "rectangle",
            },
        },
    }
    return impulse, search


def write_fixture(root: Path, scenario: str = "base") -> tuple[Path, Path, Path]:
    if scenario not in PORTABLE_SCENARIOS:
        raise ValueError(f"unknown COM replay scenario: {scenario}")
    document: dict[str, Any] = parameters()
    pulse_payload: Any = pulse()
    pulse_name = "pulse.json"
    if scenario == "fd_to_td":
        frequency_hz, s21 = frequency_domain_trace()
        pulse_payload = {
            "frequency_hz": frequency_hz,
            "s21": s21,
            "fd_to_td": {
                "sample_dt_s": 1.0 / (2.0 * 64.0e9),
                "magnitude_policy": "old",
                "phase_policy": "zero_DC",
                "debug": True,
            },
        }
        pulse_name = "thru-fd.json"
    elif scenario == "mixed_mode":
        frequency_hz, sdd21 = frequency_domain_trace()
        zero = [0.0, 0.0]
        matrices = []
        for value in sdd21:
            matrix = [[zero[:] for _ in range(4)] for _ in range(4)]
            matrix[2][0] = value
            matrix[3][1] = value
            matrices.append(matrix)
        document["portable"] = {
            "mixed_mode": {
                "frequency_hz": frequency_hz,
                "s": matrices,
                "channelize": True,
                "fd_to_td": {
                    "sample_dt_s": 1.0 / (2.0 * 64.0e9),
                    "magnitude_policy": "old",
                    "phase_policy": "zero_DC",
                    "debug": True,
                },
            }
        }
    elif scenario == "fext_next":
        # Exercise the CLI channel-role inputs separately from the generated
        # Apply_EQ aggressors in the equalization scenario.
        document["portable"] = {}
    elif scenario == "equalization":
        thru = pulse()
        document["portable"] = {
            "equalization": {
                "channel_types": ["THRU", "FEXT", "NEXT"],
                "impulses": [
                    thru,
                    [value * 0.2 for value in thru],
                    [value * 0.1 for value in thru],
                ],
                "baud_hz": 25.0e9,
                "samples_per_ui": 4,
                "ctle_type": "CL93",
                "ctle_fz_hz": 0.5e9,
                "ctle_fp1_hz": 1.0e9,
                "ctle_fp2_hz": 2.0e9,
                "ctle_gain_db": 0.0,
                "tx_ffe_taps": [1.0, 0.5],
                "tx_precursor_count": 0,
                "rx_ffe_taps": [0.05, 1.0, -0.1],
                "rx_ffe_precursor_count": 1,
            }
        }
    elif scenario == "tdiln":
        frequency_hz, sdd21 = tdiln_trace()
        document["portable"] = {
            "tdiln": {
                "frequency_hz": frequency_hz,
                "sdd21": sdd21,
                "f1_hz": 0.0,
                "f2_hz": 50.0e9,
                "baud_hz": 25.0e9,
                "samples_per_ui": 4,
                "sample_dt_s": 1.0e-12,
                "levels": 4,
                "spec_ber": 1.0e-4,
                "bin_size": 0.01,
                "bessel_order": 4,
                "bessel_cutoff_multiplier": 1.0,
                "transmitter_transition_time_ns": 0.0,
            }
        }
    elif scenario == "search":
        pulse_payload, search = search_fixture()
        document["portable"] = {"search": search}
    elif scenario == "calibration":
        calibration_pulse = pulse()
        document["package_case"] = {
            "case_id": "calibration-replay-case",
            "pulse": calibration_pulse,
            "fext": [[value * 0.1 for value in calibration_pulse]],
            "next": [[value * 0.05 for value in calibration_pulse]],
        }
        document["portable"] = {
            "calibration": {
                "frequency_hz": [0.0, 1.0, 2.0, 3.0],
                "calibration_sdd21": [[1.0, 0.0]] * 4,
                "ctle_transfer": [[1.0, 0.0]] * 4,
                "fb_hz": 4.0,
                "f_r": 1.0,
                "f_hp_hz": 0.0,
                "sigma_bn_v": 1.0,
                "pass_threshold_db": 2.0,
                "initial_step_v": 2.0,
            }
        }
    elif scenario == "mmse":
        document["portable"] = {
            "mmse": {
                "candidates": [
                    {
                        "h_matrix": [[1.0, 0.1], [0.2, 1.0], [0.1, 0.3]],
                        "noise_correlation": [[0.01, 0.0], [0.0, 0.01]],
                        "decision_index": 0,
                        "dfe_tap_count": 1,
                        "sigma_x2": 1.0,
                        "levels": 4,
                        "r_lm": 50.0,
                        "rx_min": [-2.0, -2.0],
                        "rx_max": [2.0, 2.0],
                        "dfe_min": [-0.5],
                        "dfe_max": [0.5],
                        "rx_cursor_offset": 0,
                        "ctle_index": 2,
                        "high_pass_index": 1,
                        "pre_rx_sbr": [0.1, 1.0, 0.2],
                        "equalized_sbr": [0.0, 1.0, 0.1],
                    }
                ]
            }
        }
    elif scenario == "rx_ffe_search":
        waveform = [0.0] * 32
        for index, value in ((8, 0.01), (12, 0.1), (16, 1.0), (20, 0.05), (24, 0.02), (28, 0.01)):
            waveform[index] = value
        document["portable"] = {
            "rx_ffe_search": {
                "candidates": [
                    {
                        "waveform": waveform,
                        "cursor_index": 16,
                        "precursor_count": 1,
                        "postcursor_count": 2,
                        "samples_per_ui": 4,
                        "unity_cursor": True,
                        "rx_ffe_gain_db": 0.0,
                        "evaluation": {
                            "sigma_n_v": 0.001,
                            "sigma_ne_v": 0.0,
                            "sigma_xt_v": 0.0,
                            "package_case_index": 0,
                            "tx_taps": [1.0],
                            "tx_precursor_count": 0,
                            "tx_grid_index": 0,
                            "tx_source_indices": [0],
                            "itick": 0,
                            "ffe_main_cursor_min": 0.0,
                            "ffe_post_tap1_max": 1.0,
                            "ffe_tapn_max": 1.0,
                            "parameters": {
                                "samples_per_ui": 4,
                                "r_lm": 50.0,
                                "levels": 4,
                                "sigma_x": 0.03,
                                "dfe_delta": 0.0,
                                "n_tail_start": 0,
                                "b_float_rss_max": 0.0,
                                "a_dd": 0.4,
                                "sigma_rj": 0.0001,
                                "t_o": 0.0,
                                "min_veo_test": 0.0,
                                "noise_crest_factor": 0.0,
                                "spec_ber": 0.0001,
                                "samples_for_c2m": 8,
                                "ql": 1.0,
                                "floating_dfe": False,
                                "ndfe": 1,
                                "n_bmax": 1,
                                "n_bf": 1,
                                "n_bg": 0,
                                "bmaxg": 0.3,
                                "bmax": [0.5],
                                "bmin": [-0.5],
                            },
                            "options": {
                                "snr_txw_c0": False,
                                "wc_portz": False,
                                "tx_rd_sel": 0,
                                "pkg_len_select": [1],
                                "sndr": [30.0],
                                "limit_jitter_contrib_to_dfe_span": False,
                                "force_pdf_bin_size": False,
                                "bin_size": 0.01,
                                "force_bbn_q_factor": False,
                                "bbn_q_factor": 0.0,
                                "histogram_window_weight": "rectangle",
                            },
                        },
                    }
                ]
            }
        }
    config = root / "params.json"
    pulse_path = root / pulse_name
    output = root / "artifacts"
    config.write_text(json.dumps(document, sort_keys=True), encoding="utf-8", newline="\n")
    pulse_path.write_text(json.dumps(pulse_payload, separators=(",", ":")), encoding="utf-8", newline="\n")
    if scenario == "fext_next":
        (root / "fext.json").write_text(
            json.dumps([value * 0.2 for value in pulse()], separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )
        (root / "next.json").write_text(
            json.dumps([value * 0.1 for value in pulse()], separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )
    return config, pulse_path, output


def semantic_projection(result: dict[str, Any], workflow: list[str]) -> dict[str, Any]:
    case = result["cases"][0]
    metrics = case["metrics"]
    diagnostics = case.get("diagnostics", {})
    waveform = diagnostics.get("channel_impulse", {})
    channels = {
        "fext": case["channels"]["fext"],
        "next": case["channels"]["next"],
        "calibration_noise": case["channels"]["calibration_noise"],
    }
    # Input paths are intentionally not comparable across fresh temporary
    # replays. Preserve their waveform semantics from the diagnostics sidecar
    # while retaining the empty shape for scenarios without CLI aggressors.
    crosstalk = diagnostics.get("crosstalk_inputs", {})
    if channels["fext"] or channels["next"]:
        channels = {
            "fext": [
                {
                    key: entry.get(key)
                    for key in ("sample_count", "sample_interval_s", "source_kind", "impulse_sha256")
                }
                for entry in crosstalk.get("fext", [])
            ],
            "next": [
                {
                    key: entry.get(key)
                    for key in ("sample_count", "sample_interval_s", "source_kind", "impulse_sha256")
                }
                for entry in crosstalk.get("next", [])
            ],
            "calibration_noise": None,
        }
    projection = {
        "workflow": workflow,
        "case_index": case["case_index"],
        "channels": channels,
        "metrics": {
            key: metrics[key]
            for key in (
                "FOM",
                "COM_dB",
                "VEC_dB",
                "VEO_mV",
                "sigma_N_V",
                "available_signal_v",
                "interference_noise_v",
                "threshold_der",
                "eye_opening_v",
                "calibration_sigma_bn_v",
                "calibration_sigma_ne_v",
                "calibration_sigma_hp_v",
            )
        },
        "waveform": {
            "sample_count": waveform["sample_count"],
            "sha256": waveform["sha256"],
            "source_kind": waveform["source_kind"],
            "causality_correction_db": waveform.get("causality_correction_db"),
            "truncation_db": waveform.get("truncation_db"),
            "causality_iterations": waveform.get("causality_iterations"),
        },
        "crosstalk_inputs": diagnostics.get("crosstalk_inputs", {}),
        "portable_branches": diagnostics.get("portable_branches", {}),
        "report_manifest": result.get("report_manifest"),
    }
    search = diagnostics.get("portable_branches", {}).get("search")
    if search is not None:
        taps = search.get("dfe_taps")
        if (
            not isinstance(taps, list)
            or not taps
            or len(taps) > MAX_DFE_TAPS
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in taps
            )
        ):
            raise RuntimeError("candidate search winner did not publish DFE taps")
        projection["candidate_execution_observations"] = {
            "search_winner_dfe_taps": taps,
            "result_path": "cases[].diagnostics.portable_branches.search.dfe_taps",
        }
    return projection


def invoke_scenario(binary: Path, mode: str, root: Path, scenario: str) -> dict[str, Any]:
    scenario_root = root / scenario
    scenario_root.mkdir()
    config, pulse_path, output = write_fixture(scenario_root, scenario)
    command = [str(binary)]
    if mode == "com-02":
        command.append("run")
    command.extend(
        [
            "--config",
            str(config),
            "--thru",
            str(pulse_path),
            "--output-dir",
            str(output),
        ]
    )
    if scenario == "fext_next":
        command.extend(
            ["--fext", str(scenario_root / "fext.json"), "--next", str(scenario_root / "next.json")]
        )
    if scenario == "base":
        command.append("--legacy-csv")
    completed = run_scenario_bounded(command)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{mode}/{scenario} direct leaf failed: {completed.stderr.strip()}"
        )
    envelope = json.loads(completed.stdout)
    result_path = output / "result.json"
    result = bounded_json(result_path, MAX_RESULT_JSON_BYTES)
    semantic = semantic_projection(result, ["load_config", "run_com", "write_artifacts"])
    legacy_path = output / "legacy.csv"
    if legacy_path.is_file():
        semantic["legacy_csv"] = legacy_csv_projection(legacy_path)
    semantic["scenario"] = scenario
    return {
        "scenario": scenario,
        "exit_code": completed.returncode,
        "semantic": semantic,
        "semantic_sha256": digest(
            json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
        ),
        "result_schema": result["schema_version"],
        "source_revision": result["source_revision"],
        "artifact_files": sorted(path.name for path in output.iterdir()),
        "binary_schema": envelope["schema"],
    }


def invoke(binary: Path, mode: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"sipi-{mode}-replay-") as directory:
        root = Path(directory)
        scenarios = [invoke_scenario(binary, mode, root, scenario) for scenario in PORTABLE_SCENARIOS]
        semantic = {"scenarios": [scenario["semantic"] for scenario in scenarios]}
        return {
            "mode": mode,
            "exit_code": 0,
            "semantic": semantic,
            "semantic_sha256": digest(
                json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
            ),
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
        }


def run_report(binary: Path, mode: str, run_id: str) -> dict[str, Any]:
    first = invoke(binary, mode)
    second = invoke(binary, mode)
    if first["semantic"] != second["semantic"]:
        raise RuntimeError(f"{mode} independent semantic replays differ")
    return {
        "schema": f"sipi.{mode}.direct-semantic-replay.v1",
        "run_id": run_id,
        "source": {
            "repository": "https://github.com/z331225718/agent-com.git",
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
            "declared_license": "MIT",
            "reachable_paths": SOURCE_PATHS[mode],
        },
        "candidate": {
            "status": "unbound_observation",
            "reason": "semantic replay uses the caller-provided current binary",
        },
        "mode": mode,
        "replay_count": 2,
        "scenario_count": len(PORTABLE_SCENARIOS),
        "semantic_replays_identical": True,
        "replays": [first, second],
        "semantic_payload_fields": [
            "scenarios[].scenario",
            "cases[].case_index",
            "cases[].channels",
            "cases[].metrics.COM_dB/VEC_dB/VEO_mV/sigma_N_V",
            "cases[].metrics.FOM (portable search selection when requested)",
            "cases[].metrics.available_signal_v/interference_noise_v/threshold_der/eye_opening_v",
            "cases[].metrics.calibration_sigma_bn_v/calibration_sigma_ne_v/calibration_sigma_hp_v",
            "cases[].diagnostics.channel_impulse",
            "cases[].diagnostics.crosstalk_inputs",
            "cases[].diagnostics.portable_branches",
            "report_manifest",
        ],
        "portable_semantic_branches": [
            "fd_to_td_json",
            "mixed_mode_pn_skew",
            "fext_next_waveform_inputs",
            "equalization_apply",
            "tdiln",
            "search_nonmmse_no_rxffe",
            "mmse_kkt_search",
            "fvlms_rxffe_search",
            "calibration_noise_controller",
            "workbook_csv_mat_reuse",
            "legacy_csv_projection",
        ],
        "unsupported_fail_closed": [
            "matlab_only_reporting",
            "wiener_hopf_source_unimplemented",
        ],
        "payloads_committed": False,
    }


def redact_for_report(report: dict[str, Any]) -> dict[str, Any]:
    # Keep only deterministic fields; invoke() already excludes temp paths.
    return json.loads(json.dumps(report, sort_keys=True))
