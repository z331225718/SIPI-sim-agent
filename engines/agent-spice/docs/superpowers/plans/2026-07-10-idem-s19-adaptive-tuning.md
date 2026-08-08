# IdEM s19 Adaptive Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可恢复、可审计的 IdEM 内部 adaptive order-refinement 实验，并在 splitting none 下系统寻找 s19 的 `mean S-RMS <= 0.001 + passive` 配置。

**Architecture:** fixed-order benchmark adapter 保持不变；新增 adaptive options/command adapter，使用 IdEM CLI 的 `orderMin/orderStep/orderMax/tol` 控制 reserved order 参数，advanced XML 只控制 iterations、weights、error control、splitting 和 out-of-band。独立 runner 顺序执行 fitting、history inspection、accuracy、passivity、export 和 full-grid audit，并由 manifest 驱动参数阶段。

**Tech Stack:** Python 3.11+、dataclasses、JSON/CSV、h5py、NumPy、psutil、CST IdEM 2026.02 CLI、pytest。

## Global Constraints

- 输入固定为 s19，SHA-256 `87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`，826 个原始频点。
- 主实验 `splitting=none`，线程 8，`orderMin=4`、`orderStep=2`、`orderMax=100`、`tol=0.001`。
- fitting/passivity 单阶段 timeout 7200 秒。
- 最终成功要求 independent mean S-RMS `<= 0.001`、authoritative passive、sampled max sigma `<= 1.000001`。
- 所有 accepted 模型必须 export 为 Touchstone 并在原始 826 点严格审计，不插值。
- fixed-order 与 adaptive options 不得混用。
- IdEM return code 1 继续按 artifact 和 stdout marker 判断成功。
- 单变量阶段后只组合有实测改善的参数；frequency weighting 和 splitting 均有 stop rule。
- 每个任务 TDD、代码审查、独立提交。

---

### Task 1: 定义 adaptive options 和 advanced XML

**Files:**
- Modify: `src/agent_spice/sparam/idem.py`
- Modify: `tests/test_sparam_idem.py`

**Interfaces:**
- Produces: `IdemAdaptiveFittingOptions`。
- Produces: `render_adaptive_fitting_options_xml(options) -> str`。
- Produces: `write_adaptive_fitting_options_xml(options, path) -> Path`。

- [ ] **Step 1: 写 dataclass validation 和 XML RED**

```python
def test_adaptive_xml_omits_reserved_order_and_bandwidth():
    options = IdemAdaptiveFittingOptions()
    xml = render_adaptive_fitting_options_xml(options)
    assert "<order>" not in xml
    assert "<bandwidth" not in xml
    assert "<enhancePolesPlacement>true</enhancePolesPlacement>" in xml


@pytest.mark.parametrize("kwargs", [
    {"initial_iterations": -1},
    {"postadding_iterations": 0},
    {"stagnation_alpha": 0.0},
    {"skimming_tolerance": -1.0},
    {"split_type": "puzzle"},
])
def test_adaptive_options_fail_closed(kwargs):
    with pytest.raises(ValueError):
        IdemAdaptiveFittingOptions(**kwargs)
```

- [ ] **Step 2: 运行 RED**

```powershell
python -m pytest tests/test_sparam_idem.py -q
```

- [ ] **Step 3: 实现完整 options**

```python
@dataclass(frozen=True)
class IdemAdaptiveFittingOptions:
    initial_iterations: int = 3
    postadding_iterations: int = 1
    final_iterations: int = 1
    enhance_poles_placement: bool = False
    stagnation_alpha: float = 0.05
    stagnation_back_steps: int = 3
    skimming_tolerance: float = 1e-3
    final_skimming_tolerance: float = 1e-3
    guaranteed_accuracy: float = 0.1
    split_type: str = "none"
    p4poles_type: str = "all"
    p4poles_n_largest: str = "INF"
    p4res_type: str = "all"
    enforce_dc: bool = True
    enforce_asymptotic_passivity: bool = True
    asymptotic_passivity_margin: float = 1e-3
    asymptotic_relocate_poles: bool = False
    reject_poles: bool = False
    reject_poles_max_relative_frequency: float = math.inf
    relative_frequency_weight_alpha: float | None = None
    relative_frequency_weight_threshold: float = 1e-10
    absolute_frequency_weight_points: tuple[tuple[float, float], ...] = ()
```

