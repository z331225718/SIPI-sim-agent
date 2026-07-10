# Native 生产基线固化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 Native S 参数 fitting/passivity 版本固化为唯一生产基线，移除 skrf fitting/relocation 算法入口，同时保留 skrf 非 fitting 基础能力。

**Architecture:** `fit-sparam` 和 Python fitting API 始终创建 `NativeVectorFitting`；端口规模决定内部 streaming 或 reciprocal relocation，不再由用户选择 backend。Native 使用的 relocation 数值代码迁移到独立模块，skrf 只在 Touchstone fallback、metrics、modal 和研究工具中延迟加载。

**Tech Stack:** Python 3.11+、NumPy、SciPy、现有 NativeVectorFitting、Hamiltonian passivity、pytest。

## Global Constraints

- 当前数值基线命名为 `native-idem-fast-v1`。
- 小于 30 端口使用 streaming relocation；大于等于 30 端口使用 streaming reciprocal relocation。
- 不改变当前 pole placement、residue solve、passivity 参数及 target-driven order search 行为。
- 删除 skrf VectorFitting 和 skrf reference relocation 的生产入口。
- 将 exporter `skrf` 重命名为 `native`；保留 `idem` exporter。
- 保留 skrf 包和非 fitting 功能。
- Native 主路径不得导入 `skrf` 或 `skrf.vectorFitting`。
- 使用 TDD，每个任务完成后代码审查并独立提交。
- 不暂存或修改 `.reasonix`、`.workbuddy`、pole-discovery 和 passivity probe 的用户改动。

---

### Task 1: 定义并传播 Native 基线版本

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/sparam/benchmark.py`
- Modify: `scripts/sparam_full_corpus_benchmark.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_sparam_full_corpus_benchmark.py`

**Interfaces:**
- Produces: `NATIVE_BASELINE_VERSION = "native-idem-fast-v1"`。
- Produces: `SParamFitResult.to_dict()["native_baseline_version"]`。
- Consumes: target trial 和 full-corpus fingerprint options。

- [ ] **Step 1: 写报告和 fingerprint 的失败测试**

在 `tests/test_sparam_fitting.py` 增加：

```python
def test_native_baseline_version_is_stored_in_fit_report(tmp_path, monkeypatch):
    result = _run_small_native_fit(tmp_path, monkeypatch)
    payload = result.to_dict()
    assert payload["native_baseline_version"] == "native-idem-fast-v1"
```

在 `tests/test_sparam_full_corpus_benchmark.py` 的 Native process fake 中捕获 fingerprint options，断言包含同一版本。

- [ ] **Step 2: 运行 RED**

Run:

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_sparam_full_corpus_benchmark.py -q
```

Expected: 缺少 `native_baseline_version`。

- [ ] **Step 3: 实现版本常量和序列化**

在 `fitting.py` 顶层定义：

```python
NATIVE_BASELINE_VERSION = "native-idem-fast-v1"
```

给 `SParamFitResult` 增加字段并在所有构造点赋值。target trial fingerprint 和 `run_native_target_search()` 的 options 必须加入：

```python
{"native_baseline_version": NATIVE_BASELINE_VERSION}
```

