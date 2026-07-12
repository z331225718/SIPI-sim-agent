# stabAAA 固定阶数共享极点验证实施计划

> **供 agentic workers 执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。所有步骤使用 checkbox 跟踪。

**目标：** 建立隔离、可复现的研究管线，用多组标量投影驱动原版 stabAAA，在固定阶数下形成多端口共享极点，并通过现有 Native residue LS/enforcement 与 Native、IdEM 做公平对比。

**架构：** Python 负责投影、artifact、候选极点聚类、固定阶数选择、attribution 和报告；MATLAB wrapper 只调用固定 commit 的原版 `stab_AAA.m`。研究代码全部位于 `scripts/`，不被生产 CLI 或 `src/agent_spice` 导入；阶段之间只交换 JSON、NPZ 和 MAT artifact。

**技术栈：** Python 3、NumPy、scikit-rf、pytest、MATLAB、YALMIP、MOSEK、现有 `scripts.sparam_passivity_source_attribution`。

## 全局约束

- 本计划是研究验证 spike，不修改生产拟合后端、CLI、默认算法、residue LS 或 passivity enforcement 数学。
- 固定目标阶数只能是 `6`、`8`、`10`、`13`；不允许按结果动态加阶。
- 公开 stabAAA 只按外部工具运行，不复制其源码进仓库；每次运行必须记录外部 commit SHA。
- IdEM 极点只用于 attribution 对照和事后距离诊断，不得进入候选生成、聚类或选择评分。
- 真实 Test16/s19 不进入默认单元测试；默认测试必须使用合成数据或 fake MATLAB 输出。
- 所有随机投影使用显式种子；Test16 与 s19 使用同一 seed 列表。
- 每个数值报告只从 `summary.json` 生成，Markdown 不得成为第二事实源。

---

## 文件结构

- 新建 `scripts/sparam_stabaaa_projection.py`：纯 Python 投影生成、归一化、artifact 指纹与序列化。
- 新建 `scripts/matlab_stabaaa_projection_runner.m`：调用外部原版 `stab_AAA.m`，输出单投影 MAT/JSON 结果。
- 新建 `scripts/sparam_stabaaa_poles.py`：候选合法性、共轭规范化、聚类、评分和固定阶数选择。
- 新建 `scripts/sparam_stabaaa_validation.py`：阶段编排、provenance、Native/IdEM attribution、决策与报告。
- 新建 `tests/test_sparam_stabaaa_projection.py`：投影和可复现性单测。
- 新建 `tests/test_sparam_stabaaa_poles.py`：极点处理和选择单测。
- 新建 `tests/test_sparam_stabaaa_validation.py`：runner 失败、attribution、决策、artifact 与 CLI 单测。

### Task 1：生成可复现的标量投影 artifact

**文件：**
- 新建：`scripts/sparam_stabaaa_projection.py`
- 新建：`tests/test_sparam_stabaaa_projection.py`

**接口：**
- 消费：`RawTouchstone`，其 `s.shape == (frequency_count, nports, nports)`。
- 产出：`ProjectionSpec`、`ProjectionRecord`、`build_projection_records`、`write_projection_artifacts`。
- 后续任务依赖：`projections.npz` 中键名 `response_<projection_id>`；`projections.json` 中保存定义和 SHA-256。

- [ ] **Step 1：写投影公式和固定种子失败测试**

```python
def test_tangential_projection_matches_u_h_s_v_and_is_reproducible():
    s = np.arange(24, dtype=float).reshape(3, 2, 4)[:, :, :2].astype(complex)
    first = projection.build_projection_records(s, seeds=(17,), key_channels=(), diagonal_count=0)
    second = projection.build_projection_records(s, seeds=(17,), key_channels=(), diagonal_count=0)
    record = first[0]
    expected = np.einsum("i,fij,j->f", np.conj(record.left), s, record.right)
    assert np.allclose(record.response * record.scale, expected)
    assert record.to_metadata() == second[0].to_metadata()
    assert np.array_equal(record.response, second[0].response)
```

- [ ] **Step 2：写关键通道、对角能量和退化投影测试**

```python
def test_projection_family_is_data_driven_and_skips_degenerate_response():
    s = np.zeros((5, 2, 2), dtype=complex)
    s[:, 0, 1] = np.array([0, 1, 0, 2, 0])
    records = projection.build_projection_records(
        s, seeds=(), key_channels=((0, 1),), diagonal_count=2, min_dynamic_range=1e-12
    )
    assert [item.kind for item in records] == ["channel"]
    assert records[0].row == 0 and records[0].column == 1
```

