# S-Parameter Quality Gate & Handoff Reports Plan

日期：2026-07-02

## 圆桌结论

下一阶段优先级不是继续追求更大的端口数、MOR、SROPEE，或 monkey-patch scikit-rf 私有实现，而是把当前 `fit-sparam` 从“能导出 SPICE 子电路”升级为“能判断模型是否可交付给后续仿真”。

决策：

- P0：新增 S-parameter quality gate 和 handoff report。
- P1：结构化 scikit-rf 数值诊断、质量状态、失败原因、建议重跑参数。
- P2：建立真实 benchmark corpus，再决定是否做 scikit-rf upstream/fork 优化或 MOR。

共识：

- 当前 `fit-sparam` 已经能跑通 MVP，但 `.sp` 导出成功不等于模型可进入 TRAN。
- 最大缺口是 quality gate，而不是 wrapper 调错。
- strict 模式下，未知质量不能 PASS；`None` 指标应当阻断或至少降级为不可交付状态。
- scikit-rf `VectorFitting` 继续作为近期主路径，但只能通过公开 API 使用。
- SROPEE/Block SAPOR 是后续大规模 MOR 研究线，不应作为下一阶段默认依赖。

分歧：

- DeepSeek 更激进地建议 strict 模式下 causality 未实现即 FAIL。
- 本地角色倾向先实现 report-only quality schema，再引入 `--fail-on-quality`，避免立刻打爆现有 MVP smoke。

收敛：

- 默认 profile 使用 `explore`：报告 WARN/FAIL，但不破坏已有探索工作流。
- 新增 `signoff` profile：任何阻断项失败时 CLI 返回非零码，且产物不能进入 downstream TRAN。

## 当前基线

已具备：

- `fit-sparam` CLI。
- scikit-rf `VectorFitting.auto_fit()` / `vector_fit()` 封装。
- `passivity_enforce()` 调用。
- SPICE 子电路导出。
- JSON/HTML 报告。
- `--log` 进度日志。
- 频带裁剪和频点抽样：`--fit-f-min`、`--fit-f-max`、`--fit-frequency-stride`、`--fit-max-frequency-points`。
- 原始频点评估误差：`comparison_rms_error`。

主要缺口：

- 没有独立 `sparam.quality` 模块。
- 没有稳定的质量门禁 schema。
- passivity、causality、DC/低频误差、Z0 风险、最大奇异值还未形成统一 gate。
- scikit-rf condition number、rank deficiency、最终阶数、极点数量等诊断只在日志里。
- fake tests 多，真实多端口/坏模型 benchmark 少。
- `parameter_type` 和固定 `write_spice_subcircuit_s()` 导出语义仍需收窄或解释。

## 用户目标

用户应该能回答三个问题：

1. 这个 Touchstone/fit 结果能不能交给仿真？
2. 如果不能，失败原因是什么？
3. 下一条命令该怎么调参重跑？

典型用户故事：

- 作为 PI 工程师，我想先检查 Touchstone 的端口数、Z0、频率范围、DC 覆盖、无源性风险，避免明显坏模型进入长时间拟合。
- 作为 CLI 用户，我想看到明确 `PASS/WARN/FAIL`，而不是只看到一堆误差数字。
- 作为自动化/CI 用户，我想用稳定 exit code 和 JSON schema 阻断坏模型。
- 作为 reviewer，我想 HTML 第一屏展示结论、关键指标、失败原因和可追溯配置。

## 非目标

本阶段不做：

- SROPEE/MOR 生产化。
- 32/64/128-port 性能承诺。
- 递归卷积或求解器内核改造。
- GUI。
- 完整系统 deck 组装。
- 自动修复所有坏 Touchstone。
- scikit-rf 私有函数 monkey-patch。

## 模块边界

### `sparam.io`

职责：

- Touchstone 读取。
- 元数据抽取。
- 端口数、频点数、频率范围、每频点 Z0 摘要。

原则：

- 保持薄边界。
- Touchstone 2.0 `[Reference]` 信息不可丢。

### `sparam.quality`

新增模块，职责：

- 对原始 network 做 pre-fit 检查。
- 对 fit result 做 post-fit 检查。
- 输出纯数据质量报告，不写文件、不导出 SPICE。
- 支持 profile：`explore`、`signoff`。

检查项：

- 频率单调性。
- NaN/Inf。
- 端口数和 Z0 摘要。
- DC 或低频覆盖。
- 频点抽样覆盖率。
- `comparison_rms_error`。
- 低频误差。
- passivity violation bands。
- 采样最大奇异值。
- 拟合后极点稳定性。
- causality 状态，未实现时 strict/signoff 不能 PASS。

### `sparam.conditioning`

后续模块，职责是会改变数据的处理：

- 参考阻抗重归一化。
- DC extrapolation。
- 高频尾部处理。
- S/Y/Z 转换。
- 端口重排和端口分组。

本阶段只诊断，不自动改数据。

### `sparam.fitting`

保留职责：

- scikit-rf `VectorFitting` 编排。
- 频点选择。
- passivity enforcement。
- SPICE export。
- 生成 fit result。

