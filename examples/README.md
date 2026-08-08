# SIPI M3 示例项目

这些示例展示 Platform MVP 的项目形态与 DAG 绑定机制，全部可通过 `sipi validate` 只读验证。执行状态分两类：

| 示例 | 路径 | 分析 | 执行状态 |
| --- | --- | --- | --- |
| Circuit RFM deck | `circuit/rfm-deck` | `circuit.solve.v1`（agent-spice-process） | validate 可用；真实执行见 `tests/runtime/test_real_engine_vertical.py`（真实 `agent-spice-sim` rfm-response 端到端，需本地构建引擎） |
| Channel RFM→Link | `channel/rfm-to-link` | `circuit.solve.v1` → `link.simulate.v1`（bound input） | stub 纵向 smoke 可用（`tests/runtime/test_vertical_smoke.py`）；真实双引擎执行见 `tests/runtime/test_two_engine_vertical.py`（真实 agent-spice + 真实 pybert，需本地构建 wheel/引擎） |
| COM r480 | `com/r480` | `com.r480.run.v1`（agent-com-process） | validate 可用；真实执行待 oracle/license 分类 |

## 运行

```powershell
.venv\Scripts\python.exe -B -m sipi_cli validate --root examples\channel\rfm-to-link --format json
```

## 说明

- `bundles/` 内是 stub 引擎（与测试套件同源契约），用于冻结项目/engine.lock 的机器可复现结构；真实引擎执行已解锁（M2 deferred 触发条件全部满足：managed lock 就绪 + parity gate approved + 许可分类），验收测试经 `tests/runtime/test_real_engine_vertical.py` 与 `tests/runtime/test_two_engine_vertical.py` 运行真实引擎（`skipUnless` 本地已构建）。
- `channel/rfm-to-link` 演示 M3-08 的绑定语义：上游 `circuit.solve.v1` 导出 `rfm-response` 角色，下游 `link.simulate.v1` 通过 `from_analysis + artifact_role + expected_schema` 消费。