XML 必须包含官方 help 中同名节点；relative 与 absolute weights 互斥。

- [ ] **Step 4: GREEN 和 XML parse 检查**

```powershell
python -m pytest tests/test_sparam_idem.py -q
```

使用 `xml.etree.ElementTree.fromstring()` 确认 XML well-formed。

- [ ] **Step 5: 提交**

```powershell
git add src/agent_spice/sparam/idem.py tests/test_sparam_idem.py
git commit -m "feat: define IdEM adaptive fitting options"
```

---

### Task 2: 实现 adaptive fitting CLI adapter

**Files:**
- Modify: `src/agent_spice/sparam/idem.py`
- Modify: `tests/test_sparam_idem.py`

**Interfaces:**
- Produces: `run_idem_adaptive_fitting(touchstone_path, model_path, *, order_min, order_step, order_max, target, bandwidth_hz, threads, options_xml_path, idem_bin_dir=None, timeout_seconds=None) -> dict[str, Any]`。

- [ ] **Step 1: 写精确命令 RED**

```python
assert command == [
    str(bin_dir / "idemmp_fitting.exe"),
    "-its", str(touchstone),
    "-o", str(model),
    "-tol", "0.001",
    "-orderMin", "4",
    "-orderStep", "2",
    "-orderMax", "100",
    "-bandwidth", "2000000000",
    "-DC", "1",
    "-nThreads", "8",
    "-xml", str(xml_path),
]
```

另写 stale output、missing model、invalid order range 和 timeout propagation 测试。

- [ ] **Step 2: 运行 RED 并实现 wrapper**

调用前删除 stale model。成功要求：model 非空、stdout 不含 `Error:`，且 returncode 0 或 stdout 含 `End of model build`。

返回值包含 command、status、paths 和 `inspect_idem_model()` 摘要。

- [ ] **Step 3: 运行 GREEN 和真实 help 对照**

```powershell
python -m pytest tests/test_sparam_idem.py -q
& 'C:\Program Files\CST Studio Suite 2026\AMD64\idemmp_fitting.exe' -help
```

- [ ] **Step 4: 提交**

```powershell
git add src/agent_spice/sparam/idem.py tests/test_sparam_idem.py
git commit -m "feat: run IdEM adaptive order refinement"
```

---

### Task 3: 实现单个 adaptive trial pipeline 和 resume

**Files:**
- Create: `scripts/sparam_idem_s19_tuning.py`
- Create: `tests/test_sparam_idem_s19_tuning.py`
- Modify: `src/agent_spice/sparam/benchmark.py` only if shared serialization helper is needed

**Interfaces:**
- Produces: `IdemAdaptiveTrialConfig`，包含 order contract 和 advanced options。
- Produces: `run_adaptive_trial(entry, config, output_dir, *, resume=True, idem_bin_dir=None) -> ToolTrial`。
- Produces phase files: `fit.json`、`history.json`、`pre_accuracy.json`、`enforce.json`、`final_accuracy.json`、`final_check.json`、`export.json`、`audit.json`、`trial.json`。

- [ ] **Step 1: 写 pipeline RED**

fake adapters 覆盖：

- pre-RMS 超目标时跳过 passivity，但保存 history。
- post-enforcement RMS 超目标时 FAIL。
- check-only non-passive 时 FAIL。
- exported grid mismatch 时 INVALID。
- successful audit 时 PASS。
- model final order 超过 100 时 INVALID。
- truncated trial JSON 或 fingerprint mismatch 时重跑。
- exact valid fingerprint 时零 phase 调用。