新增职责：

- 调用 `sparam.quality`。
- 将质量报告并入 JSON/HTML。
- 在 `--fail-on-quality` 下根据 quality gate 返回非零码。

### `sparam.report`

建议从 `fitting.py` 拆出，职责：

- HTML 渲染。
- JSON schema 稳定化。
- 第一屏展示 verdict、失败原因和建议。

### `sparam.benchmark`

后续模块，职责：

- 记录端口数、频点数、fit config、runtime、peak memory、SPICE size、quality status。
- 支持本地私有数据路径，缺失则 skip。
- 输出 JSONL/CSV，供性能路线决策使用。

### `sparam.mor`

延后，职责：

- SROPEE 隔离实验。
- Block SAPOR/Krylov/端口分组研究。
- 不进入默认 runtime dependency。

## JSON 报告契约

保持现有 top-level 字段兼容，同时新增稳定 schema：

```json
{
  "schema_version": "0.2",
  "input": {
    "source": "path/to/file.s16p",
    "sha256": "...",
    "ports": 16,
    "frequency_points": 1001,
    "frequency_range_hz": [0.0, 10000000000.0],
    "reference_impedance": [50.0],
    "z0_summary": {}
  },
  "fit_selection": {
    "frequency_points": 1001,
    "fit_frequency_points": 512,
    "fit_frequency_range_hz": [1000000.0, 5000000000.0],
    "stride": 1,
    "max_points": 512,
    "f_min": 1000000.0,
    "f_max": 5000000000.0
  },
  "fit": {
    "mode": "auto",
    "model_order": 40,
    "pole_count": 24,
    "rms_error": 0.01,
    "rms_error_scope": "fit_frequency_points",
    "comparison_rms_error": 0.02,
    "comparison_rms_error_scope": "original_frequency_points",
    "weighted_rms_error": null,
    "low_frequency_error": null,
    "dc_error": null
  },
  "passivity": {
    "before": false,
    "after": true,
    "max_singular_value_after": 1.0000001,
    "epsilon": 1e-6,
    "violation_bands_before": [],
    "violation_bands_after": []
  },
  "quality": {
    "profile": "explore",
    "status": "WARN",
    "allowed_for": "report_only",
    "blocking_reasons": [],
    "warnings": []
  },
  "diagnostics": [
    {
      "id": "comparison_rms_error",
      "status": "PASS",
      "severity": "info",
      "metric": 0.02,
      "threshold": 0.05,
      "message": "Original-point comparison RMS is within the explore threshold.",
      "recommendation": null
    }
  ],
  "artifacts": {
    "spice_path": "runs/model.sp",
    "json_report_path": "runs/fit_report.json",
    "html_report_path": "runs/fit_report.html",
    "log_path": "runs/fit.log"
  },
  "performance": {
    "load_seconds": null,
    "fit_seconds": null,
    "passivity_seconds": null,
    "export_seconds": null,
    "peak_memory_mb": null
  }
}
```

诊断项字段：

- `id`
- `status`: `PASS|WARN|FAIL|UNKNOWN`
- `severity`: `info|warning|error`
- `metric`
- `threshold`
- `frequency_hz` 或 `frequency_range_hz`
- `ports`
- `message`
- `recommendation`

质量状态：

- `PASS`: 可作为 handoff candidate。
- `WARN`: 可探索，不可默认进入 TRAN。
- `FAIL`: 阻断。
- `UNKNOWN`: strict/signoff 下等同 FAIL。

`allowed_for`：

- `report_only`
- `ac_only`
- `tran_candidate`
- `production`

## CLI 契约

新增参数：

```powershell
--quality-profile explore|signoff
--fail-on-quality
--max-comparison-rms-error 0.05
--max-passivity-epsilon 1e-6
--require-dc
--allow-quality-warnings
```

默认行为：

- `--quality-profile explore`
- 默认不因 WARN/FAIL 改变现有探索工作流。
- 报告里必须标注 `allowed_for=report_only` 或 `tran_candidate`。

严格行为：

```powershell
python -m agent_spice.cli fit-sparam .\model.s16p `
  --output runs-sparam/model.sp `
  --report runs-sparam/fit_report.json `
  --html-report runs-sparam/fit_report.html `
  --log runs-sparam/fit.log `
  --quality-profile signoff `
  --fail-on-quality
```

退出码：

- `0`: 命令成功，且未启用 fail-on-quality 或质量通过。
- `1`: 输入、参数或质量 gate 失败。
- 保持 ValueError 无 traceback 的现有 CLI 体验。

产物规则：

- `--skip-passivity-enforce` 只能产生 preview/debug artifact。
- preview 产物不得被 downstream 自动消费。
- strict PASS 之前，不复制到 production model path。

## 里程碑

### Milestone 1: Report-Only Quality Schema

目标：

- 新增 `sparam.quality`。
- 输出稳定 `quality` 和 `diagnostics[]`。
- 默认只报告，不改变退出码。

文件范围：

- `src/agent_spice/sparam/quality.py`
- `src/agent_spice/sparam/fitting.py`
- `tests/test_sparam_quality.py`
- `tests/test_sparam_fitting.py`
- `docs/sparam-quality-gate-plan.md`

