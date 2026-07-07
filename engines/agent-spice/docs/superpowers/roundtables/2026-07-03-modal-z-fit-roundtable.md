# Modal Z-Fit Roundtable

日期：2026-07-03

## 议题

Agent-Spice 30-port PDN 拟合需要寻找算法突破，而不是继续扫 `model_order_max`。本轮讨论围绕 `docs/superpowers/specs/2026-07-03-modal-z-fit-design.md` 收敛实施 plan。

## 参与情况

- 本地 Architecture reviewer subagent：启动失败，原因是当前 Codex usage limit。
- 本地 Implementation reviewer subagent：启动失败，原因是当前 Codex usage limit。
- DeepSeek external reviewer：`DEEPSEEK_API_KEY` 存在，脚本执行 exit code 0，但 stdout 为空；不作为有效观点来源。
- 主 agent 本地审查：基于当前代码、spec、scikit-rf 实现和已跑 30-port 结果完成收敛。

## 圆桌结论

- 决策：不继续盲扫 60/80/100 阶；先实现一个隔离的 reduced-basis Z-domain rational fitting prototype。
- 共识：当前元素级 VF 的问题不是单纯计算速度，而是目标函数和数据表述不匹配 PDN 交付目标。PDN 应以 Z-domain log-magnitude error 和主导端口模态为核心指标。
- 分歧：原 spec 的 “`Z_fit = Q @ diag(lambda_fit) @ Qᴴ`” 过窄，可能丢掉 reduced modal basis 内的耦合项。
- 必须修改：MVP 改成 `Zr(f) = Qᴴ @ Z(f) @ Q`，拟合 `k^2` 个 reduced matrix traces，再重建 `Z_fit = Q @ Zr_fit @ Qᴴ`。
- 延后事项：passivity enforcement、SPICE synthesis、SROPEE/Block SAPOR 隔离实验、Loewner MIMO prototype。
- 验收标准：生成 `fit-modal-z` JSON/HTML 报告；用 30-port 数据与元素级 VF 20/40 阶结果对比；如果没有显著改善，报告明确建议停止方案 A。

## 各角色要点

### Architecture

- 新增算法必须隔离在 `agent_spice.sparam.modal` 和 `agent_spice.sparam.modal_report`，不能污染当前可交付的 `fit-sparam` SPICE 导出路径。
- reduced-basis full matrix 比 diagonal-only modal trace 更稳健；它仍然显著降低响应数量，例如 30-port full matrix 是 900 条响应，`mode_count=8` 只需要 64 条 reduced traces。
- fixed stable poles 的最小二乘原型比直接再调用 scikit-rf scalar VF 更适合第一轮验证，因为它避免 pole relocation 变量干扰。

### Implementation

- 采用 TDD：先测 `z_log_magnitude_rms_error()`、basis construction、projection/reconstruction、fixed-pole scalar fit、CLI report。
- CLI 新增 `fit-modal-z`，只写 report/html，不写 SPICE。
- 30-port 默认建议：`--decomposition svd --mode-count 8 --scalar-fit-order 24 --frequency-sample-count 256`。`svd` 对非 Hermitian 或强频变 Z 更稳。

### Safety/Risk

- fixed basis 可能无法覆盖强频变模态；必须报告 `basis_projection_z_log_magnitude_rms_error`，区分 basis 失败和 rational fit 失败。
- fixed-pole LS 可能病态；实现必须加入列归一化和 least-squares fallback。
- 不保证 passive；报告必须清楚标注 prototype/report-only。

### Product/Spec

- 优化报告必须回答一个业务问题：是否值得继续 modal-Z 路线。
- 成功不是“新增一个命令”，而是证明 30-port 相比元素级 VF 20/40 阶有无显著改善。
- 如果结果不显著，下一步应转向 Loewner 或 Block SAPOR/MOR，而不是继续扫阶。
