"""Probe the documented ADS passivity action surface for the fixed pulse bench.

This external-only helper changes no electrical or numerical control of the
P3C-04au bench.  It adds only the documented ``ImpSaveSpectrum=yes`` output
request, then reports the structured dataset variable names.  The first run is
an inventory probe; it intentionally does not interpret the names as a
passivity-correction result.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PULSE_PATH = ROOT / "tools" / "run_p3c_external_ads_fixed_pulse_operator.py"
SPEC = importlib.util.spec_from_file_location("fixed_pulse_operator", PULSE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("fixed_pulse_operator_import_unavailable")
PULSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PULSE)

VECTORSET_NAME = re.compile(r'^\* Vectorset name: "([^"\\]+)"$')
SPECTRUM_KINDS = ("CMP1_IMP", "CMP1_OR", "CMP1_FFT_IMP", "CMP1_S0")


class PassivitySurfaceError(RuntimeError):
    pass


def build_netlist() -> str:
    base = PULSE.build_netlist()
    needle = "ImpEnforcePassivity=yes "
    if base.count(needle) != 1 or "ImpSaveSpectrum=" in base:
        raise PassivitySurfaceError("fixed_pulse_predecessor_surface_mismatch")
    result = base.replace(needle, "ImpEnforcePassivity=yes ImpSaveSpectrum=yes ")
    if result.count("ImpSaveSpectrum=yes") != 1:
        raise PassivitySurfaceError("impulse_spectrum_request_mismatch")
    return result


def assert_fixed_output_only_delta(netlist: str) -> None:
    if netlist.count("ImpSaveSpectrum=yes") != 1:
        raise PassivitySurfaceError("impulse_spectrum_request_mismatch")
    PULSE.assert_fixed_netlist(netlist.replace("ImpSaveSpectrum=yes ", ""))
    base = PULSE.build_netlist()
    expected = base.replace("ImpEnforcePassivity=yes ", "ImpEnforcePassivity=yes ImpSaveSpectrum=yes ")
    if netlist != expected:
        raise PassivitySurfaceError("fixed_pulse_non_output_surface_changed")


def expected_vectorsets() -> tuple[str, ...]:
    names = [f"TRAN.CHANNEL.{kind}({row};{column})" for row in range(1, 5) for column in range(1, 5) for kind in SPECTRUM_KINDS]
    names.append("TRAN.TRAN")
    return tuple(names)


def vectorset_inventory(dataset: Path) -> tuple[str, ...]:
    if not PULSE.ads.DSDUMP.is_file():
        raise PassivitySurfaceError("ads_dsdump_not_found")
    result = PULSE.ads.subprocess.run(
        [str(PULSE.ads.DSDUMP), str(dataset)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if result.returncode:
        raise PassivitySurfaceError("ads_dataset_dump_rejected")
    names: list[str] = []
    for line in result.stdout.splitlines():
        match = VECTORSET_NAME.match(line.strip())
        if match is not None:
            names.append(match.group(1))
    if tuple(names) != expected_vectorsets():
        raise PassivitySurfaceError("ads_dataset_vectorset_inventory_rejected")
    return tuple(names)


def canonical_vectorset_identity(names: tuple[str, ...]) -> str:
    payload = bytearray(b"sipi.p3c.ads-passivity-surface-vectorset-identity.v1\x00")
    for name in names:
        encoded = name.encode("ascii")
        payload.extend(len(encoded).to_bytes(2, "big"))
        payload.extend(encoded)
    return hashlib.sha256(payload).hexdigest()


def materialize_probe(source: Path, destination: Path, *, invoke_ads: bool) -> dict[str, Any]:
    if destination.exists():
        raise PassivitySurfaceError("run_directory_must_not_exist")
    destination.mkdir(parents=True)
    data = destination / "data"
    data.mkdir()
    copied = data / "channel_gen5_highloss.s4p"
    before = PULSE.source_identity(source)
    shutil.copyfile(source, copied)
    if PULSE.source_identity(source) != before or (copied.stat().st_size, PULSE.sha256_file(copied)) != before:
        raise PassivitySurfaceError("selected_s4p_copy_drift")
    netlist = build_netlist()
    assert_fixed_output_only_delta(netlist)
    netlist_path = destination / "p3c_fixed_pulse_passivity_surface.ckt"
    netlist_path.write_text(netlist, encoding="ascii", newline="\n")
    result: dict[str, Any] = {
        "schema": "sipi.p3c-external-ads-fixed-pulse-passivity-surface-probe.v1",
        "runtime_invoked": False,
        "source": {"byte_length": before[0], "sha256": before[1]},
        "generated": {"netlist_sha256": PULSE.sha256_file(netlist_path), "netlist_byte_length": netlist_path.stat().st_size},
    }
    if invoke_ads:
        PULSE.ads.run_ads(netlist_path, destination, data)
        result["runtime_invoked"] = True
        names = vectorset_inventory(destination / "p3c_prbs9.ds")
        result["passivity_surface"] = {
            "vectorset_count": len(names),
            "s0_vectorset_count": sum(".CMP1_S0(" in name for name in names),
            "vectorset_identity_sha256": canonical_vectorset_identity(names),
        }
    (destination / "manifest.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="ascii", newline="\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not PULSE.ads.valid_run_id(args.run_id):
            raise PassivitySurfaceError("run_id_invalid")
        source = PULSE.require_external(args.s4p, "s4p")
        root = PULSE.require_external(args.output_root, "output_root")
        result = materialize_probe(source, root / args.run_id, invoke_ads=args.run)
    except (OSError, ValueError, PassivitySurfaceError, PULSE.FixedPulseError, PULSE.ads.ExternalReferenceError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "ads_run_completed" if args.run else "generated", "netlist_sha256": result["generated"]["netlist_sha256"], "passivity_surface": result.get("passivity_surface")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