验收：

- JSON 包含 `schema_version`、`quality.status`、`diagnostics[]`。
- 现有 `fit-sparam` smoke 不破坏。
- 质量未知时报告 `UNKNOWN`，不能伪装为 PASS。
- HTML 第一屏显示 verdict、关键指标和建议。

### Milestone 2: Strict Quality Gate

目标：

- 引入 `--quality-profile` 和 `--fail-on-quality`。
- signoff profile 可阻断坏模型。

文件范围：

- `src/agent_spice/sparam/quality.py`
- `src/agent_spice/sparam/fitting.py`
- `src/agent_spice/cli.py`
- `tests/test_cli_fit_sparam.py`
- `README.md`
- `docs/sparam-fit-performance.md`

验收：

- strict 模式下任何 blocking diagnostic 返回非零码。
- `passive_after_enforce is None/False` 不能 PASS。
- `comparison_rms_error is None` 不能 PASS。
- 缺 DC 且 `--require-dc` 时 FAIL。
- `--skip-passivity-enforce` 产物标记为 preview/debug。

### Milestone 3: S-Parameter Benchmark Corpus

目标：

- 建立真实 benchmark/golden 报告。
- 用数据决定性能路线。

文件范围：

- `src/agent_spice/sparam/benchmark.py`
- `src/agent_spice/cli.py`
- `benchmarks/sparam/cases.yaml`
- `benchmarks/sparam/README.md`
- `tests/test_sparam_benchmark.py`
- `tests/test_sparam_public_skrf_contract.py`

验收：

- benchmark 输出 JSONL/CSV。
- 至少支持本地私有数据路径，缺失则 skip。
- 记录 runtime、peak memory、ports、points、SPICE size、quality status。
- 禁止 `src/agent_spice/sparam` monkey-patch 或调用 scikit-rf 私有核心。

## Acceptance Fixtures

至少覆盖：

- 健康 2-port。
- 健康 16-port。
- 频率不单调。
- NaN/Inf。
- 少于 2 个 fit 频点。
- Z0 异常或频率相关 Z0。
- passivity violation。
- 抽样后误差变差。
- 缺 DC。
- scikit-rf passivity/error API 异常。

known-bad fixture 在 strict 模式下必须 FAIL。

## 性能路线

短期：

- 继续使用公开 scikit-rf API。
- 改善频点选择和 profile preset。
- 记录 BLAS/NumPy/scikit-rf 版本。
- case 级并行和参数 sweep 可做，但不能隐藏质量风险。

中期：

- benchmark 证明 `_pole_relocation()` 是主要瓶颈后，再考虑 upstream PR：
  - batched QR。
  - 可选 condition number 诊断。
  - `d_res == 0` 防 NaN。
  - 带容差的实极点/纯虚边界判断。

长期：

- MOR：SROPEE 隔离实验，Block SAPOR/Krylov/端口分组自研。
- Modal/orthonormal/AAA/RKFIT/Loewner 作为 benchmark 候选，不作为近期默认生产路径。

## 许可证与依赖边界

- scikit-rf 是当前可接受依赖。
- SROPEE 标记为 GPL-3.0，只能做隔离实验或算法参考。
- 不 vendor GPL 代码。
- 不把 SROPEE 加入 runtime dependencies、wheel、solver package。
- GPL solver 继续进程级隔离。
- 便携 solver zip 需要 SBOM 和许可证审查。

## Graduation Criteria

进入下一阶段 MOR/大端口优化前，必须满足：

- 质量 schema 稳定。
- strict gate 可阻断 known-bad fixture。
- 至少一个 16-port 样例能生成 PASS/WARN/FAIL 可解释报告。
- PASS 的 SPICE 子电路能被 ngspice 或 Xyce 至少一个后端跑通 smoke。
- benchmark 能稳定记录 runtime/memory/quality。
- 没有 scikit-rf 私有 monkey-patch。

## 当前实现状态

- Milestone 1 已落地：`sparam.quality`、JSON/HTML `quality` 和 `diagnostics[]`、report-only 默认行为。
- Milestone 2 已落地：`--quality-profile`、`--fail-on-quality`、`--allow-quality-warnings`、`--max-comparison-rms-error`、`--max-passivity-epsilon`、`--require-dc`。
- 默认 `explore` profile 保持 MVP smoke 兼容。
- `signoff` profile 下，未知质量项、超阈值误差、跳过 passivity enforcement、剩余 passivity violation、缺失 required DC 都会阻断质量通过。

## 下一步任务建议

1. 建 `benchmarks/sparam/README.md` 和本地数据 manifest。
2. 实现 `sparam benchmark` 或等价 CLI，输出 JSONL/CSV。
3. 增加至少一个私有 16-port 样例的 benchmark 配置，数据缺失时自动 skip。
4. 加 `tests/test_sparam_public_skrf_contract.py`，防止未来误用 scikit-rf 私有 API。
5. 基于 benchmark 决定是否进入 scikit-rf upstream 优化或 MOR/SROPEE 研究线。
