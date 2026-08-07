"""Stub Agent-Spice RFM bundle for the rfm-to-link vertical smoke example.

Reads an inline request JSON and writes ``meta.json`` carrying the
``agent-spice.rfm-response.v1`` domain result so the downstream
``link.simulate.v1`` analysis can consume it as a bound input.  Real
agent-spice bundles are deferred (license third-party classification and
managed lock); this stub freezes the vertical chain mechanics.
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
    argv = sys.argv[1:]
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    request = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    (out / "meta.json").write_text(
        json.dumps(
            {
                "schema": "agent-spice.rfm-response.v1",
                "effective_input": request,
                "backend_metadata": {"backend": "stub-rfm"},
                "diagnostics": [],
            }
        ),
        encoding="utf-8",
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
