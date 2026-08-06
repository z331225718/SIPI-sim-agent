"""Verify the certified capability catalog against its policy and engine.lock."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from sipi_contracts import parse_capabilities_certified, parse_engine_lock


def q(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_path = root / "docs" / "baselines" / "capabilities.certified.v1.json"
    if not catalog_path.is_file():
        print("capabilities.certified.v1.json: absent (nothing is certified)")
        return 0
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    parsed = parse_capabilities_certified(raw, producer=True)
    q(parsed.to_wire() == raw, "consumer round trip")
    q(raw["advertise"] is True and raw["status"] == "certified", "catalog advertisement")
    lock_path = root / "engine.lock"
    engines: dict[str, dict] = {}
    if lock_path.is_file():
        engines = {entry["instance_id"]: entry for entry in parse_engine_lock(lock_path.read_text(encoding="utf-8")).wire["engines"]}
    for entry in raw["entries"]:
        q(entry["evidence_state"] == "certified" and entry["release_channel"] == "stable", f"{entry['engine_instance']}: evidence/release")
        q(all(value == "unsupported" for value in entry["resource_enforcement"].values()), f"{entry['engine_instance']}: hard enforcement before M3")
        q(entry["certified_at"] <= entry["expires_at"], f"{entry['engine_instance']}: expiry ordering")
        q(bool(entry["evidence_refs"]), f"{entry['engine_instance']}: evidence refs")
        if engines:
            q(entry["engine_instance"] in engines, f"{entry['engine_instance']}: unknown engine instance")
            locked = engines[entry["engine_instance"]]
            q("sha256:" + locked["bundle"]["sha256"] == entry["bundle_hash"], f"{entry['engine_instance']}: bundle hash mismatch")
            q(locked["license_provenance"]["distribution_status"] != "blocked_unknown", f"{entry['engine_instance']}: license blocked")
    print(f"capabilities.certified.v1.json: valid ({len(raw['entries'])} certified entries)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"certified catalog invalid: {error}", file=sys.stderr)
        raise SystemExit(1)