- [ ] **Step 3：运行测试，确认模块尚不存在**

运行：`python -m pytest tests/test_sparam_stabaaa_projection.py -q`

预期：FAIL，`ModuleNotFoundError: scripts.sparam_stabaaa_projection`。

- [ ] **Step 4：实现投影数据类型与生成函数**

```python
@dataclass(frozen=True)
class ProjectionSpec:
    projection_id: str
    kind: Literal["channel", "diagonal", "tangential"]
    row: int | None = None
    column: int | None = None
    seed: int | None = None

@dataclass
class ProjectionRecord:
    spec: ProjectionSpec
    response: np.ndarray
    scale: complex
    left: np.ndarray | None = None
    right: np.ndarray | None = None

def build_projection_records(
    s: np.ndarray,
    *,
    seeds: tuple[int, ...],
    key_channels: tuple[tuple[int, int], ...],
    diagonal_count: int,
    min_dynamic_range: float = 1e-12,
) -> list[ProjectionRecord]:
    """Return normalized non-degenerate channel, diagonal and tangential projections."""
```

实现要求：随机向量用 `np.random.default_rng(seed)` 生成独立实部/虚部后归一化；`scale` 是全频率统一的最大绝对值；对角通道按 `sum(abs(diff(response))**2)` 排序；退化项返回结构化 skip metadata，不写空 response。

- [ ] **Step 5：实现 artifact 写出和输入指纹**

```python
def write_projection_artifacts(
    output_dir: Path,
    *,
    frequencies_hz: np.ndarray,
    records: Sequence[ProjectionRecord],
    input_sha256: str,
) -> dict[str, Any]:
    """Atomically write projections.npz and projections.json and return the JSON manifest."""
```

- [ ] **Step 6：运行投影测试**

运行：`python -m pytest tests/test_sparam_stabaaa_projection.py -q`

预期：PASS。

- [ ] **Step 7：提交**

```powershell
git add scripts/sparam_stabaaa_projection.py tests/test_sparam_stabaaa_projection.py
git commit -m "test(sparam): add stabAAA projection artifacts"
```

### Task 2：建立不修改原算法的 MATLAB runner 契约

**文件：**
- 新建：`scripts/matlab_stabaaa_projection_runner.m`
- 修改：`scripts/sparam_stabaaa_validation.py`（本任务先建立 runner 调用与解析骨架）
- 新建：`tests/test_sparam_stabaaa_validation.py`

**接口：**
- 消费：`projections.npz` 导出的单投影 MAT 文件、外部 `stabaaa_root`、`tol`、`mmax`、`con_type`。
- 产出：`stabaaa/<projection-id>.mat` 和同名 JSON，字段固定为 `status`、`projection_id`、`poles_rad_per_s`、`support_points`、`weights`、`error_history`、`elapsed_seconds`、`solver_status`、`failure_reason`。

- [ ] **Step 1：写 Python 结果解析和失败保真测试**

```python
def test_parse_runner_result_rejects_silent_fallback(tmp_path):
    result = tmp_path / "p0.json"
    result.write_text(json.dumps({
        "status": "failed",
        "projection_id": "p0",
        "failure_reason": "mosek_infeasible",
        "fallback": "aaa",
    }), encoding="utf-8")
    parsed = validation.parse_stabaaa_result(result)
    assert parsed.status == "failed"
    assert parsed.failure_reason == "mosek_infeasible"
    assert parsed.poles.size == 0
```

- [ ] **Step 2：运行测试确认失败**

运行：`python -m pytest tests/test_sparam_stabaaa_validation.py -q -k runner`

预期：FAIL，解析接口不存在。

- [ ] **Step 3：实现 MATLAB wrapper**