- [ ] **Step 4: 运行 GREEN 和导入回归**

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_sparam_full_corpus_benchmark.py tests/test_sparam_imports.py -q
```

Expected: 全部通过，Native import 不加载 skrf。

- [ ] **Step 5: 代码审查并提交**

检查版本只在 Native 数值行为变化时参与 fingerprint，不加入生成时间。

```powershell
git add src/agent_spice/sparam/fitting.py src/agent_spice/sparam/benchmark.py scripts/sparam_full_corpus_benchmark.py tests/test_sparam_fitting.py tests/test_sparam_full_corpus_benchmark.py
git commit -m "feat: version Native S-parameter baseline"
```

---

### Task 2: 将 Native relocation 从 skrf 模块迁出

**Files:**
- Create: `src/agent_spice/sparam/pole_relocation.py`
- Delete: `src/agent_spice/sparam/skrf_streaming.py`
- Modify: `src/agent_spice/sparam/native_vf.py`
- Create: `tests/test_sparam_pole_relocation.py`
- Delete: `tests/test_sparam_skrf_streaming.py`

**Interfaces:**
- Produces: `streaming_pole_relocation(...)`，保持现有签名和返回值。
- Produces: `streaming_reciprocal_pole_relocation(...)`，保持现有签名和返回值。
- Removes: `streaming_relocation_patch()` 和 `streaming_lowmem_pole_relocation()`。

- [ ] **Step 1: 先迁移测试名称和 imports，形成 RED**

将 `tests/test_sparam_skrf_streaming.py` 中 Native 仍需的测试移动到 `tests/test_sparam_pole_relocation.py`，import 改为：

```python
from agent_spice.sparam.pole_relocation import (
    streaming_pole_relocation,
    streaming_reciprocal_pole_relocation,
)
```

删除仅验证 `streaming_lowmem_pole_relocation` 和 monkey patch skrf 类的测试。保留以下行为覆盖：

- 与已保存数值 reference 一致。
- reciprocal 对称矩阵与 full streaming 一致。
- c_res diagnostics。
- 带外 c_res regularization。
- 不分配 stacked real/imag 大临时矩阵。

- [ ] **Step 2: 运行 RED**

```powershell
python -m pytest tests/test_sparam_pole_relocation.py -q
```

Expected: `ModuleNotFoundError: agent_spice.sparam.pole_relocation`。

- [ ] **Step 3: 用 Git 可审计迁移实现**

通过 `apply_patch` 创建 `pole_relocation.py`，复制当前 streaming 与 reciprocal 所需实现和共享私有 helper。不得保留：

```python
from skrf.vectorFitting import VectorFitting
streaming_relocation_patch
streaming_lowmem_pole_relocation
```

修改 `native_vf.py`：

```python
from .pole_relocation import streaming_pole_relocation
```

- [ ] **Step 4: 删除旧模块并运行 GREEN**

```powershell
python -m pytest tests/test_sparam_pole_relocation.py tests/test_sparam_native_vf.py tests/test_sparam_imports.py -q
rg -n "skrf_streaming|streaming_relocation_patch|streaming_lowmem_pole_relocation" src tests
```

Expected: tests 全部通过；`rg` 无生产引用。

- [ ] **Step 5: 代码审查并提交**

对比迁移前后函数体，确认没有数值常量、矩阵形状和返回顺序变化。

```powershell
git add src/agent_spice/sparam/pole_relocation.py src/agent_spice/sparam/native_vf.py tests/test_sparam_pole_relocation.py
git add -u -- src/agent_spice/sparam/skrf_streaming.py tests/test_sparam_skrf_streaming.py
git commit -m "refactor: move Native pole relocation out of skrf module"
```

---

### Task 3: 删除 skrf fitting backend 和 relocation 选择

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_cli_fit_sparam.py`
- Modify: `tests/test_sparam_imports.py`
- Delete or rewrite: `tests/test_sparam_public_skrf_contract.py`

**Interfaces:**
- Produces: `_native_relocation_mode(nports: int) -> Literal["streaming", "streaming-reciprocal"]`。
- Changes: `_create_vector_fitting(network, config)` 始终返回 `NativeVectorFitting`。
- Removes: `SParamFitConfig.vector_fit_backend`。
- Removes: `SParamFitConfig.relocation_backend`。
- Removes CLI: `--vector-fit-backend`、`--relocation-backend`。

- [ ] **Step 1: 写唯一 backend 和端口策略失败测试**

```python
@pytest.mark.parametrize(("ports", "expected"), [(2, "streaming"), (19, "streaming"), (30, "streaming-reciprocal"), (166, "streaming-reciprocal")])
def test_native_relocation_mode_is_internal_and_port_scaled(ports, expected):
    assert fitting._native_relocation_mode(ports) == expected


def test_sparam_config_no_longer_accepts_vector_backend():
    with pytest.raises(TypeError):
        SParamFitConfig(vector_fit_backend="skrf")
```

CLI 测试断言 parser 不接受两个旧 flag，正常 `fit-sparam` 仍构造 Native 配置。

- [ ] **Step 2: 运行 RED**

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py -q
```

Expected: 旧字段仍存在、旧 flag 仍可解析。

- [ ] **Step 3: 简化 fitting 创建和 relocation 调用**

删除 `_LazyVectorFitting`。`_create_vector_fitting()` 直接：

```python
def _create_vector_fitting(network: Any, config: SParamFitConfig) -> NativeVectorFitting:
    vector_fit = NativeVectorFitting(network)
    _configure_native_vector_fitting(vector_fit, config)
    return vector_fit
```

Native relocation mode 在创建后根据 `network.nports` 设置：

```python
vector_fit._pole_relocation = (
    streaming_reciprocal_pole_relocation
    if network.nports >= 30
    else streaming_pole_relocation
)
```

删除 `_fit_model()` 的 skrf monkey-patch 分支，直接调用 `_fit_model_inner()`。

- [ ] **Step 4: 精简 CLI 和 preset**

删除 parser flags、preset override、config wiring 和相关显式参数兼容逻辑。正常用户参数和 target-driven fitting 语义不得变化。

- [ ] **Step 5: 更新测试并运行 GREEN**

删除只测试 skrf backend/patch 的 Fake 类和用例；其余 FakeVectorFitting 测试改为 monkeypatch `_create_vector_fitting` 或 `NativeVectorFitting`，不能为了测试重新引入生产 backend 选择。

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py tests/test_sparam_native_vf.py tests/test_sparam_imports.py -q
```

