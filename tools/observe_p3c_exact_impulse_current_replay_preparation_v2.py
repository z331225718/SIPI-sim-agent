"""Run the additive T08 two-fresh replay against the current clean archive.

The v1 observer remains pinned to its historical blocked-input contract.  This
wrapper keeps that observer implementation unchanged while rebinding only the
clean-archive commit/tree and the additive v2 summary schema.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "7f21b5fc8f3290b3726d64c1858bd8f013816920"
BASELINE_TREE = "adc84f2ffbe4d755032c452e8181e56603cccf53"
SUMMARY_SCHEMA = "sipi.p3c.exact-impulse-current-replay-preparation.v2"
LEGACY_PATH = ROOT / "tools" / "observe_p3c_exact_impulse_current_replay_preparation.py"


def _load_legacy():
    spec = importlib.util.spec_from_file_location("_t08_v1_observer", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("v1_observer_import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASELINE_COMMIT = BASELINE_COMMIT
    module.BASELINE_TREE = BASELINE_TREE
    module.SUMMARY_SCHEMA = SUMMARY_SCHEMA
    return module


def main(argv: list[str] | None = None) -> int:
    # The clean archive is the execution root; only the toolchain and target
    # are external.  The observer's command intentionally stays locked/offline.
    cargo_bin = Path.home() / ".cargo" / "bin"
    os.environ["PATH"] = str(cargo_bin) + os.pathsep + os.environ.get("PATH", "")
    module = _load_legacy()

    # The v1 observer deliberately retains only the child-report digest.  The
    # additive v2 record needs the hash-only metric facts as well, so capture
    # the child JSON before the observer removes its temporary custody root.
    captured: dict[str, object] = {}
    original_run_child = module._run_child

    def run_child(*args, **kwargs):
        original_run_child(*args, **kwargs)
        report = args[4] if len(args) > 4 else kwargs["report"]
        captured["child"] = json.loads(report.read_text(encoding="ascii"))

    module._run_child = run_child
    original_write_summary = module.write_summary

    def write_summary(path, summary):
        child = captured.get("child")
        if not isinstance(child, dict) or not isinstance(child.get("fresh_runs"), list):
            raise module.FreshReplayError("child_report_capture")
        runs = child["fresh_runs"]
        summary = dict(summary)
        summary["fresh_run_facts"] = runs
        summary["reference_payload_sha256"] = runs[0]["reference_rx_payload_sha256"]
        summary["reference_waveform_digests"] = [run["reference_waveform_digest"] for run in runs]
        summary["candidate_waveform_digests"] = [run["candidate_waveform_digest"] for run in runs]
        summary["waveform_nrmse_bits"] = [run["waveform_nrmse_bits"] for run in runs]
        summary["waveform_nrmse_limit_bits"] = [run["waveform_nrmse_limit_bits"] for run in runs]
        summary["within_one_percent"] = [run["within_waveform_nrmse_limit"] for run in runs]
        return original_write_summary(path, summary)

    module.write_summary = write_summary
    return module.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
