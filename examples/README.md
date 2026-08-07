# SIPI M3 示例项目

这些示例展示 Platform MVP 的项目形态与 DAG 绑定机制，全部可通过 `sipi validate` 只读验证。执行状态分两类：

| 示例 | 路径 | 分析 | 执行状态 |
| --- | --- | --- | --- |
| Circuit RFM deck | `circuit/rfm-deck` | `circuit.solve.v1`（agent-spice-process） | validate 可用；真实执行待 agent-spice license/third-party 分类 + managed lock |
| Channel RFM→Link | `channel/rfm-to-link` | `circuit.solve.v1` → `link.simulate.v1`（bound input） | pybert 节点可用 stub 执行；真实执行待 managed lock |
| COM r480 | `com/r480` | `com.r480.run.v1`（agent-com-process） | validate 可用；真实执行待 oracle/license 分类 |

## 运行

```powershell
.venv\Scripts\python.exe -B -m sipi_cli validate --root examples\channel\rfm-to-link --format json
```

## 说明

- `bundles/` 内是 stub 引擎（与测试套件同源契约），用于冻结项目/engine.lock 的机器可复现结构；真实引擎 bundle 在 M2 deferred 触发条件（managed lock 就绪 + parity gate approved）与 agent-spice/agent-com 许可分类完成后替换。
- `channel/rfm-to-link` 演示 M3-08 的绑定语义：上游 `circuit.solve.v1` 导出 `rfm-response` 角色，下游 `link.simulate.v1` 通过 `from_analysis + artifact_role + expected_schema` 消费。