- [ ] **Step 6: 代码审查并提交**

```powershell
rg -n "vector_fit_backend|relocation_backend|skrf.vectorFitting" src/agent_spice/cli.py src/agent_spice/sparam/fitting.py
git diff --check
git add src/agent_spice/sparam/fitting.py src/agent_spice/cli.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py tests/test_sparam_imports.py
git add -u -- tests/test_sparam_public_skrf_contract.py
git commit -m "refactor: make Native the only S-parameter fitting backend"
```

Expected: `rg` 无命中。

---

### Task 4: 重命名 Native exporter 并保持 IdEM-style exporter

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `src/agent_spice/cli.py`
- Modify: `tests/test_sparam_fitting.py`
- Modify: `tests/test_cli_fit_sparam.py`

**Interfaces:**
- Changes: `SParamFitConfig.exporter` choices 为 `"native" | "idem"`，默认 `"native"`。
- Removes: exporter value `"skrf"`。

- [ ] **Step 1: 写 exporter 失败测试**

```python
def test_default_exporter_is_native():
    assert SParamFitConfig().exporter == "native"


def test_cli_rejects_removed_skrf_exporter(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["fit-sparam", str(tmp_path / "x.s2p"), "--output", str(tmp_path / "x.sp"), "--rms-target", "0.1", "--exporter", "skrf"])
```

- [ ] **Step 2: 运行 RED**

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py -q
```

- [ ] **Step 3: 重命名配置和 CLI choice**

默认分支直接调用：

```python
vector_fit.write_spice_subcircuit_s(...)
```

`exporter == "idem"` 继续调用现有 `write_idem_spice_subcircuit()`。

- [ ] **Step 4: 运行 GREEN 和 SPICE smoke**

```powershell
python -m pytest tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py tests/test_sparam_native_vf.py -q
python -m agent_spice.cli fit-sparam tests/fixtures/sparam/simple_through.s2p --output runs-sparam/native-baseline-smoke/model.sp --rms-target 0.5 --passivity enforce --max-order 4
```

Expected: model 和 report 生成，report baseline version 正确。

- [ ] **Step 5: 提交**

```powershell
git add src/agent_spice/sparam/fitting.py src/agent_spice/cli.py tests/test_sparam_fitting.py tests/test_cli_fit_sparam.py
git commit -m "refactor: rename default S-parameter exporter to Native"
```

---

### Task 5: 文档、兼容扫描和完整基线验收

**Files:**
- Modify: `README.md`
- Modify: `docs/sparam-fit-performance.md`
- Modify: `docs/sparam-idem-full-benchmark.md` only if generated contract wording refers to removed options
- Test: `tests/test_benchmark_documentation.py`

**Interfaces:**
- Produces: 用户文档只描述 Native production fitting。
- Preserves: skrf non-fitting dependency and documentation where relevant。

- [ ] **Step 1: 写文档失败测试**

断言 README 的生产 CLI 不包含 `--vector-fit-backend`、`--relocation-backend` 或 `--exporter skrf`，并包含 `native-idem-fast-v1`。

- [ ] **Step 2: 运行 RED 并更新文档**

```powershell
python -m pytest tests/test_benchmark_documentation.py -q
```

README 说明：Native 是唯一 fitting backend；skrf 只用于格式/metrics/modal 等辅助功能。

- [ ] **Step 3: 全仓引用扫描**

```powershell
rg -n "vector_fit_backend|relocation_backend|exporter.*skrf|skrf_streaming" src tests README.md docs
```

允许命中仅限历史设计/计划和明确的非生产 skrf 功能；生产代码不得命中。

- [ ] **Step 4: 全量测试和 import smoke**

```powershell
python -m pytest -q
python -c "import sys; import agent_spice.sparam.fitting; assert 'skrf' not in sys.modules"
git diff --check
```

Expected: 全部通过。

- [ ] **Step 5: 提交**

```powershell
git add README.md docs/sparam-fit-performance.md docs/sparam-idem-full-benchmark.md tests/test_benchmark_documentation.py
git commit -m "docs: establish Native S-parameter production baseline"
```

## Completion Gate

- Native 是唯一 fitting backend。
- CLI/API 不再接受 skrf fitting 或 relocation 选择。
- Native relocation 数值代码不位于 skrf 命名模块。
- 默认 exporter 为 native。
- Native 主路径不导入 skrf。
- 基线版本进入报告和 fingerprint。
- 2-port smoke 与全仓测试通过。
- 用户未提交研究改动保持原样。
