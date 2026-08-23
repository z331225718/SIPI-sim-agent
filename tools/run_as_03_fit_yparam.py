"""AS-03 two-replay runner."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_as_remaining import main as _main

if __name__ == "__main__":
    sys.argv[1:1] = ["AS-03"]
    raise SystemExit(_main())
