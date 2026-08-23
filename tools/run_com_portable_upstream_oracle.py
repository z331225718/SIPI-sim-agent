"""Execute the pinned pure-Python Agent-COM leaves for COM-02 evidence.

This is intentionally an invocation oracle, not a checked-in numeric fixture:
the payload is produced by the source implementation at runtime and includes
the source commit/tree binding.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ROOT = Path(os.environ.get("AGENT_COM_ROOT", r"C:\Users\z3312\code\COM"))
sys.path.insert(0, str(UPSTREAM_ROOT / "src"))

from agent_com.calibration import calibrate_receiver_noise  # noqa: E402
from agent_com.equalization.mmse import constrained_mmse  # noqa: E402
from agent_com.equalization.rx_ffe import force_rx_ffe  # noqa: E402


def source_identity() -> dict[str, str]:
    revision = subprocess.check_output(
        ["git", "-C", str(UPSTREAM_ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(UPSTREAM_ROOT), "rev-parse", f"{revision}^{{tree}}"], text=True
    ).strip()
    if revision != UPSTREAM_COMMIT or tree != UPSTREAM_TREE:
        raise RuntimeError("upstream COM checkout is not the pinned source")
    return {
        "repository": str(UPSTREAM_ROOT),
        "commit": revision,
        "tree": tree,
        "license": "MIT",
    }


def main() -> int:
    source = source_identity()
    h = np.asarray([[1.0, 0.1], [0.2, 1.0], [0.1, 0.3]], dtype=np.float64)
    mmse = constrained_mmse(
        h,
        np.eye(2, dtype=np.float64) * 0.01,
        decision_index=0,
        dfe_tap_count=1,
        sigma_x2=1.0,
        levels=4,
        r_lm=50.0,
        rx_min=np.asarray([-2.0, -2.0]),
        rx_max=np.asarray([2.0, 2.0]),
        dfe_min=np.asarray([-0.5]),
        dfe_max=np.asarray([0.5]),
        rx_cursor_offset=0,
    )
    waveform = np.zeros(32, dtype=np.float64)
    waveform[[8, 12, 16, 20, 24, 28]] = [0.01, 0.1, 1.0, 0.05, 0.02, 0.01]
    rxffe = force_rx_ffe(
        waveform,
        cursor_index=16,
        precursor_count=1,
        postcursor_count=2,
        samples_per_ui=4,
        unity_cursor=True,
        return_filtered=True,
    )
    calibration = calibrate_receiver_noise(
        lambda sigma: np.asarray([3.0 - sigma, 2.5 - sigma], dtype=np.float64),
        pass_threshold_db=2.0,
        initial_step_v=2.0,
    )
    payload = {
        "schema": "sipi.com-02.upstream-runtime-oracle.v1",
        "oracle_kind": "upstream_runtime_execution",
        "source": source,
        "mmse": {
            "fom_db": float(mmse.fom_db),
            "sigma_e": float(mmse.sigma_e),
            "condition_number": float(mmse.condition_number),
            "rx_ffe": np.asarray(mmse.rx_ffe).tolist(),
            "dfe": np.asarray(mmse.dfe).tolist(),
        },
        "rx_ffe_search": {
            "taps": np.asarray(rxffe.taps).tolist(),
            "filtered_waveform_sha256": hashlib.sha256(
                np.asarray(rxffe.filtered, dtype=np.float64).tobytes()
            ).hexdigest(),
        },
        "calibration": {
            "sigma_bn_v": float(calibration.sigma_bn_v),
            "iteration_count": len(calibration.iterations),
            "minimum_com_db": [float(item.minimum_com_db) for item in calibration.iterations],
        },
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
