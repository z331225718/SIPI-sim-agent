"""Run one immutable PB-03 `sim-rust` candidate/oracle replay."""

from __future__ import annotations

from pb_03_replay_common import parse_run_args, run_main


if __name__ == "__main__":
    raise SystemExit(run_main(parse_run_args("PB-03", "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml")))
