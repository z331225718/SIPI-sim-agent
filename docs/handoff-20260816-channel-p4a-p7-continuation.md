# Handoff：P4A/ P7 交接（SIPI-sim-agent）

## 目标背景
- 本次交接从当前工作树状态继续，当前已完成较大部分 P2/P3A/P4A/P7 的基础工程，近期核心在于：  
  1）继续推进 P4A IBIS 守卫型批量 quasi-static 路线的长期收尾；  
  2）处理 P7 的 release 与候选链门控，尤其 P7-08 / P7-09 前置阻断。  
- 工作区当前存在未提交改动，不建议回滚；请仅基于当前状态继续。

## 当前提交面（最近）
- `b70f8c6`：`test: rebind channel evidence for IBIS batch route`
- `c7aebc7`：`feat: add sealed IBIS quasi-static batch route`
- `369a6c0`：`test: rebind channel evidence for sealed IBIS route`
- `463b5bb`：`feat: add sealed IBIS quasi-static route`
- `8d25145`：`test: rebind matched S2P evidence for current candidate`
- `fa79434`：`test: rebind fixed TRAN evidence for current candidate`
- `538f5dd`：`feat: add bounded one-node RC PWL route`
- `35ffb7b`：`feat: add bounded one-node RC PWL core`

## 当前工作树（未提交，本次不能直接清理）
- `M crates/sipi-channel/src/lib.rs`
- `M crates/sipi-channel/src/p3c_fixed_pole_rational_fit_v1.rs`
- `M crates/sipi-channel/src/p3c_real_constrained_fixed_pole_fit_v1.rs`
- `M crates/sipi-ieee-com-sparam/src/s21_to_raw_periodic_v1.rs`
- `M crates/sipi-p3c/src/lib.rs`
- `M crates/sipi-p3c/tests/p3c_sealed_s4p_external_fit_runner.rs`
- `M crates/sipi-p3c/tests/p3c_sealed_s4p_external_impulse_diagnostic_runner.rs`
- `M crates/sipi-p3c/tests/p3c_sealed_s4p_external_raw_periodic_runner.rs`
- `M crates/sipi-p3c/tests/p3c_sealed_s4p_external_runner.rs`
- `M uv.lock`（请勿触碰，用户文件，通常由系统环境导致）

## 已完成关键事实（建议按以下顺序接续）
1. P4A 已有可复用入口：  
   - `sipi ibis quasi-static-evaluate-artifact`（单点）  
   - `sipi ibis quasi-static-evaluate-artifact-batch`（批量）  
   - 均为 strict artifact-only、caller-owned、非 transient、非 profile/parity 结果路线。  
2. P4A evidence/release 绑定完成：  
   - `docs/baselines/p4a-ibis-conformance-matrix.v1.yaml` / P4A 相关审计  
   - `tools/verify_p4a...` 对应 verifier 与 route binding 已落地（以 `selected-waveform` 类似路径进行入口约束）  
3. P3A 当前候选链已重绑到当前 product candidate 并保留历史：  
   - 最新 channel matched-S2P external evidence rebind 已作为 current 保持。  
   - 旧 evidence 保持 historical + source drift，不能回填为 current。  
4. P7 方面：
   - P7-05 系列 gate-consistency 修复完成到较高覆盖（unavailable/accepted-authority 等）  
   - P7-06 进入 current chain 可复现预检分支：  
     - `P7-06c`（layout 静态预检）  
     - `P7-06d`（PE 识别）  
     - `P7-06e`（bcryptprimitives/ProcessPrng authority preflight）  
     - `P7-06f`（layout policy v2）  
     - `P7-06g`（当前候选观测链：repro twin + composition + install + 性能，仍 blocked）  
   - `docs/baselines/audits/2026-08-15-p7-current-candidate-chain-observation.md` 为关键依据。  
5. P7-07 系列：  
   - `P7-07a` / `P7-07b` / `P7-07c` / `P7-07d` 已完成；均为 non-conclusive（不提升 release）。  
   - 重点结论：不应创建 release candidate / 不应把观察当 approval。  

## 当前阻塞（下一个 agent 必看）
- `P7-08`：`blocked_no_path_scoped_replacement_and_retirement_approval` 仍未解除。  
  - 当前 Rust CLI 仍是窄固定能力路径，Python adapter / engine / fixture / M0-M5 migration 仍待逐路径替换映射与退役审批。  
- `P7-09a` 已完成，但后续 `P7-09` 与正式 release 相关收口仍待。  
- P7/发布仍被 `fresh-machine`、`license/notice`、多域/跨域 certification、required profile acceptance 阻塞。  
- 产品层仍有多个 P3C 分支历史观测与来源漂移痕迹（已留档），不应重写为当前可接受状态。  

## 建议接续动作（优先级）
1. 先固定证据链一致性：  
   - 重核 `docs/baselines/release-capability-publication.v1.yaml` 与 `tools/verify_release_capability_publication.py` 是否与现有行语义一致。  
2. 接着推进 P7-08 的 owner 批准项：  
   - 路径替换映射策略、同批 drift gate 清理、release 退役审批策略。  
3. P7-06 的 composition/archive/install/evaluation remain pending 依赖仍在：  
   - 不重复做已经通过过的 static observation（PE/metadata/metadata normalization），避免重复绕过。  
4. 若继续做 P3C，请先确认已冻结的指标/误差和 source policy；当前工作树有大量相关变更，建议与 `git diff` 逐块确认后再执行大面积改动。  

## 已知风险与注意事项
- 不要把 historical evidence（v1/v2/v3/v4 等）直接当成 current candidate 结论。  
- 不要把 static/license metadata 观察提升成 legal/conclusion 或 release approval。  
- 任何新增路由/命令更改须显式绑定到 exact manifest/evidence 与 exact blocker/non-claim 语义。  
- `uv.lock` 当前 dirty，且 user 已要求保留；除非明确要求，不要改。  

## 便于接续的最小复核命令
- `git status --short`  
- `git log --oneline -n 12`  
- `python -B tools/verify_release_capability_publication.py`  
- `python -B tools/verify_p4a_ibis_conformance_matrix.py`  
- 相关验收审计按 `docs/baselines/audits/*.md` 逐个核验

## 当前转交说明
- 建议下一位 agent 只继续做“P7 release gate 收口 + P7-08”优先级最高；  
- 如需变更 P3C，请先同步当前该模块未提交文件列表并执行最小 diff 评审，再进入新切片。  
