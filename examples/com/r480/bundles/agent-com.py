"""Stub Agent-COM bundle for the r480 example (validate-only).

Real agent-com bundles are deferred (oracle/license classification); this stub
exists so ``sipi validate`` is reproducible today.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("stub agent-com bundle: real engine execution is not wired yet", file=sys.stderr)
    return 9


if __name__ == "__main__":
    raise SystemExit(main())
