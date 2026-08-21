"""Verify the current v2 owner-input request only."""

from __future__ import annotations

import argparse
import json
import sys

import yaml

try:
    from tools.verify_owner_decision_reconciliation_v2 import CURRENT_REQUEST, CURRENT_REQUEST_SCHEMA, validate_current_request
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from verify_owner_decision_reconciliation_v2 import CURRENT_REQUEST, CURRENT_REQUEST_SCHEMA, validate_current_request

SCHEMA = CURRENT_REQUEST_SCHEMA


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **validate_current_request()}, sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, RuntimeError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
