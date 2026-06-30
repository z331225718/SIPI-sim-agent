# Remaining Implementation Tasks After Task 6

日期：2026-06-30

当前已完成：

- Task 1: Package Scaffold
- Task 2: Project Manifest And Run Layout
- Task 3: HSPICE Audit Scanner
- Task 4: `.alter` Case Expansion
- Task 5: Measurement And Probe Normalization
- Task 6: Compatibility Report And Converter

当前验证基线：

```powershell
python -m pytest tests/test_import.py tests/test_project_manifest.py tests/test_hspice_audit.py tests/test_hspice_alter.py tests/test_hspice_measure.py tests/test_hspice_converter.py -v
```

最近一次 5.4 reviewer 验证结果：`22 passed`。

## Task 7: Backend Process Abstraction

目标：创建后端执行抽象，支持 ngspice 和 Xyce 的命令构造。

文件：

- `src/agent_spice/backend/__init__.py`
- `src/agent_spice/backend/base.py`
- `src/agent_spice/backend/ngspice.py`
- `src/agent_spice/backend/xyce.py`
- `tests/test_backend_commands.py`

验收：

- `NgspiceBackend.command_for(deck)` 返回 `["ngspice", "-b", str(deck)]`。
- `XyceBackend.command_for(deck)` 返回 `["Xyce", str(deck)]`。
- `XyceBackend.xdm_command_for(hspice_path, output_path)` 生成 HSPICE -> Xyce 的 XDM 命令。
- 新增测试通过，并保持现有 22 个测试通过。

## Task 8: Deck Builder And Case Artifacts

目标：把转换后的 deck 和 compatibility report 写入稳定 case 目录。

文件：

- `src/agent_spice/deck/__init__.py`
- `src/agent_spice/deck/builder.py`
- `tests/test_deck_builder.py`

验收：

- `write_case_artifacts(run_dir, deck_text, compat_report)` 创建 `case.cir`。
- 同一目录下创建 `compat_report.json`。
- 返回对象包含 `deck_path` 和 `compat_report_path`。

## Task 9: `run-hspice` CLI

目标：把已完成的 HSPICE audit/alter/converter/deck artifacts 串成 CLI。

文件：

- 修改 `src/agent_spice/cli.py`
- 创建 `tests/test_cli_run_hspice.py`

验收：

- 支持 `agent-spice run-hspice legacy.sp --backend ngspice|xyce --output-root runs`。
- 默认不执行后端时可以生成 case deck 和 `compat_report.json`。
- `.alter` deck 展开为多个 case 目录。
- 保持 CLI 入口 `main(argv)` 可测试。

## Task 10: Touchstone Metadata Loader

目标：支持读取 Touchstone `.sNp` 元数据，为 PI S 参数流水线入口做准备。

文件：

- `src/agent_spice/sparam/__init__.py`
- `src/agent_spice/sparam/io.py`
- `tests/test_sparam_io.py`

验收：

- 能读取最小 `.s2p` fixture。
- 输出端口数、频点数、每端口参考阻抗。
- 测试不依赖外部网络。

## Task 11: scikit-rf Vector Fitting Wrapper

目标：封装 `scikit-rf` 的 VectorFitting -> passivity -> SPICE export 主路径。

文件：

- `src/agent_spice/sparam/fitting.py`
- `tests/test_sparam_fitting.py`

验收：

- 用 monkeypatch/fake object 测试 wrapper 调用 `Network`、`VectorFitting`、`auto_fit()`、`passivity_enforce()`、`write_spice_subcircuit_s()`。
- 不在单元测试里依赖真实复杂 RF fitting。

## Task 12: CPM-lite Loader And PWL Renderer

目标：支持内部 CPM-lite JSON，并渲染为 SPICE PWL 电流源。

文件：

- `src/agent_spice/cpm/__init__.py`
- `src/agent_spice/cpm/io.py`
- `src/agent_spice/cpm/waveform.py`
- `tests/test_cpm_lite.py`

验收：

- 能读取 `model` 和 `bumps`。
- 每个 bump 渲染为 `I_<name> <node> <return_node> PWL(...)`。
- 波形点转换为 float，输出稳定。

## Task 13: Legacy Fixtures And Smoke Regression

目标：建立最小 HSPICE PI fixture 和 smoke tests。

文件：

- `tests/fixtures/hspice/simple_pi.sp`
- `tests/fixtures/hspice/alter_pi.sp`
- `tests/fixtures/cpm/chiplet_demo.json`
- `tests/test_smoke_fixtures.py`

验收：

- `simple_pi.sp` 通过 `run_hspice(..., execute=False)` 生成 base case。
- `alter_pi.sp` 生成 base、high_decap、low_decap 三个 case。
- 不依赖本机安装 ngspice/Xyce。

## Task 14: Full Test Gate And Documentation Update

目标：补 M1 兼容矩阵并跑全量测试。

文件：

- `docs/m1-compatibility-matrix.md`
- 如有必要，更新 `docs/pi-spice-simulator-spec.md`

验收：

- 兼容矩阵记录 `.include/.inc`、`.lib` discovery、`.param` passthrough、`.alter` expansion、`.probe -> .print`、`.measure` normalization、XDM command construction。
- 运行 `python -m pytest -v`，全部通过。
- 运行 CLI smoke：`python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-smoke`，生成 `runs-smoke/simple_pi/simple_pi__base/case.cir`。