- [ ] **Step 2: 运行 RED**

```powershell
python -m pytest tests/test_sparam_idem_s19_tuning.py -q
```

- [ ] **Step 3: 实现 fingerprint 和阶段状态机**

fingerprint payload：

```python
{
    "contract_version": "idem_s19_adaptive_v1",
    "input_sha256": entry.sha256,
    "idem_identity": idem_tool_identity(...),
    "validation_identity": benchmark_implementation_identity(),
    "trial_config": config.to_dict(),
}
```

验收顺序固定为 fit -> inspect -> pre accuracy -> conditional enforce -> final accuracy -> check-only -> export -> audit。

- [ ] **Step 4: 实现 history normalization**

`history.json` 至少包含：

```python
{
    "error_history": model["error_history"],
    "orders_history": model["orders_history"],
    "pole_blocks": model["pole_blocks"],
    "final_order": model["order"],
    "total_pole_count": model["total_pole_count"],
}
```

长度不一致或非有限 history 标记 warning，不伪造对齐数据。

- [ ] **Step 5: GREEN、review、commit**

```powershell
python -m pytest tests/test_sparam_idem_s19_tuning.py tests/test_sparam_idem.py tests/test_sparam_benchmark.py -q
git add scripts/sparam_idem_s19_tuning.py tests/test_sparam_idem_s19_tuning.py src/agent_spice/sparam/benchmark.py
git commit -m "feat: run resumable IdEM adaptive trials"
```

---

### Task 4: 建立 staged experiment manifest 和 summary

**Files:**
- Modify: `scripts/sparam_idem_s19_tuning.py`
- Modify: `tests/test_sparam_idem_s19_tuning.py`
- Create: `configs/idem-s19-adaptive-v1.json`

**Interfaces:**
- Produces: `build_stage1_trials() -> tuple[IdemAdaptiveTrialConfig, ...]`。
- Produces: `run_experiment(input_path, output_root, *, stage, resume=True) -> dict[str, Any]`。
- Produces: `summarize_trials(trials) -> dict[str, Any]`。

- [ ] **Step 1: 写 deterministic manifest RED**

断言 trial id 唯一、排序稳定、每个 trial 相对 baseline 只改变一组机制参数。必须包含：

```text
baseline-adaptive
enhanced-placement
postadding-2
postadding-3
iterations-initial5-final3
stagnation-alpha0p01
stagnation-alpha0p001
stagnation-back5
guaranteed-0p01
guaranteed-0p001
skimming-1e-4
skimming-1e-5
final-skimming-1e-4
final-skimming-1e-5
reject-poles-1p0
reject-poles-1p2
reject-poles-2p0
asymptotic-relocate
p4poles-eye
p4poles-largest4
p4poles-largest8
```

- [ ] **Step 2: 实现 manifest 和 sequential runner**

一个时刻只允许一个 IdEM trial。每个 trial 完成后原子更新 `summary.partial.json`。

- [ ] **Step 3: 实现 summary ranking**

排序键：

```python
(
    not target_met,
    final_mean_rms_or_inf,
    final_order_or_inf,
    elapsed_seconds_or_inf,
)
```

同时计算相对 baseline 的 pre-RMS 改善比例、order 差、时间和内存差。

- [ ] **Step 4: GREEN 和 commit**

```powershell
python -m pytest tests/test_sparam_idem_s19_tuning.py -q
git add scripts/sparam_idem_s19_tuning.py tests/test_sparam_idem_s19_tuning.py configs/idem-s19-adaptive-v1.json
git commit -m "feat: define staged IdEM s19 experiment"
```

---

### Task 5: 真实 adaptive smoke

**Files:**
- Modify only Task 1-4 files when smoke exposes a verified defect.