```matlab
function matlab_stabaaa_projection_runner(input_mat, output_mat, output_json, ...
        stabaaa_root, projection_id, tol, mmax, con_type)
    addpath(fullfile(stabaaa_root, 'Source'));
    payload = load(input_mat);
    started = tic;
    try
        [~, om, ff, weights, errvec, poles] = stab_AAA(...
            payload.response, payload.omega_rad_per_s, tol, mmax, con_type);
        status = 'completed';
        failure_reason = '';
        solver_status = 'completed';
    catch exception
        om = []; ff = []; weights = []; errvec = []; poles = [];
        status = 'failed';
        failure_reason = exception.identifier;
        solver_status = exception.message;
    end
    elapsed_seconds = toc(started);
    save(output_mat, 'status', 'projection_id', 'poles', 'om', 'ff', ...
        'weights', 'errvec', 'elapsed_seconds', 'solver_status', 'failure_reason');
    % 使用 jsonencode 写出同字段；失败时仍必须写文件。
end
```

wrapper 只能调用 `stab_AAA`；不得调用普通 AAA、pole flipping 或 Native 极点作为 fallback。

- [ ] **Step 4：实现 Python runner command 与 parser**

```python
@dataclass(frozen=True)
class StabAAAResult:
    projection_id: str
    status: str
    poles: np.ndarray
    support_points: np.ndarray
    error_history: np.ndarray
    elapsed_seconds: float
    solver_status: str
    failure_reason: str | None

`build_matlab_runner_command` 接受 MATLAB 路径、wrapper 路径、输入输出路径、外部仓库路径和 stabAAA 参数并返回无 shell 拼接的参数列表；`parse_stabaaa_result(path: Path) -> StabAAAResult` 严格校验上述 JSON schema。
```

- [ ] **Step 5：增加 preflight**

preflight 校验 `stabaaa_root/Source/stab_AAA.m`、MATLAB 可执行文件、外部 git commit SHA 和仓库示例路径。缺 LICENSE 记录为 `license_missing`，由 `--allow-unlicensed-research-run` 显式允许隔离研究运行；缺少该开关时退出，不启动 MATLAB。

- [ ] **Step 6：运行 runner 契约测试**

运行：`python -m pytest tests/test_sparam_stabaaa_validation.py -q -k "runner or preflight"`

预期：PASS；测试使用 fake JSON 和 monkeypatched subprocess，不要求本机安装 MATLAB。

- [ ] **Step 7：提交**

```powershell
git add scripts/matlab_stabaaa_projection_runner.m scripts/sparam_stabaaa_validation.py tests/test_sparam_stabaaa_validation.py
git commit -m "test(sparam): add isolated stabAAA runner contract"
```

### Task 3：聚类候选并精确选择固定阶数共享极点

**文件：**
- 新建：`scripts/sparam_stabaaa_poles.py`
- 新建：`tests/test_sparam_stabaaa_poles.py`

**接口：**
- 消费：多个 `StabAAAResult` 与投影 metadata。
- 产出：`PoleCandidate`、`PoleCluster`、`cluster_candidates`、`select_fixed_order`。
- 阶数约定：实极点成本 1，正虚部复极点代表一个共轭对且成本 2。

- [ ] **Step 1：写稳定性、共轭和重复候选测试**

```python
def test_normalize_candidates_rejects_rhp_and_uses_positive_imaginary_representative():
    poles = np.array([-1+0j, -2+3j, -2-3j, 1+4j, np.nan+0j])
    accepted, rejected = poles_mod.normalize_candidates(poles, projection_id="p0")
    assert [item.pole for item in accepted] == [-1+0j, -2+3j]
    assert {item.reason for item in rejected} == {"unstable", "non_finite"}
```

- [ ] **Step 2：写精确 order、频带覆盖和禁止 oracle 泄漏测试**

```python
def test_select_fixed_order_counts_pairs_as_two_and_does_not_accept_oracle_poles():
    clusters = make_clusters(real=2, complex_pairs=4)
    selected = poles_mod.select_fixed_order(
        clusters, target_order=8, frequency_band_edges_hz=(1e6, 1e8, 1e9, 3e9)
    )
    assert poles_mod.effective_order(selected) == 8
    assert "idem" not in inspect.signature(poles_mod.select_fixed_order).parameters
```

- [ ] **Step 3：运行测试确认失败**

运行：`python -m pytest tests/test_sparam_stabaaa_poles.py -q`

预期：FAIL，模块不存在。

- [ ] **Step 4：实现候选规范化与距离**

```python
def normalized_pole_distance(left: complex, right: complex) -> float:
    scale = max(abs(left), abs(right), 1.0)
    return float(abs(left - right) / scale)

def normalize_candidates(
    poles: np.ndarray, *, projection_id: str, real_axis_tolerance: float = 1e-10
) -> tuple[list[PoleCandidate], list[RejectedPole]]:
    """Normalize stable poles and return accepted candidates plus explicit rejections."""
```

