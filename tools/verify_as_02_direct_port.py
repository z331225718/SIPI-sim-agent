"""AS-02 direct-port verifier entry point."""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/as-02-fit-sparam-cascade-direct-port.v1.yaml"
AUDIT_PATH = ROOT / "docs/baselines/audits/2026-08-23-as-02-fit-sparam-cascade-direct-port.md"
sys.path.insert(0, str(ROOT / "tools"))
from verify_as_remaining_direct_port import verify as _verify  # noqa: E402


def verify(document, source=None, root=ROOT):
    return _verify(document, evidence_path=EVIDENCE, source=source, root=root)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    result = _verify(yaml.safe_load(path.read_text(encoding="utf-8")), evidence_path=path, source=args.source)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]: print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__": raise SystemExit(main())