- [ ] **Step 1: 运行完整回归**

```powershell
python -m pytest -q
```

- [ ] **Step 2: 运行 2-port adaptive smoke**

```powershell
python scripts/sparam_idem_s19_tuning.py run-one `
  --input tests/fixtures/sparam/simple_through.s2p `
  --output-root runs-sparam/idem-adaptive-smoke `
  --order-min 2 --order-step 1 --order-max 8 `
  --target 0.5 --threads 8 --resume
```

要求：history 可解析、最终 passive、export grid 与 5 点输入一致。

- [ ] **Step 3: 运行 s19 bounded smoke**

```powershell
python scripts/sparam_idem_s19_tuning.py run-one `
  --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output-root runs-sparam/idem-s19-adaptive-smoke `
  --order-min 4 --order-step 2 --order-max 12 `
  --target 0.001 --threads 8 --resume
```

不要求达到目标，但要求 826 点、history、order cap、resume 和失败原因有效。

- [ ] **Step 4: 重跑两条命令验证零算法 resume**

phase artifacts mtime 不变，summary byte-identical。

- [ ] **Step 5: 修正缺陷后提交**

仅当 smoke 暴露真实缺陷才提交：

```powershell
git add src/agent_spice/sparam/idem.py scripts/sparam_idem_s19_tuning.py tests/test_sparam_idem.py tests/test_sparam_idem_s19_tuning.py
git commit -m "fix: validate IdEM adaptive smoke"
```

---

### Task 6: 执行 s19 第一阶段单变量实验

**Files:**
- Generate: `runs-sparam/idem-s19-adaptive-v1/manifest.json`
- Generate: `runs-sparam/idem-s19-adaptive-v1/summary.json`
- Generate: `runs-sparam/idem-s19-adaptive-v1/summary.csv`

- [ ] **Step 1: 运行 fixed-order 对照和 adaptive baseline**

```powershell
python scripts/sparam_idem_s19_tuning.py run-stage `
  --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output-root runs-sparam/idem-s19-adaptive-v1 `
  --stage baseline --threads 8 --resume
```

确认 fixed-order order100 结果与旧 benchmark 同量级；adaptive baseline 记录真实 order history。

- [ ] **Step 2: 运行 stage1**

```powershell
python scripts/sparam_idem_s19_tuning.py run-stage `
  --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output-root runs-sparam/idem-s19-adaptive-v1 `
  --stage single-variable --threads 8 --resume
```

- [ ] **Step 3: 审计每个 trial**

检查 input SHA、826 点、order history、final order <=100、model existence、非有限指标、passivity 和 audit agreement。

- [ ] **Step 4: 应用 stop rule**

若任一 splitting-none trial 已满足最终合同，进入 Task 9 报告；仍可运行最多三个有解释价值的组合，不再铺开全部参数。

若没有成功 trial，进入 Task 7。

---

### Task 7: 生成并执行有效参数组合

**Files:**
- Modify: `runs-sparam/idem-s19-adaptive-v1/manifest.json` through runner-generated combination stage
- Generate: combination trial directories

- [ ] **Step 1: 选择有效参数**

候选满足以下至少一项：pre-RMS 相对 adaptive baseline 改善 20%；相同/更低 order 下 RMS 更低；变为 target PASS；使 passivity 可修且 final RMS 不超目标。

- [ ] **Step 2: 生成确定性组合**

最多选择三个不同机制参数。先生成所有两两组合；只有两个参数组合继续改善时，才生成三参数组合。禁止组合两个仅数值不同但机制相同的参数，例如两个 alpha。

- [ ] **Step 3: 执行组合 stage**

```powershell
python scripts/sparam_idem_s19_tuning.py run-stage `
  --input user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p `
  --output-root runs-sparam/idem-s19-adaptive-v1 `
  --stage combinations --threads 8 --resume
```

