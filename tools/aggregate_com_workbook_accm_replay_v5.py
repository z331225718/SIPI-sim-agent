"""Aggregate two additive COM v5 diagnostic reports.

This is a strict evidence gate, not a parity or release claim.  It accepts
only the complete report shape emitted by the hardened runner.  In
particular, both reports must prove the same pinned source, fixture,
toolchain, and typed projections while retaining distinct nonce-bound scratch
roots.  Candidate port order is deliberately required to remain
``false/false/not_observed`` until the product publishes an applied-order
diagnostic.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from tools import run_com_workbook_accm_replay_v5 as runner
except ModuleNotFoundError as error:
    # Keep the standalone ``python tools/<script>.py`` entrypoint usable.
    if error.name != "tools":
        raise
    runner_spec = importlib.util.spec_from_file_location("com_workbook_accm_runner", Path(__file__).with_name("run_com_workbook_accm_replay_v5.py"))
    if runner_spec is None or runner_spec.loader is None:
        raise RuntimeError("COM v5 runner module is unavailable")
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)

REPORT_SCHEMA = "sipi.com.workbook-accm-replay.v5.diagnostic"
AGGREGATE_SCHEMA = "sipi.com.workbook-accm-replay.v5.aggregate"
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONTROL_VECTORS = ([0.0, 0.0], [0.0, 0.001])
PORT_ORDER = [1, 3, 2, 4]
METRIC_KEYS = (
    "FOM",
    "COM_dB",
    "VEC_dB",
    "VEO_mV",
    "sigma_N_V",
    "available_signal_v",
    "interference_noise_v",
    "threshold_der",
    "impulse_sample_count",
)
UPSTREAM_REQUIRED_METRICS = ("FOM", "COM_dB", "VEC_dB", "VEO_mV", "sigma_N_V")
BUILD_ENV_CLEARED_KEYS = runner.BUILD_ENV_CLEARED_KEYS
UPSTREAM_ENV_CLEARED_KEYS = runner.UPSTREAM_ENV_CLEARED_KEYS
BUILD_COMMAND = runner.BUILD_COMMAND
BUILD_ENV_POLICY = runner.BUILD_ENV_POLICY
BUILD_CONFIG_POLICY = runner.BUILD_CONFIG_POLICY
BUILD_CARGO_HOME_POLICY = runner.BUILD_CARGO_HOME_POLICY
UPSTREAM_UV_COMMAND = runner.UPSTREAM_UV_COMMAND
CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
CANDIDATE_ARCHIVE = {"bytes": 51384320, "sha256": "1f44f6dccba7a00684a82c4c7ce6248eb5ea7f353875af5d9589d17ece6883d0"}
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE = {"bytes": 43694080, "sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"}
FIXTURE_EXPECTED = {
    "workbook": {
        "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx",
        "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae",
        "bytes": 67087,
        "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925",
    },
    "s4p": {
        "path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p",
        "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0",
        "bytes": 6457063,
        "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec",
    },
}
NON_CLAIMS = [
    "no S-parameter fit",
    "channel uses one final FD-to-TD impulse",
    "no upstream or global numeric parity",
    "no release or promotion claim",
    "candidate DFE publication is not inferred from hidden state",
]
PATH_RE = re.compile(
    r"(?i)(?:^|[\s=(\[\{\"'])"
    r"(?:[a-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])"
)
REPORT_KEYS = {
    "schema",
    "run_id",
    "nonce",
    "candidate",
    "upstream",
    "fixtures",
    "fixture_post",
    "upstream_source_pre",
    "upstream_source_post",
    "archive_post",
    "port_order",
    "toolchain",
    "toolchain_post",
    "toolchain_stable",
    "scratch",
    "scratch_post",
    "build",
    "controls",
    "status",
    "matched",
    "acceptance",
    "blockers",
    "non_claims",
}


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_report(path: Path) -> bytes:
    if _is_reparse(path) or not path.is_file():
        raise ValueError("report is not a regular file")
    before = path.stat()
    if before.st_size < 0 or before.st_size > MAX_REPORT_BYTES:
        raise ValueError("report exceeds bounded size")
    payload = path.read_bytes()
    after = path.stat()
    if len(payload) != before.st_size or after.st_size != before.st_size:
        raise ValueError("report changed while reading")
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(_read_report(path)).hexdigest()


def _hex(value: Any, label: str, *, nonzero: bool = True) -> None:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None or (nonzero and set(value) == {"0"}):
        raise ValueError(f"{label} is not a valid nonzero SHA-256")


def _finite(value: Any, label: str, *, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    try:
        finite = math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise ValueError(f"{label} is not finite")


def _same_float(left: Any, right: Any, label: str) -> None:
    """Require a finite numeric field to equal its mechanical source exactly."""
    _finite(left, f"{label}.observed", allow_none=False)
    _finite(right, f"{label}.expected", allow_none=False)
    if float(left) != float(right):
        raise ValueError(f"{label} cross-field drift")


def _same_delta(observed: Any, left: Any, right: Any, label: str) -> None:
    expected = None if left is None or right is None else abs(float(left) - float(right))
    if expected is None:
        if observed is not None:
            raise ValueError(f"{label} must be null")
        return
    _same_float(observed, expected, label)


def path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path_free(key)
            path_free(item)
    elif isinstance(value, list):
        for item in value:
            path_free(item)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/")
        if PATH_RE.search(normalized) or normalized.startswith(("/", "../")) or "file://" in normalized.lower():
            raise ValueError("absolute path leaked into aggregate")


def _archive(value: Any, label: str, expected: dict[str, Any]) -> None:
    required = {"bytes", "sha256", "command"}
    if not isinstance(value, dict) or set(value) != required or value["bytes"] != expected["bytes"] or value["command"] != f"git -c core.autocrlf=false archive --format=tar <{label}>":
        raise ValueError(f"{label} archive shape drift")
    _hex(value["sha256"], f"{label} archive")
    if value["sha256"] != expected["sha256"]:
        raise ValueError(f"{label} archive hash drift")


def _archive_post(value: Any, label: str, expected: dict[str, Any]) -> None:
    required = {"bytes", "sha256", "path_redacted"}
    if not isinstance(value, dict) or set(value) != required or value["bytes"] != expected["bytes"] or value["path_redacted"] is not True:
        raise ValueError(f"{label} archive post shape drift")
    _hex(value["sha256"], f"{label} archive post")
    if value["sha256"] != expected["sha256"]:
        raise ValueError(f"{label} archive post hash drift")


def _fixture(value: Any, label: str, expected: dict[str, Any]) -> None:
    required = {"path", "git_blob_sha1", "bytes", "sha256", "source_commit", "basename", "materialized_bytes", "materialized_sha256"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError(f"{label} fixture shape drift")
    if {key: value[key] for key in ("path", "git_blob_sha1", "bytes", "sha256")} != expected:
        raise ValueError(f"{label} fixture identity drift")
    if value["source_commit"] != UPSTREAM_COMMIT or value["basename"] != Path(expected["path"]).name or value["materialized_bytes"] != expected["bytes"] or value["materialized_sha256"] != expected["sha256"]:
        raise ValueError(f"{label} fixture materialization drift")


def _fixture_post(value: Any, label: str, expected: dict[str, Any]) -> None:
    expected_value = {"source_bytes": expected["bytes"], "source_sha256": expected["sha256"], "materialized_bytes": expected["bytes"], "materialized_sha256": expected["sha256"]}
    if not isinstance(value, dict) or set(value) != set(expected_value) or value != expected_value:
        raise ValueError(f"{label} fixture post drift")


def _source_identity(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"package_source_inventory", "module_file"}:
        raise ValueError(f"{label} source identity shape drift")
    inventory = value["package_source_inventory"]
    if not isinstance(inventory, dict) or set(inventory) != {"count", "total_bytes", "sha256"} or isinstance(inventory["count"], bool) or not isinstance(inventory["count"], int) or inventory["count"] <= 0 or isinstance(inventory["total_bytes"], bool) or not isinstance(inventory["total_bytes"], int) or inventory["total_bytes"] <= 0:
        raise ValueError(f"{label} source inventory drift")
    _hex(inventory["sha256"], f"{label} source inventory")
    module = value["module_file"]
    required = {"relative_path", "basename", "bytes", "sha256", "root_contained", "path_redacted"}
    if not isinstance(module, dict) or set(module) != required or module["relative_path"] != "src/agent_com/__init__.py" or module["basename"] != "__init__.py" or module["root_contained"] is not True or module["path_redacted"] is not True or isinstance(module["bytes"], bool) or not isinstance(module["bytes"], int) or module["bytes"] <= 0:
        raise ValueError(f"{label} module identity drift")
    _hex(module["sha256"], f"{label} module")


TOOL_KEYS = {"role", "basename", "file_bytes", "file_sha256", "version_args", "version_exit", "version_stdout_sha256", "version_stderr_sha256", "path_redacted"}


def _toolchain(value: Any, label: str) -> None:
    roles = ("cargo", "rustc", "python", "uv")
    if not isinstance(value, dict) or set(value) != set(roles):
        raise ValueError(f"{label} toolchain shape drift")
    for role in roles:
        identity = value[role]
        if not isinstance(identity, dict) or set(identity) != TOOL_KEYS or identity["role"] != role:
            raise ValueError(f"{label} {role} identity drift")
        if not isinstance(identity["basename"], str) or not identity["basename"] or "/" in identity["basename"] or "\\" in identity["basename"] or isinstance(identity["file_bytes"], bool) or not isinstance(identity["file_bytes"], int) or identity["file_bytes"] <= 0 or identity["version_exit"] != 0 or identity["path_redacted"] is not True:
            raise ValueError(f"{label} {role} runtime receipt drift")
        _hex(identity["file_sha256"], f"{label} {role} file")
        _hex(identity["version_stdout_sha256"], f"{label} {role} stdout")
        _hex(identity["version_stderr_sha256"], f"{label} {role} stderr")
        if not isinstance(identity["version_args"], list) or not identity["version_args"] or any(not isinstance(item, str) for item in identity["version_args"]):
            raise ValueError(f"{label} {role} version args drift")


def _marker_payload(report: dict[str, Any]) -> bytes:
    return f"sipi-com-workbook-accm-v5\nrun_id={report['run_id']}\nnonce={report['nonce']}\n".encode("ascii")


def _marker(value: Any, report: dict[str, Any], label: str) -> None:
    payload = _marker_payload(report)
    required = {"basename", "bytes", "sha256", "path_redacted"}
    if not isinstance(value, dict) or set(value) != required or value["basename"] != ".sipi-com-workbook-accm-v5-root-marker" or value["bytes"] != len(payload) or value["path_redacted"] is not True:
        raise ValueError(f"{label} marker drift")
    _hex(value["sha256"], f"{label} marker")
    if value["sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"{label} marker identity drift")


def _scratch(value: Any, report: dict[str, Any]) -> None:
    required = {"basename", "nonce", "nonce_bound", "fresh_at_start", "reparse_ancestors_checked", "path_redacted", "marker"}
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["basename"], str) or not value["basename"] or report["nonce"] not in value["basename"] or value["nonce"] != report["nonce"] or value["nonce_bound"] is not True or value["fresh_at_start"] is not True or value["reparse_ancestors_checked"] is not True or value["path_redacted"] is not True:
        raise ValueError("scratch receipt is not nonce-bound")
    _marker(value["marker"], report, "scratch pre")


def _scratch_post(value: Any, report: dict[str, Any]) -> None:
    required = {"basename", "nonce", "post_verified", "path_redacted", "marker"}
    if not isinstance(value, dict) or set(value) != required or value["basename"] != report["scratch"]["basename"] or value["nonce"] != report["nonce"] or value["post_verified"] is not True or value["path_redacted"] is not True:
        raise ValueError("scratch post receipt drift")
    _marker(value["marker"], report, "scratch post")


def _binary(value: Any, label: str) -> None:
    required = {"basename", "bytes", "sha256", "path_redacted"}
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["basename"], str) or not value["basename"] or "/" in value["basename"] or "\\" in value["basename"] or isinstance(value["bytes"], bool) or not isinstance(value["bytes"], int) or value["bytes"] <= 0 or value["path_redacted"] is not True:
        raise ValueError(f"{label} binary receipt drift")
    _hex(value["sha256"], f"{label} binary")


def _build(value: Any) -> None:
    required = {"exit", "stdout_sha256", "stderr_sha256", "command", "timeout_s", "env_policy", "env_receipt", "binary_pre", "binary_post", "binary_stable"}
    if not isinstance(value, dict) or set(value) != required or value["exit"] != 0 or value["timeout_s"] != 900 or value["binary_stable"] is not True or value["command"] != BUILD_COMMAND or value["env_policy"] != BUILD_ENV_POLICY:
        raise ValueError("candidate build receipt drift")
    _hex(value["stdout_sha256"], "candidate build stdout")
    _hex(value["stderr_sha256"], "candidate build stderr")
    _binary(value["binary_pre"], "candidate pre")
    _binary(value["binary_post"], "candidate post")
    if value["binary_pre"] != value["binary_post"]:
        raise ValueError("candidate binary changed during replay")
    environment = value["env_receipt"]
    required_environment = {"cleared_keys", "forced_keys", "flags_cleared", "target_flags_cleared", "wrappers_cleared", "config_policy", "cargo_home_policy", "target_basename", "path_redacted"}
    if not isinstance(environment, dict) or set(environment) != required_environment or environment["flags_cleared"] is not True or environment["target_flags_cleared"] is not True or environment["wrappers_cleared"] is not True or environment["config_policy"] != BUILD_CONFIG_POLICY or environment["cargo_home_policy"] != BUILD_CARGO_HOME_POLICY or environment["path_redacted"] is not True or not isinstance(environment["target_basename"], str) or not environment["target_basename"] or "/" in environment["target_basename"] or "\\" in environment["target_basename"]:
        raise ValueError("candidate build environment policy drift")
    cleared = environment["cleared_keys"]
    if not isinstance(cleared, list) or any(not isinstance(key, str) for key in cleared) or len(cleared) != len(set(cleared)) or not set(BUILD_ENV_CLEARED_KEYS).issubset(cleared):
        raise ValueError("candidate build cleared-key receipt drift")
    if any(not (key.startswith("CARGO_TARGET_") and key.endswith(("_RUSTFLAGS", "_RUSTDOCFLAGS", "_LINKER"))) for key in set(cleared) - set(BUILD_ENV_CLEARED_KEYS)):
        raise ValueError("candidate build target-key receipt drift")
    if environment["forced_keys"] != ["CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "CARGO_TERM_COLOR", "RUSTC", "CARGO_TARGET_DIR"]:
        raise ValueError("candidate build forced-key receipt drift")


def _metrics(value: Any, label: str, *, required_keys: tuple[str, ...] = METRIC_KEYS) -> None:
    if not isinstance(value, dict) or set(value) != set(METRIC_KEYS):
        raise ValueError(f"{label} metric schema drift")
    for key in METRIC_KEYS:
        _finite(value[key], f"{label}.{key}", allow_none=key not in required_keys)


def _array(value: Any, label: str, *, shaped: bool) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} array receipt missing")
    required = {"shape", "sample_count", "bytes", "sha256"} if shaped else {"sample_count", "sha256"}
    if set(value) != required or isinstance(value["sample_count"], bool) or not isinstance(value["sample_count"], int) or value["sample_count"] <= 0:
        raise ValueError(f"{label} array receipt shape drift")
    if shaped:
        if isinstance(value["bytes"], bool) or not isinstance(value["bytes"], int) or value["bytes"] <= 0 or not isinstance(value["shape"], list) or not value["shape"] or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value["shape"]):
            raise ValueError(f"{label} shaped array receipt drift")
        if math.prod(value["shape"]) != value["sample_count"] or value["bytes"] != value["sample_count"] * 8:
            raise ValueError(f"{label} shaped array size drift")
    _hex(value["sha256"], f"{label} array")


def _arrays(value: Any, label: str, names: tuple[str, ...], *, shaped: bool) -> None:
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(f"{label} array schema drift")
    for name in names:
        _array(value[name], f"{label}.{name}", shaped=shaped)


def _index(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} index drift")


def _taps(value: Any, label: str, *, allow_none: bool) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} taps drift")
    for item in value:
        _finite(item, label, allow_none=False)


def _upstream_winner(value: Any) -> None:
    required = {"cursor_index", "ctle_index", "high_pass_index", "tx_grid_index", "sigma_n_v", "fom_db", "selected_tx_taps", "dfe_taps", "dfe_published"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("upstream winner schema drift")
    for key in ("cursor_index", "ctle_index", "high_pass_index", "tx_grid_index"):
        _index(value[key], f"upstream winner.{key}")
    _finite(value["sigma_n_v"], "upstream winner.sigma_n_v", allow_none=False)
    _finite(value["fom_db"], "upstream winner.fom_db", allow_none=False)
    _taps(value["selected_tx_taps"], "upstream selected TX", allow_none=True)
    _taps(value["dfe_taps"], "upstream DFE", allow_none=False)
    if value["dfe_published"] is not True or value["selected_tx_taps"] is not None:
        raise ValueError("upstream winner publication drift")


def _candidate_winner(value: Any) -> None:
    required = {"cursor_index", "ctle_index", "high_pass_index", "tx_grid_index", "sigma_n_v", "fom_db", "selected_tx_taps", "dfe_taps", "dfe_published", "selected_pulse"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("candidate winner schema drift")
    for key in ("cursor_index", "ctle_index", "high_pass_index", "tx_grid_index"):
        _index(value[key], f"candidate winner.{key}")
    _finite(value["sigma_n_v"], "candidate winner.sigma_n_v", allow_none=False)
    _finite(value["fom_db"], "candidate winner.fom_db", allow_none=False)
    _taps(value["selected_tx_taps"], "candidate selected TX", allow_none=False)
    if value["dfe_taps"] is not None or value["dfe_published"] is not False:
        raise ValueError("candidate DFE publication state drift")
    _array(value["selected_pulse"], "candidate selected pulse", shaped=False)


def _upstream_case(value: Any, index: int) -> None:
    required = {"metrics", "winner", "port_order", "arrays"}
    if not isinstance(value, dict) or set(value) != required or value["port_order"] != PORT_ORDER:
        raise ValueError("upstream case schema drift")
    metrics = value["metrics"]
    winner = value["winner"]
    _metrics(metrics, "upstream case", required_keys=UPSTREAM_REQUIRED_METRICS)
    _upstream_winner(winner)
    _same_float(winner["fom_db"], metrics["FOM"], "upstream winner FOM/metrics.FOM")
    _same_float(winner["sigma_n_v"], metrics["sigma_N_V"], "upstream winner sigma/metrics.sigma_N_V")
    arrays = value["arrays"]
    _arrays(arrays, "upstream case", ("unequalized_impulse", "equalized_pulse", "frequency_hz", "ptdr", "ptdr_gated", "tdr_time_s"), shaped=True)
    if winner["cursor_index"] >= arrays["equalized_pulse"]["sample_count"]:
        raise ValueError("upstream cursor is outside equalized pulse")
    if metrics["impulse_sample_count"] is not None and metrics["impulse_sample_count"] != arrays["unequalized_impulse"]["sample_count"]:
        raise ValueError("upstream impulse sample count is not bound to the array")


def _candidate_case(value: Any, index: int) -> None:
    required = {"case_index", "metrics", "winner", "arrays", "port_order", "port_order_observed", "provenance"}
    if not isinstance(value, dict) or set(value) != required or value["case_index"] != index or value["port_order"] is not None or value["port_order_observed"] is not False:
        raise ValueError("candidate case schema or port-order observation drift")
    metrics = value["metrics"]
    winner = value["winner"]
    _metrics(metrics, "candidate case")
    _candidate_winner(winner)
    _same_float(winner["fom_db"], metrics["FOM"], "candidate winner FOM/metrics.FOM")
    _same_float(winner["sigma_n_v"], metrics["sigma_N_V"], "candidate winner sigma/metrics.sigma_N_V")
    arrays = value["arrays"]
    _arrays(arrays, "candidate case", ("channel_impulse", "channel_pulse"), shaped=False)
    if winner["selected_pulse"] != arrays["channel_pulse"]:
        raise ValueError("candidate selected pulse is not the applied channel pulse")
    if winner["cursor_index"] >= arrays["channel_pulse"]["sample_count"]:
        raise ValueError("candidate cursor is outside channel pulse")
    if metrics["impulse_sample_count"] != arrays["channel_impulse"]["sample_count"]:
        raise ValueError("candidate impulse sample count is not bound to the array")
    provenance = value["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {"config_sha256", "channel_source_sha256", "impulse_sha256"}:
        raise ValueError("candidate provenance schema drift")
    for key, item in provenance.items():
        _hex(item, f"candidate provenance.{key}")
    if provenance["channel_source_sha256"] != FIXTURE_EXPECTED["s4p"]["sha256"]:
        raise ValueError("candidate channel source is not the pinned S4P fixture")
    if provenance["impulse_sha256"] != arrays["channel_impulse"]["sha256"]:
        raise ValueError("candidate impulse provenance is not the reported array")


def _upstream_runtime_proof(value: Any, source_identity: dict[str, Any]) -> None:
    required = {"environment", "agent_com", "numpy", "scipy"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("upstream runtime proof schema drift")
    environment = value["environment"]
    if not isinstance(environment, dict) or set(environment) != {"cleared", "pythonpath_mode", "pythonno_user_site", "uv_no_config"} or environment["cleared"] != list(UPSTREAM_ENV_CLEARED_KEYS) or environment["pythonpath_mode"] not in {"unset", "materialized_archive_src"} or environment["pythonno_user_site"] is not True or environment["uv_no_config"] is not True:
        raise ValueError("upstream environment proof drift")
    agent = value["agent_com"]
    if not isinstance(agent, dict) or set(agent) != {"module", "contained_in_materialized_archive", "module_file", "package_source_inventory"} or agent["module"] != "agent_com" or agent["contained_in_materialized_archive"] is not True:
        raise ValueError("agent_com containment proof drift")
    observed = {"module_file": agent["module_file"], "package_source_inventory": agent["package_source_inventory"]}
    _source_identity(source_identity, "expected upstream")
    _source_identity(observed, "observed upstream")
    if observed != source_identity:
        raise ValueError("upstream runtime source identity drift")
    for name in ("numpy", "scipy"):
        package = value[name]
        required_package = {"relative_path", "basename", "bytes", "sha256", "root_contained", "path_redacted", "module", "version"}
        if not isinstance(package, dict) or set(package) != required_package or package["module"] != name or package["relative_path"] is not None or package["root_contained"] is not False or package["path_redacted"] is not True or not isinstance(package["basename"], str) or not package["basename"] or "/" in package["basename"] or "\\" in package["basename"] or isinstance(package["bytes"], bool) or not isinstance(package["bytes"], int) or package["bytes"] <= 0 or not isinstance(package["version"], str) or not package["version"]:
            raise ValueError(f"{name} runtime identity drift")
        _hex(package["sha256"], f"{name} runtime file")


def _upstream_payload(value: Any, source_identity: dict[str, Any]) -> None:
    required = {"exit", "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes", "runtime", "attempts", "config_sha256", "port_order", "runtime_proof", "artifact", "cases", "blocker"}
    if not isinstance(value, dict) or set(value) != required or value["exit"] != 0 or value["runtime"] != "executed_clean_archive_uv" or value["config_sha256"] != FIXTURE_EXPECTED["workbook"]["sha256"] or value["port_order"] != PORT_ORDER or value["blocker"] is not None or not isinstance(value["cases"], list) or len(value["cases"]) != 2:
        raise ValueError("upstream payload schema drift")
    _hex(value["stdout_sha256"], "upstream stdout")
    _hex(value["stderr_sha256"], "upstream stderr")
    for key, minimum in (("stdout_bytes", 1), ("stderr_bytes", 0)):
        if isinstance(value[key], bool) or not isinstance(value[key], int) or value[key] < minimum or value[key] > MAX_CAPTURE_BYTES:
            raise ValueError(f"upstream {key} receipt drift")
    _upstream_runtime_proof(value["runtime_proof"], source_identity)
    artifact = value["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"basename", "bytes", "sha256", "path_redacted"} or artifact["basename"] != "upstream-projection.json" or isinstance(artifact["bytes"], bool) or not isinstance(artifact["bytes"], int) or artifact["bytes"] <= 0 or artifact["path_redacted"] is not True:
        raise ValueError("upstream artifact receipt drift")
    _hex(artifact["sha256"], "upstream artifact")
    if artifact["bytes"] != value["stdout_bytes"] or artifact["sha256"] != value["stdout_sha256"]:
        raise ValueError("upstream artifact does not match stdout receipt")
    attempts = value["attempts"]
    if not isinstance(attempts, list) or len(attempts) != 1:
        raise ValueError("upstream attempt receipt drift")
    for item in attempts:
        if not isinstance(item, dict) or set(item) != {"exit", "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes", "method", "command", "blocker"} or item["method"] != "uv_offline" or item["command"] != UPSTREAM_UV_COMMAND or item["exit"] != 0 or item["blocker"] is not None:
            raise ValueError("upstream attempt schema drift")
        _hex(item["stdout_sha256"], "upstream attempt stdout")
        _hex(item["stderr_sha256"], "upstream attempt stderr")
        for key, minimum in (("stdout_bytes", 1), ("stderr_bytes", 0)):
            if isinstance(item[key], bool) or not isinstance(item[key], int) or item[key] < minimum or item[key] > MAX_CAPTURE_BYTES:
                raise ValueError(f"upstream attempt {key} receipt drift")
    attempt = attempts[0]
    if value["exit"] != attempt["exit"] or value["stdout_sha256"] != attempt["stdout_sha256"] or value["stderr_sha256"] != attempt["stderr_sha256"] or value["stdout_bytes"] != attempt["stdout_bytes"] or value["stderr_bytes"] != attempt["stderr_bytes"]:
        raise ValueError("upstream final attempt receipt is not top-level bound")
    for index, case in enumerate(value["cases"]):
        _upstream_case(case, index)


def _candidate_payload(value: Any, expected_vector: list[float]) -> None:
    required = {"exit", "stdout_sha256", "stderr_sha256", "runtime_timeout_s", "command", "vector", "runtime_exit", "consumer_proof", "artifact_sha256", "artifacts", "cases", "blocker"}
    if not isinstance(value, dict) or set(value) != required or value["exit"] != 0 or value["runtime_exit"] != 0 or value["runtime_timeout_s"] != 180 or value["consumer_proof"] is not True or value["blocker"] is not None or value["vector"] != expected_vector or not isinstance(value["vector"], list) or not isinstance(value["cases"], list) or len(value["cases"]) != 2:
        raise ValueError("candidate payload schema drift")
    _hex(value["stdout_sha256"], "candidate stdout")
    _hex(value["stderr_sha256"], "candidate stderr")
    _hex(value["artifact_sha256"], "candidate result artifact")
    expected_command = "sipi-com-direct-run run --config <pinned-workbook> --thru <pinned-s4p> --output-dir <fresh-output> --override AC_CM_RMS=<vector> --overwrite"
    if value["command"] != expected_command or len(value["vector"]) != 2 or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in value["vector"]):
        raise ValueError("candidate command/vector drift")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, list) or {item.get("basename") for item in artifacts if isinstance(item, dict)} != {"result.json", "report.html", "diagnostics.json"} or len(artifacts) != 3:
        raise ValueError("candidate artifact inventory drift")
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"basename", "bytes", "sha256", "path_redacted"} or item["path_redacted"] is not True or isinstance(item["bytes"], bool) or not isinstance(item["bytes"], int) or item["bytes"] <= 0:
            raise ValueError("candidate artifact receipt shape drift")
        _hex(item["sha256"], "candidate artifact")
    result_artifact = next(item for item in artifacts if item["basename"] == "result.json")
    if result_artifact["sha256"] != value["artifact_sha256"]:
        raise ValueError("candidate result artifact hash mismatch")
    for index, case in enumerate(value["cases"]):
        _candidate_case(case, index)


def _comparison(value: Any, upstream_case: dict[str, Any], candidate_case: dict[str, Any]) -> None:
    required = {"port_order_match", "port_order_observed", "port_order_status", "cursor_index_match", "sigma_n_v_abs_delta", "fom_db_abs_delta", "metric_abs_delta", "dfe", "array_receipts"}
    if not isinstance(value, dict) or set(value) != required or value["port_order_match"] is not False or value["port_order_observed"] is not False or value["port_order_status"] != "not_observed" or not isinstance(value["cursor_index_match"], bool):
        raise ValueError("comparison port-order or schema drift")
    expected_cursor_match = upstream_case["winner"]["cursor_index"] == candidate_case["winner"]["cursor_index"]
    if value["cursor_index_match"] != expected_cursor_match:
        raise ValueError("comparison cursor match drift")
    _same_delta(value["sigma_n_v_abs_delta"], upstream_case["winner"]["sigma_n_v"], candidate_case["winner"]["sigma_n_v"], "comparison sigma delta")
    _same_delta(value["fom_db_abs_delta"], upstream_case["winner"]["fom_db"], candidate_case["winner"]["fom_db"], "comparison FOM delta")
    metric_delta = value["metric_abs_delta"]
    if not isinstance(metric_delta, dict) or set(metric_delta) != set(METRIC_KEYS):
        raise ValueError("comparison metric delta schema drift")
    for key, item in metric_delta.items():
        _same_delta(item, upstream_case["metrics"][key], candidate_case["metrics"][key], f"comparison metric delta.{key}")
    dfe = value["dfe"]
    if not isinstance(dfe, dict) or set(dfe) != {"upstream_published", "candidate_published", "status"} or dfe["upstream_published"] is not True or dfe["candidate_published"] is not False or dfe["status"] != "candidate_missing":
        raise ValueError("comparison DFE publication drift")
    arrays = value["array_receipts"]
    if not isinstance(arrays, dict) or set(arrays) != {"upstream", "candidate"} or arrays["upstream"] != upstream_case["arrays"] or arrays["candidate"] != candidate_case["arrays"]:
        raise ValueError("comparison array receipt mismatch")


def _control(value: Any, index: int, source_identity: dict[str, Any]) -> None:
    required = {"vector", "upstream", "candidate", "comparison"}
    if not isinstance(value, dict) or set(value) != required or value["vector"] != list(CONTROL_VECTORS[index]):
        raise ValueError("control schema drift")
    _upstream_payload(value["upstream"], source_identity)
    _candidate_payload(value["candidate"], value["vector"])
    comparisons = value["comparison"]
    if not isinstance(comparisons, list) or len(comparisons) != 2:
        raise ValueError("comparison count drift")
    for upstream_case, candidate_case, comparison in zip(value["upstream"]["cases"], value["candidate"]["cases"], comparisons):
        _comparison(comparison, upstream_case, candidate_case)


def _validate_report_shape(value: dict[str, Any]) -> None:
    if set(value) != REPORT_KEYS or value["schema"] != REPORT_SCHEMA or value["status"] != "scoped_mismatch_observed" or value["matched"] is not False or value["acceptance"] is not False or value["blockers"] != ["candidate_dfe_taps_not_published"] or value["non_claims"] != NON_CLAIMS:
        raise ValueError("report top-level schema or claim drift")
    for key in ("run_id", "nonce"):
        if not isinstance(value[key], str) or HEX64.fullmatch(value[key]) is None:
            raise ValueError("report run identity drift")
    if value["run_id"] == value["nonce"]:
        raise ValueError("report run_id and nonce must be distinct")
    candidate = value["candidate"]
    upstream = value["upstream"]
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree", "archive"} or candidate["commit"] != CANDIDATE_COMMIT or candidate["tree"] != CANDIDATE_TREE:
        raise ValueError("candidate source identity drift")
    if not isinstance(upstream, dict) or set(upstream) != {"commit", "tree", "archive"} or upstream["commit"] != UPSTREAM_COMMIT or upstream["tree"] != UPSTREAM_TREE:
        raise ValueError("upstream source identity drift")
    _archive(candidate["archive"], "candidate", CANDIDATE_ARCHIVE)
    _archive(upstream["archive"], "upstream", UPSTREAM_ARCHIVE)
    fixtures = value["fixtures"]
    fixture_post = value["fixture_post"]
    if not isinstance(fixtures, dict) or set(fixtures) != set(FIXTURE_EXPECTED) or not isinstance(fixture_post, dict) or set(fixture_post) != set(FIXTURE_EXPECTED):
        raise ValueError("fixture receipt schema drift")
    for key, expected in FIXTURE_EXPECTED.items():
        _fixture(fixtures[key], key, expected)
        _fixture_post(fixture_post[key], key, expected)
    archive_post = value["archive_post"]
    if not isinstance(archive_post, dict) or set(archive_post) != {"candidate", "upstream"}:
        raise ValueError("archive post schema drift")
    _archive_post(archive_post["candidate"], "candidate", CANDIDATE_ARCHIVE)
    _archive_post(archive_post["upstream"], "upstream", UPSTREAM_ARCHIVE)
    source_pre = value["upstream_source_pre"]
    source_post = value["upstream_source_post"]
    _source_identity(source_pre, "upstream pre")
    _source_identity(source_post, "upstream post")
    if source_pre != source_post:
        raise ValueError("upstream extracted source changed during replay")
    port_order = value["port_order"]
    if not isinstance(port_order, dict) or set(port_order) != {"source_key", "source_cell", "one_based"} or port_order["source_key"] != "Port Order" or port_order["source_cell"] != "COM_Settings!G7" or port_order["one_based"] != PORT_ORDER:
        raise ValueError("source port order drift")
    _toolchain(value["toolchain"], "pre")
    _toolchain(value["toolchain_post"], "post")
    if value["toolchain_stable"] is not True or value["toolchain"] != value["toolchain_post"]:
        raise ValueError("toolchain changed during replay")
    _scratch(value["scratch"], value)
    _scratch_post(value["scratch_post"], value)
    _build(value["build"])
    controls = value["controls"]
    if not isinstance(controls, list) or len(controls) != len(CONTROL_VECTORS):
        raise ValueError("control matrix drift")
    for index, control in enumerate(controls):
        _control(control, index, source_pre)


def _duplicate_safe_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid report JSON: {type(error).__name__}") from error
    if not isinstance(value, dict):
        raise ValueError("report JSON root is not an object")
    return value


def load_report(path: Path) -> dict[str, Any]:
    value = _duplicate_safe_json(_read_report(path))
    _validate_report_shape(value)
    path_free(value)
    return value


def stable_control(control: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(control)
    for side in ("upstream", "candidate"):
        payload = result.get(side)
        if isinstance(payload, dict):
            for key in ("exit", "runtime_exit", "stdout_sha256", "stderr_sha256", "artifact_sha256", "artifacts", "attempts"):
                payload.pop(key, None)
    return result


def _ensure_output_absent(output: Path) -> None:
    if output.exists():
        raise FileExistsError("aggregate output must be a new file")


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    _ensure_output_absent(output)
    first = load_report(first_path)
    second = load_report(second_path)
    if first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"]:
        raise ValueError("fresh replay run_id/nonce must be distinct")
    for key in ("candidate", "upstream", "fixtures", "fixture_post", "upstream_source_pre", "upstream_source_post", "archive_post", "port_order", "toolchain", "toolchain_post", "toolchain_stable"):
        if first[key] != second[key]:
            raise ValueError(f"cross-run {key} drift")
    if first["blockers"] != second["blockers"] or first["build"]["env_receipt"] != second["build"]["env_receipt"] or first["build"]["command"] != second["build"]["command"] or first["build"]["env_policy"] != second["build"]["env_policy"]:
        raise ValueError("cross-run build or blocker drift")
    if first["scratch"]["basename"] == second["scratch"]["basename"] or first["scratch"]["marker"]["sha256"] == second["scratch"]["marker"]["sha256"]:
        raise ValueError("physical scratch root receipts are not distinct")
    if first["scratch_post"]["marker"]["sha256"] != first["scratch"]["marker"]["sha256"]:
        raise ValueError("first scratch pre/post marker drift")
    if second["scratch_post"]["marker"]["sha256"] != second["scratch"]["marker"]["sha256"]:
        raise ValueError("second scratch pre/post marker drift")

    controls = []
    typed_stability: list[bool] = []
    candidate_config_digests: list[list[str | None]] = []
    candidate_artifact_drift: list[bool] = []
    upstream_stability: list[bool] = []
    for index, (left, right) in enumerate(zip(first["controls"], second["controls"])):
        if left["vector"] != right["vector"]:
            raise ValueError(f"control vector drift at {index}")
        stable = stable_control(left) == stable_control(right)
        typed_stability.append(stable)
        left_digests = [case["provenance"]["config_sha256"] for case in left["candidate"]["cases"]]
        right_digests = [case["provenance"]["config_sha256"] for case in right["candidate"]["cases"]]
        candidate_config_digests.append(left_digests + right_digests)
        candidate_artifact_drift.append(left["candidate"]["artifacts"] != right["candidate"]["artifacts"])
        upstream_stability.append(left["upstream"]["cases"] == right["upstream"]["cases"])
        controls.append({"index": index, "vector": left["vector"], "first": left, "second": right, "typed_projection_stable": stable})

    first_binary = first["build"]["binary_pre"]
    second_binary = second["build"]["binary_pre"]
    first_report_bytes = _read_report(first_path)
    second_report_bytes = _read_report(second_path)
    if _duplicate_safe_json(first_report_bytes) != first or _duplicate_safe_json(second_report_bytes) != second:
        raise ValueError("report changed while hashing")
    result: dict[str, Any] = {
        "schema": AGGREGATE_SCHEMA,
        "status": "scoped_mismatch_observed",
        "matched": False,
        "acceptance": False,
        "blockers": sorted(set(first["blockers"])),
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "fixtures": first["fixtures"],
        "fixture_post": first["fixture_post"],
        "upstream_source_pre": first["upstream_source_pre"],
        "upstream_source_post": first["upstream_source_post"],
        "archive_post": first["archive_post"],
        "port_order": first["port_order"],
        "toolchain": first["toolchain"],
        "toolchain_post": first["toolchain_post"],
        "toolchain_stable": True,
        "scratch_roots": [
            {"slot": "run1", "basename": first["scratch"]["basename"], "nonce": first["nonce"], "marker": first["scratch"]["marker"]},
            {"slot": "run2", "basename": second["scratch"]["basename"], "nonce": second["nonce"], "marker": second["scratch"]["marker"]},
        ],
        "controls": controls,
        "replay_variance": {
            "typed_projection_stable_by_control": typed_stability,
            "candidate_config_provenance_sha256": candidate_config_digests,
            "candidate_config_provenance_drift": any(len(set(digests)) > 1 for digests in candidate_config_digests),
            "candidate_artifact_receipts_drift_by_control": candidate_artifact_drift,
            "upstream_projection_stable_by_control": upstream_stability,
        },
        "runs": [
            {"slot": "run1", "basename": first_path.name, "bytes": len(first_report_bytes), "sha256": hashlib.sha256(first_report_bytes).hexdigest(), "run_id": first["run_id"], "nonce": first["nonce"], "status": first["status"]},
            {"slot": "run2", "basename": second_path.name, "bytes": len(second_report_bytes), "sha256": hashlib.sha256(second_report_bytes).hexdigest(), "run_id": second["run_id"], "nonce": second["nonce"], "status": second["status"]},
        ],
        "builds": [first["build"], second["build"]],
        "binary_rebuild_drift": first_binary["sha256"] != second_binary["sha256"],
        "non_claims": NON_CLAIMS,
    }
    path_free(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": "valid", "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
