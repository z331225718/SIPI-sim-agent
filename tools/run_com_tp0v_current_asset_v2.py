"""Future-only TP0V v2 replay contract.

The executable implementation is deliberately unavailable until a clean candidate
and this harness are committed: callers must use the root `sipi com run` command,
four isolated archive/build/output roots, and record uninstrumented wall time.
It must reject alignment, resampling, truncation, delay correction, or a Rust case
that is not strictly faster than its MATLAB peer.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from verify_com_tp0v_current_asset_v2 import MANIFEST, load, validate
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--upstream-archive", type=Path, required=True); parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(); validate(load(MANIFEST), args.upstream_archive)
    if args.execute: raise SystemExit("blocked: bind a clean candidate and committed harness before replay")
    print("valid preparation only; no formal replay was run"); return 0
if __name__ == "__main__": raise SystemExit(main())
