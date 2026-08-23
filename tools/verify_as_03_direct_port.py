"""AS-03 direct-port verifier entry point."""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/as-03-fit-yparam-direct-port.v1.yaml"
AUDIT_PATH = ROOT / "docs/baselines/audits/2026-08-23-as-03-fit-yparam-direct-port.md"
sys.path.insert(0, str(ROOT / "tools"))
from verify_as_remaining_direct_port import verify as _verify  # noqa: E402


def verify(document, source=None, root=ROOT): return _verify(document, evidence_path=EVIDENCE, source=source, root=root)


if __name__ == "__main__":
    path = EVIDENCE
    result = _verify(yaml.safe_load(path.read_text(encoding="utf-8")), evidence_path=path)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]: print(f"- {blocker}")
    raise SystemExit(0 if result["valid"] else 1)
