"""Minimal fake PyBERT sim-native engine used by adapter tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fail", action="store_true")
    argv = sys.argv[1:]
    command = argv[0] if argv else ""
    if command in {"sim-native", "sim-agent-spice-response"}:
        argv = argv[1:]
    if command == "sim-agent-spice-response":
        parser.add_argument("--rfm-metadata", required=True)
        parser.add_argument("--rfm-response", required=True)
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    simulation_input = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    if simulation_input.get("fail") or args.fail:
        print("pybert simulation failed", file=sys.stderr)
        return 9
    (out / "meta.json").write_text(
        json.dumps(
            {
                "schema": (
                    "pybert.agent-spice-current-driven-link-cli-result.v1"
                    if command == "sim-agent-spice-response"
                    else "pybert.native-cli-result.v1"
                ),
                "effective_input": simulation_input,
                "backend_metadata": {"backend": "fake-native"},
                "diagnostics": [],
                "arrays_file": "arrays.npz",
            }
        ),
        encoding="utf-8",
    )
    (out / "arrays.npz").write_bytes(b"fake-npz-bytes")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