右半平面极点必须拒绝；不得 flip。负虚部候选映射到正虚部代表；同一投影内共轭重复只计一次支持。

- [ ] **Step 5：实现确定性聚类与评分**

```python
@dataclass(frozen=True)
class PoleCluster:
    cluster_id: str
    center: complex
    projection_ids: tuple[str, ...]
    projection_kinds: tuple[str, ...]
    support_count: int
    scalar_error_improvement: float
    score: float

`cluster_candidates(candidates, *, relative_radius: float) -> list[PoleCluster]` 先按确定性 pole key 排序，再做 single-linkage 半径聚类；cluster center 使用支持投影数加权的复数均值，并按固定公式计算 `score`。
```

排序 tie-break 固定为 `(-score, abs(imag(center)), abs(real(center)), cluster_id)`，确保跨平台结果稳定。

- [ ] **Step 6：实现固定阶数选择与失败状态**

`select_fixed_order` 先满足对数频带覆盖，再按分数填充；无法精确组成目标阶数时返回 `OrderSelection(status="order_unavailable")`，不得补 Native/IdEM 极点。

- [ ] **Step 7：运行测试**

运行：`python -m pytest tests/test_sparam_stabaaa_poles.py -q`

预期：PASS。

- [ ] **Step 8：提交**

```powershell
git add scripts/sparam_stabaaa_poles.py tests/test_sparam_stabaaa_poles.py
git commit -m "test(sparam): select fixed-order stabAAA poles"
```

### Task 4：接入现有 residue LS 与 enforcement attribution

**文件：**
- 修改：`scripts/sparam_stabaaa_validation.py`
- 修改：`tests/test_sparam_stabaaa_validation.py`

**接口：**
- 复用：`load_raw_touchstone`、`fit_fixed_pole_residues`、`measure_model`、`enforce_promoted_passivity`、`effective_order`。
- 产出：`attribution/<method>/<order>/summary.json`，方法为 `stabaaa_projection`、`native`、可选 `idem`。

- [ ] **Step 1：写同阶 attribution 失败测试**

```python
def test_run_fixed_order_attribution_uses_same_raw_grid_and_existing_ls(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(validation, "fit_fixed_pole_residues", lambda raw, poles, **kw: calls.append((poles, kw)) or fake_model())
    monkeypatch.setattr(validation, "measure_model", fake_measure)
    monkeypatch.setattr(validation, "enforce_promoted_passivity", lambda model, raw: model)
    result = validation.run_fixed_order_attribution(
        raw=fake_raw(), method="stabaaa_projection", target_order=10,
        poles=order10_poles(), output_dir=tmp_path,
    )
    assert calls[0][1]["fit_max_frequency_points"] is None
    assert calls[0][1]["parameter_type"] == "s"
    assert result["effective_order"] == 10
```

- [ ] **Step 2：写 provenance 和 IdEM 泄漏保护测试**

输入 hash 不匹配时，`idem` case 必须标记 `provenance_mismatch` 并跳过；`stabaaa_projection` 的 `pole_clusters.json` 和 `orders/*/poles.json` 不得包含 IdEM 派生字段。

- [ ] **Step 3：运行测试确认失败**

运行：`python -m pytest tests/test_sparam_stabaaa_validation.py -q -k attribution`

预期：FAIL，attribution 接口不存在。

- [ ] **Step 4：实现单方法单阶 attribution**

```python
def run_fixed_order_attribution(
    *, raw: RawTouchstone, method: str, target_order: int,
    poles: np.ndarray, output_dir: Path,
) -> dict[str, Any]:
    pre_model = fit_fixed_pole_residues(
        raw, poles, parameter_type="s", fit_max_frequency_points=None,
        rcond=None, enforce_dc=False,
    )
    pre = measure_model(pre_model, raw)
    post_model = enforce_promoted_passivity(pre_model, raw)
    post = measure_model(post_model, raw)
    return build_attribution_summary(method, target_order, pre_model, post_model, pre, post)
```

summary 同时记录 LS `rank`、`condition_number`、residue Frobenius norm、最大 residue、pre/post RMS、pre/post sigma、enforcement 时间和内存诊断。

- [ ] **Step 5：实现 Native/IdEM 公平对照装载**

