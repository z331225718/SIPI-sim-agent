"""Stub Agent-Spice bundle for the rfm-deck example (validate-only).

Real agent-spice bundles are deferred (license third-party classification and
managed lock); this stub exists so ``sipi validate`` is reproducible today.
Execution is wired once real adapter builders/bundles are available.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("stub agent-spice bundle: real engine execution is not wired yet", file=sys.stderr)
    return 9


if __name__ == "__main__":
    raise SystemExit(main())
