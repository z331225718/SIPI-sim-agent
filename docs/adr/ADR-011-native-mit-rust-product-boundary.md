# ADR-011：原生 MIT Rust 产品边界

- 状态：Accepted
- 日期：2026-08-09
- 决策者：项目用户/owner
- 影响范围：产品架构、许可、源码迁移、运行时、CLI、发布与认证

## 背景

v0.1 以降低迁移风险为首要目标：平台先通过 Python 控制面、process adapter、锁定 bundle 和旧引擎获得统一入口，再逐步迁入源码。该路线已经产出有价值的契约、工件、fail-closed、跨域 DTO 和数值比较证据。

产品终态现已进一步明确：项目要成为原生 SIPI 仿真平台，集合 TRAN、Channel、IBIS-AMI 和 COM；非 MIT 第一方实现要 clean-room 重做；产品统一 Rust；既有项目例子的准确性要保持；最终由一个易于用户和 AI 使用的 CLI 暴露。

如果继续把 Python adapter、旧可执行文件和跨仓历史迁入当作终态，产品会同时违反 Rust-only 目标和可审计 MIT 边界。尤其是把非 MIT/BSD 派生历史 filter 进最终 monorepo，不能因为路径或包元数据变化而变成 MIT 实现。

## 决策

1. 最终产品是一个 Rust workspace，包含 contracts、artifacts、runtime、pipeline、TRAN、Channel、IBIS、AMI、COM 和 CLI。
2. `sipi` 是唯一公开 CLI。允许由同一 workspace 构建的私有隔离 worker，但它们不形成第二套用户接口。
3. 第一方可发布源码统一采用 MIT。MIT-compatible 第三方依赖保留自己的许可证、NOTICE 和 SBOM；“MIT 产品”不被解释为所有第三方字节都采用 MIT。
4. 已确认 MIT 的旧源码可以直接复用或移植，但需逐文件来源和依赖审计。
5. 非 MIT 第一方实现不迁入产品历史。它们只可在隔离观察侧作为黑盒 oracle；实现侧依据公开标准和独立行为规格 clean-room 重做。
6. 供应商 DLL、IBIS/AMI 模型、私有 corpus 和不可再分发 golden 默认由用户外部提供，不进入 Git 或发行包。
7. 准确性以 versioned acceptance profile 认证：固定来源、输入、stage、容差、平台、provenance 和 non-claims。
8. Python runtime/adapters、旧 engine bundle、PyBERT CI/nightly 和历史迁入工具降级为迁移/oracle 设施，不再是产品 completion path。
9. 不执行 PyBERT 非 MIT/BSD 历史向最终 MIT 产品仓的 filter-repo 迁入。需要的历史留在原仓或独立 evidence/quarantine repo。
10. Windows x86_64 为首个认证平台；Linux/macOS 继续暂缓，除非专门门禁通过。

## 结果

### 正面结果

- 发布边界、实现语言和许可目标一致。
- 用户只面对一个稳定入口，AI 可依赖 schema/capabilities/errors，而不是猜测旧 CLI。
- 旧项目的准确性证据仍可复用，但不会把旧运行时固化成永久依赖。
- 每个领域可独立演进和认证，同时通过 typed artifact 组成 pipeline。

### 成本与约束

- Channel/PyAMI 等非 MIT/BSD 来源不能直接翻译，重做成本明显增加。
- strict clean-room 需要材料和角色隔离；已接触受限源码的实现者不能自行证明隔离。
- 旧 adapter 和 nightly 仍需保留一段时间产生 oracle 证据，但不得进入 release。
- 单一 fixture 或单一平台的成功不能外推，能力矩阵会在较长时间内保持窄范围。

## 对既有 ADR 的影响

- ADR-001、ADR-002、ADR-006、ADR-008 继续解释 v0.1 迁移阶段为何使用多包、旧契约和进程隔离。
- 本 ADR 覆盖这些 ADR 对“最终产品形态”的推论：process adapter、多 wheel 和旧引擎 fallback 不再是终态。
- ADR-003、ADR-004、ADR-005、ADR-009、ADR-010 中关于显式语义、领域边界、工件和平台认证的原则继续有效。

## 非宣称

- 本决策不是法律意见，也不自动解决任何具体第三方资产的授权。
- 用户批准推进不替代逐资产许可、NOTICE、SBOM 和分发范围核验。
- 采用 Rust 或重新实现不自动构成 clean-room；只有材料、角色和审计链满足要求才可声明。
- 本决策不表示 TRAN、Channel、IBIS-AMI、COM 或跨平台能力已经认证。