Native 必须来自同一输入、同一目标阶数的 canonical model 或本次固定阶数运行；IdEM 只在 artifact 的 input SHA-256 和 effective order 都匹配时纳入 `same_order_comparison`。不同阶 IdEM 只写入 `product_baseline`。

- [ ] **Step 6：运行 attribution 测试和既有回归**

运行：

```powershell
python -m pytest tests/test_sparam_stabaaa_validation.py -q -k attribution
python -m pytest tests/test_sparam_passivity_source_attribution.py tests/test_sparam_full_grid_pole_baseline.py -q
```

预期：全部 PASS。

- [ ] **Step 7：提交**

```powershell
git add scripts/sparam_stabaaa_validation.py tests/test_sparam_stabaaa_validation.py
git commit -m "test(sparam): compare stabAAA poles through attribution"
```

### Task 5：完成阶段编排、决策和中文报告

**文件：**
- 修改：`scripts/sparam_stabaaa_validation.py`
- 修改：`tests/test_sparam_stabaaa_validation.py`

**接口：**
- CLI 子命令：`preflight`、`prepare`、`run-projections`、`select-poles`、`attribute`、`report`、`run-all`。
- 总产物：`manifest.json`、`summary.json`、`report.md`。

- [ ] **Step 1：写 GO/PARTIAL/NO-GO 决策表测试**

```python
@pytest.mark.parametrize((metrics, expected), [
    (passing_test16_and_s19(), "GO"),
    (quality_passes_but_time_is_slow(), "PARTIAL"),
    (test16_only_improves(), "PARTIAL"),
    (fixed_order_does_not_improve(), "NO-GO"),
])
def test_decide_validation(metrics, expected):
    assert validation.decide_validation(metrics)["status"] == expected
```

- [ ] **Step 2：写 resume 和失败 artifact 测试**

完成阶段只有在输入 hash、配置指纹和所需文件都匹配时复用；MATLAB 中途失败也必须写 `manifest.json`、阶段状态和 `summary.json`。

- [ ] **Step 3：运行测试确认失败**

运行：`python -m pytest tests/test_sparam_stabaaa_validation.py -q -k "decision or resume or report"`

预期：FAIL。

- [ ] **Step 4：实现 manifest 与阶段状态机**

```python
STAGES = ("preflight", "prepare", "run_projections", "select_poles", "attribute", "report")

`config_fingerprint` 对排序后的 canonical JSON 计算 SHA-256；`can_resume_stage` 同时校验指纹、阶段完成状态和 required paths；`record_stage` 通过临时文件加 `Path.replace` 原子更新 manifest。
```

- [ ] **Step 5：实现严格验收决策**

`decide_validation` 逐条输出 spec 中五项 GO 条件的 observed、threshold、passed 和 evidence path。时间超过 IdEM 5 倍时状态必须是 `PARTIAL`，标签为 `quality_only`，不能输出“达到时间效率”。

- [ ] **Step 6：实现 Markdown 报告器**

报告从 `summary.json` 读取并包含：环境/许可、投影成功率、固定阶数表、2 GHz 诊断、LS 条件、pre/post passivity、时间内存、随机种子复现性、验收逐条证据和最终决策。

- [ ] **Step 7：实现 CLI**

```powershell
python scripts/sparam_stabaaa_validation.py run-all `
  --case-config scripts/sparam_stabaaa_cases.json `
  --stabaaa-root C:\path\to\stabAAA `
  --matlab matlab `
  --orders 6 8 10 13 `
  --seeds 17 29 43 71 `
  --output-root runs-sparam/stabaaa-shared-pole-validation
```

CLI 默认不允许无 LICENSE 外部仓库；研究者确认组织政策允许后才显式添加 `--allow-unlicensed-research-run`。

- [ ] **Step 8：运行完整单元测试**

运行：

```powershell
python -m pytest tests/test_sparam_stabaaa_projection.py tests/test_sparam_stabaaa_poles.py tests/test_sparam_stabaaa_validation.py -q
python -m pytest tests/test_sparam_passivity_source_attribution.py tests/test_sparam_full_grid_pole_baseline.py -q
```

预期：全部 PASS。

- [ ] **Step 9：提交**

```powershell
git add scripts/sparam_stabaaa_validation.py tests/test_sparam_stabaaa_validation.py
git commit -m "test(sparam): orchestrate stabAAA validation spike"
```

### Task 6：执行外部示例与 Test16 单 case 门