`combinations` 是 CLI 兼容 alias，等价于 canonical stage 名 `combination`；两种拼写均应保持可复现。

- [ ] **Step 4: 决策**

若成功，进入 Task 9。若最佳 RMS 仍大于 `0.001`，但 residual 集中于稳定频段，进入 Task 8 weighting；否则直接进入 splitting eligibility 检查。

---

### Task 8: 条件 frequency weighting 与 splitting 对照

**Files:**
- Modify: `scripts/sparam_idem_s19_tuning.py`
- Modify: `tests/test_sparam_idem_s19_tuning.py`
- Generate: conditional trial directories

- [ ] **Step 1: 计算无权 residual band**

从最佳 exported model 和原始 s19 流式计算每个频点的 aggregate RMS/max error，输出 `residual_by_frequency.csv`。

- [ ] **Step 2: 仅在误差集中时生成权重**

若最差连续频带贡献至少 50% 总平方误差，生成 2-4 个 anchor；权重限制 `[1e-3, 1]`。否则记录 `weighting_not_justified`，不运行 weighting trial。

- [ ] **Step 3: 执行 weighting 并用无权指标验收**

最多运行 baseline weight 和增强一次的两个 trial。加权训练误差不得进入 acceptance。

- [ ] **Step 4: splitting eligibility**

流式计算 reciprocity RMS：

```python
sqrt(mean(abs(S_ij - S_ji) ** 2))
```

若 IdEM/数据判断 reciprocal，记录 `splitting_disallowed_for_reciprocal_data` 并停止。若非 reciprocal，运行 column；只有 column 仍失败时运行 all 精度上限。

- [ ] **Step 5: splitting 复杂度记录**

保存 total states、max split order、SPICE bytes。不得生成公共 order ratio。

---

### Task 9: 生成 canonical s19 调参报告

**Files:**
- Create: `docs/sparam-idem-s19-tuning.md`
- Modify: `README.md`
- Modify: `scripts/sparam_idem_s19_tuning.py`
- Modify: `tests/test_sparam_idem_s19_tuning.py`

**Interfaces:**
- Produces: `render_s19_tuning_markdown(summary) -> str`。

- [ ] **Step 1: 写报告 snapshot RED**

报告必须包含：合同、输入 SHA、fixed/adaptive 区别、每个 stage、最佳配置、order/error histories、最终 RMS/sigma/time/memory、事实/强推断/假设标签、可复现命令。

- [ ] **Step 2: 实现 JSON -> CSV/Markdown 纯生成器**

禁止读取历史结论文档。缺失值显示 `N/A`，失败显示 `FAIL/INVALID`，不写无证据算法结论。

- [ ] **Step 3: 生成真实报告**

```powershell
python scripts/sparam_idem_s19_tuning.py report `
  --output-root runs-sparam/idem-s19-adaptive-v1 `
  --markdown docs/sparam-idem-s19-tuning.md
```

- [ ] **Step 4: 二次 resume 与 byte identity**

重跑 stage/report，确认不执行算法，summary.csv 和 Markdown byte-identical。

- [ ] **Step 5: 全量测试、review、commit**

```powershell
python -m pytest -q
git diff --check
git add docs/sparam-idem-s19-tuning.md README.md scripts/sparam_idem_s19_tuning.py tests/test_sparam_idem_s19_tuning.py
git commit -m "bench: tune IdEM adaptive fitting on s19"
```

## Completion Gate

- adaptive command/XML、history、resume 和 audit 均通过真实 smoke。
- splitting none 单变量阶段全部完成或明确 bounded failure。
- 只组合有证据参数，frequency weighting/splitting 遵守 stop rule。
- 每个 accepted model 满足 `RMS <=0.001 + authoritative passive + sampled sigma <=1.000001`。
- 若无成功模型，报告仍给出最佳 RMS/order、history 和明确失败原因。
- canonical 报告可复现、byte-stable，完整测试通过。
