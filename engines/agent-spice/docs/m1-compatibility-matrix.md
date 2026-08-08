# M1 HSPICE Compatibility Matrix

| Feature | Status | Test Coverage |
|---|---|---|
| `.include` / `.inc` | supported; `.inc` is rewritten to `.include`; project-local dependencies are staged into each run directory | `tests/test_hspice_converter.py`, `tests/test_cli_run_hspice.py` |
| `.lib` discovery | audited and reported; project-local library files are staged for execution | `tests/test_hspice_audit.py`, `tests/test_cli_run_hspice.py` |
| `.param` passthrough | supported in generated case decks | `tests/fixtures/hspice/simple_pi.sp`, `tests/test_smoke_fixtures.py` |
| `.alter` expansion | supported with deterministic case names | `tests/test_hspice_alter.py`, `tests/test_cli_run_hspice.py` |
| `.probe` to `.print` | supported | `tests/test_hspice_converter.py`, `tests/test_smoke_fixtures.py` |
| `.measure` normalization | supported for output request metadata | `tests/test_hspice_measure.py` |
| HSPICE/Cadence 电流源 `PWL(... R=<time>)` | ngspice 对独立**电流**源不接受 `R=`（仅电压 PWL 支持）；converter 改写为等价的行为电流源 `B... I=pwl(...)`，用时间回绕保留从 `R` 到最后采样点的重复区间 | `tests/test_hspice_converter.py`；`user_input/cpm_model/TOP_VDD/PowerModel.sp` 的 ngspice-46 真实 TRAN |
| 独立电流源 `M=<N>` | ngspice 支持；等效为并联 N 个相同电流源。若该源同时使用需转换的 `PWL R=`，converter 将 `M` 乘入行为源表达式，不能丢失 | `tests/test_hspice_converter.py`；ngspice-46 本地实测 |
| 电容 `M=<N>` | ngspice 支持；等效电容为 `N*C`，即并联 N 个相同电容 | ngspice-46 本地实测 |
| 直接挂载 Touchstone `sNp` 的多端口网络并做 `.tran` | **不支持作为原样 ngspice 网表能力**。ngspice 的 `.sp` 是对电路进行频域 S 参数分析；其 Touchstone `xfer` 使用仅用于 AC 标量传递函数，不能替代多端口时域卷积。converter 必须识别该类实例并改走 `Touchstone -> 拟合/无源性检查 -> SPICE 子电路 -> TRAN`，或报告阻断 | ngspice-46 手册 8.2.19、11.3.8；项目 `fit-sparam` 流程 |
| Backend command construction | ngspice and Xyce command adapters | `tests/test_backend_commands.py` |
| XDM invocation command | HSPICE-to-Xyce command construction supported | `tests/test_backend_commands.py` |
| Case artifacts | `case.cir` and `compat_report.json` are written per case | `tests/test_deck_builder.py` |
| `run-hspice` CLI | converts HSPICE deck cases without requiring simulator execution | `tests/test_cli_run_hspice.py`, `tests/test_smoke_fixtures.py` |
| ngspice execution artifacts | writes `stdout.log`, `stderr.log`, portable `waveform.csv`, and machine-readable `run_summary.json` with parsed `.measure` values | `tests/test_cli_run_hspice.py`, `tests/test_hspice_results.py` |

## Deferred Beyond M1

| Feature | Reason |
|---|---|
| Full Synopsys HSPICE syntax parity | MVP focuses on the PI deck subset and emits compatibility data for unsupported directives. |
| Real ngspice/Xyce execution in unit tests | Tests must not depend on local simulator installations. |
| Production S-parameter model quality gates | Metadata loading and VectorFitting wrapper are in place; deeper quality policy is a later phase. |

## SIPI/PI Scope And Known Differences

本兼容层的 M1 范围是无源 SIPI/PI 网表：R/L/C/K、传输线、理想 V/I 激励、PWL/PULSE/SIN/EXP、CPM/UPM 子电路、VRM/decap 以及 S 参数拟合导出的宏模型。每次 ngspice 运行前必须执行 converter；顶层输入保存为 `case.source.sp`，转换后的可执行网表为 `case.cir`，相对 `.include`/`.lib` 依赖也会递归暂存并转换。

以下项目不属于自动等价转换范围，发现后应在 `compat_report.json` 中阻断并给出位置，而不是静默近似：工艺 MOS/BJT/二极管模型和 HSPICE 专有 `.model` 参数、Verilog-A、加密 PDK、HSPICE 专有有源器件模型。ngspice 的 `ngbehavior=hs` 只能辅助递归 `.lib` 与 MOS `nf` 处理，不能替代本项目的 converter，也不代表完整 HSPICE 语法兼容。
