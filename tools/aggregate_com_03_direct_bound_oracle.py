"""Aggregate two additive COM-03 immutable-candidate oracle reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aggregate_com_03_direct_oracle import BOUND_INPUT_SCHEMA, BOUND_SCHEMA, aggregate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = aggregate(
        args.first,
        args.second,
        input_schema=BOUND_INPUT_SCHEMA,
        aggregate_schema=BOUND_SCHEMA,
    )
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "schema": document["schema"],
                "scenario_count": document["scenario_count"],
                "fresh_runs": document["fresh_runs"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