**文件：**
- 新建：`scripts/sparam_stabaaa_cases.json`
- 生成但不提交：`runs-sparam/stabaaa-shared-pole-validation/test16/**`

**接口：**
- case config 保存输入路径、SHA-256、Native artifact、IdEM artifact 和目标频带诊断范围。
- 此任务需要 MATLAB、YALMIP、MOSEK 与组织对无 LICENSE 代码运行的明确允许。

- [ ] **Step 1：记录外部环境与固定 commit**

运行 `preflight`。预期 `manifest.json` 包含 MATLAB/YALMIP/MOSEK 版本、stabAAA commit、LICENSE 状态和输入 hash；任何缺失均停止，不伪造成功。

- [ ] **Step 2：运行 Absorber 与 ISS 示例**

使用外部仓库原命令运行两个示例，保存 stdout/stderr、退出状态、误差轨迹和时间。预期两个示例均完成；否则决策为 `NO-GO: upstream_example_failed`。

- [ ] **Step 3：只生成 Test16 投影并人工审计 manifest**

运行 `prepare --case test16`。核对端口数、频点数、输入 SHA-256、投影数量、退化投影和 seed 列表，确认无 IdEM 派生输入。

- [ ] **Step 4：运行 Test16 stabAAA 与固定阶数选择**

运行 `run-projections`、`select-poles`。预期成功投影达到配置最小数，且 `orders/6|8|10|13/poles.json` 的 effective order 精确匹配目录名。

- [ ] **Step 5：运行 Test16 attribution 与报告**

运行 `attribute --case test16` 和 `report`。检查 order-10 `final RMS <= 0.001`、passivity、IdEM 1.25 倍门和随机种子重复率；保存所有失败原因。

- [ ] **Step 6：提交 case 配置，不提交大型运行产物**

```powershell
git add scripts/sparam_stabaaa_cases.json
git commit -m "test(sparam): define stabAAA validation cases"
```

### Task 7：执行 s19 交叉验证并形成最终决策

**文件：**
- 生成但不提交：`runs-sparam/stabaaa-shared-pole-validation/s19/**`
- 新建：`docs/sparam-stabaaa-shared-pole-validation-results.md`

- [ ] **Step 1：运行 s19 全阶段**

使用与 Test16 相同的 orders、seed 列表、聚类半径和评分权重执行 `run-all --case s19`。不得根据 Test16 结果重新调参后只重跑 s19。

- [ ] **Step 2：生成双 case 总结**

运行 `report --cases test16 s19`，产生总 `summary.json` 和 `report.md`。预期每条 GO 条件都有 observed、threshold、passed 与 artifact 路径。

- [ ] **Step 3：审计公平性**

确认所有同阶比较的 effective order 相同；IdEM 不同阶数只出现在 product baseline；候选选择输入中没有 IdEM 字段；所有报告数值能回溯到 per-case summary。

- [ ] **Step 4：固化中文结果报告**

由机器 `report.md` 生成仓库报告 `docs/sparam-stabaaa-shared-pole-validation-results.md`，只补充实验背景和结论，不手工改动数值表。

- [ ] **Step 5：按结果停止或另开 spec**

- `GO`：另开生产化 spec，讨论许可替代、依赖去除、Python/Native 实现和性能预算。
- `PARTIAL`：只提出一个有明确假设的新验证 spike，不扩展到五个算法。
- `NO-GO`：结束 stabAAA 路线，按原 scope 再评估 Loewner 或 RKFIT。

- [ ] **Step 6：运行最终回归并提交报告**

运行：`python -m pytest -q`

预期：全部既有测试与新增测试 PASS；已有明确 skip/xfail 可保留。

```powershell
git add docs/sparam-stabaaa-shared-pole-validation-results.md
git commit -m "docs: report stabAAA shared-pole validation"
```

## 自检结果

- spec 的投影、原版 runner、候选处理、固定阶数、attribution、指标、决策、artifact、失败路径和真实双 case 验证均有对应任务。
- 生产集成、MIMO stabAAA、自研 smiAAA、其他非 VF 算法未混入本计划。
- `ProjectionRecord`、`StabAAAResult`、`PoleCluster` 和 attribution summary 的生产/消费关系在任务接口中保持一致。
- 计划没有依赖未定义的 IdEM oracle 参与选择；IdEM 只在 Task 4 的对照与事后诊断阶段出现。
