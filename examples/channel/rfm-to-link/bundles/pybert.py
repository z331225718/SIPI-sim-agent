"""Stub PyBERT strict sim-native engine for the rfm-to-link example.

This is the same minimal fixture used by the platform test suite: it reads an
inline SimulationInputV1 JSON and writes ``meta.json`` + ``arrays.npz`` so the
adapter contract (input.json -> --output-dir) can be exercised end to end.
Real pybert bundles are wired once the managed dependency lock exists
(M2 deferred trigger: managed lock + parity gate approved).
"""

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
    if argv and argv[0] == "sim-native":
        argv = argv[1:]
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
                "schema": "pybert.native-cli-result.v1",
                "effective_input": simulation_input,
                "backend_metadata": {"backend": "stub-native"},
                "diagnostics": [],
                "arrays_file": "arrays.npz",
            }
        ),
        encoding="utf-8",
    )
    (out / "arrays.npz").write_bytes(b"stub-arrays")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
