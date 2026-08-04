# M0-03 Toolchain Observation

采集环境为 Windows x86_64。此记录冻结可调用的版本和显式子进程入口，不安装、升级或永久修改用户环境。

| Tool | Selected / observed | Status |
| --- | --- | --- |
| Python | uv CPython 3.12.13；默认 `python` 为 3.14.5 | selected and isolated-verified |
| Rust | `rustup run 1.97.0-x86_64-pc-windows-msvc` | selected, not on PATH |
| Node/npm | 24.16.0 / 12.0.1 | observed |
| Git | 2.54.0.windows.1 | observed |
| GitNexus | 1.6.6 global package entrypoint | observed; never invoke `@latest` |
| ngspice/Xyce | 46 / 7.10 | observed |
| XDM | 2.6 (`xdm_bdl.exe`) | observed |
| HSPICE/ADS | unavailable | unavailable |
| MATLAB | R2024b | observed only |

The exact source of truth is [toolchains.lock](../../toolchains.lock). Rust must be launched through its pinned `rustup run` command; each baseline process must use its own `CARGO_HOME`, `CARGO_TARGET_DIR`, `UV_CACHE_DIR`, `TMP`, and `TEMP`. Python baselines require `PYTHONNOUSERSITE=1` and an empty `PYTHONPATH`.

The isolated Python/Rust probe and pinned GitNexus invocation are recorded in `toolchain-verification.v1.json`; this closes the narrow M0-03 toolchain observation. It is not a release lock and does not certify any engine baseline.
