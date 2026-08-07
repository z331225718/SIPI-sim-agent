# SIPI M3 用户迁移指南

本文把三个旧引擎的常用命令映射到平台 `sipi` 命令。平台侧当前状态：控制面、执行驱动、缓存、进程树与恢复均已实现并经独立审计；真实引擎 bundle 待 M2 deferred 触发条件（managed lock 就绪 + parity gate approved + agent-spice/agent-com 许可分类）后替换示例 stub。

## 命令映射

| 旧入口 | 旧命令 | `sipi` 映射 |
| --- | --- | --- |
| PyBERT | `pybert sim <config>` | `sipi run`（project analysis `link.simulate.v1`，strict `pybert-python`） |
| PyBERT | `pybert sim-auto` | `sipi run`（analysis `backend_selection.mode=auto`） |
| PyBERT | `pybert sim-compare` | `sipi run`（`mode=compare`，reference/candidate 两角色）+ `sipi report` |
| Agent-Spice | `run-hspice` / `run-rfm` | `sipi run`（analysis `circuit.solve.v1`，strict `agent-spice-process`） |
| Agent-COM | `com8023 run` | `sipi run`（analysis `com.r480.run.v1`，strict `agent-com-process`） |

## 使用示例

```powershell
# 只读校验项目（解析、路径哈希、DAG、选择预检）
sipi validate --root examples\channel\rfm-to-link --format json

# 提交运行（默认连接持久 supervisor；--detach 立即返回 run_id）
sipi run --root examples\channel\rfm-to-link --detach

# 状态 / 取消 / 重试
sipi status --root examples\channel\rfm-to-link <run_id>
sipi cancel --root examples\channel\rfm-to-link <run_id>
sipi retry --root examples\channel\rfm-to-link <run_id>

# 统一报告（含 compare 判定）
sipi report --root examples\channel\rfm-to-link <run_id> --format json
```

## 当前状态与门禁

- 平台层（DAG、bound inputs、publish CAS、cache、cancel、进程树、reconcile、报告）已可运行；`examples/channel/rfm-to-link` 可用 stub 引擎做纵向 smoke。
- Circuit/COM 示例目前 validate-only；真实执行需要引擎 bundle 与对应 adapter 接线（M3-07b/08b）。
- 迁移不改变领域语义：平台不重写 golden、不 alias 领域 schema；`pybert sim-auto/sim-compare` 的平台等价物由 runtime 的 discriminated selection 表达，adapter 保持 strict-only。

## 迁移检查单

1. `sipi validate` 对目标项目返回 0。
2. `sipi run --detach` 返回 run_id 且 `sipi status` 最终为 succeeded。
3. compare 项目 `sipi report` 输出 matched/mismatch 与证据路径。
4. 旧入口（如 `pybert sim`）与 adapter 在同一 fixture 上结果等价（M2-05 引擎级，门禁后验收）。
5. 取消后无残留进程；重启后 reconcile 正确回收（`sipi status` 可见终态）。
