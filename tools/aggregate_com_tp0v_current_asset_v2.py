"""Future-only aggregate guard for the four isolated TP0V v2 records."""
from __future__ import annotations
import json
def require_strictly_faster(records: list[dict]) -> None:
    by_key = {(r["engine"], r["case"]): r for r in records}
    for case in (0, 1):
        if not by_key[("rust", case)]["wall_clock_s"] < by_key[("matlab", case)]["wall_clock_s"]:
            raise ValueError("rejected: Rust was not strictly faster for TP0V case %d" % case)
def aggregate(records: list[dict]) -> dict:
    if len(records) != 4: raise ValueError("blocked: exactly two MATLAB and two Rust records required")
    require_strictly_faster(records)
    return {"schema": "sipi.com.tp0v-current-asset-aggregate.v2", "status": "pending_full_comparison", "records": records}
