# ADR-006: 继承 PyBERT v1 与既有交接

状态：已接受。

继承 `pybert.simulation.v1`、Rust core、AMI host handoff 和 RFM consumer 等既有资产/边界。`RunEventV1`、`ArtifactRefV1` 与 `ChannelResponseV1` 保持不可变，平台只做显式映射。PyBERT 的 auto/compare 不得嵌入平台 auto/compare，adapter 始终 strict-only；最终迁入生产目标由 Agent-Spice 改为本仓。
