"""Minimal fake com8023 engine used by adapter tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--thru", type=Path, required=True)
    parser.add_argument("--fext", type=Path, action="append", default=[])
    parser.add_argument("--next", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--no-result", action="store_true")
    argv = sys.argv[1:]
    if argv and argv[0] == "run":
        argv = argv[1:]
    args = parser.parse_args(argv)
    config_bytes = args.config.read_bytes()
    if b"FAIL" in config_bytes or args.fail:
        print("com8023 run failed", file=sys.stderr)
        return 4
    if b"NO_RESULT" in config_bytes or args.no_result:
        return 0
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": "r480",
                "profile": "r480",
                "cases": [],
                "provenance": {"inputs": {"config": str(args.config), "thru": str(args.thru)}},
                "warnings": [],
                "timings_s": {},
            }
        ),
        encoding="utf-8",
    )
    (out / "diagnostics.npz").write_bytes(b"fake-com-npz")
    (out / "report.html").write_text("<html><body>com report</body></html>", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
