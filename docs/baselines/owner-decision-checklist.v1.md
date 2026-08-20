# Owner 决策清单（待填写）

> 本文件把 `docs/baselines/owner-input-request.v1.yaml` 的机器绑定记录展开为人类可填写表单，并补充分类为 `semantics_not_implemented`、但实质上同样需要 owner 输入（profile / 外部资产 / 语义选择）的项。
>
> 填写方式：在每项「决策记录」小节直接改文档（把勾选框 `[ ]` 改为 `[x]` 并写下你的选择），或回复本文件编号 + 你的选择即可。
> 你把决定告诉我后，我会回填 owner-input-request 与 plan-remaining-items-ledger，并推进对应 gate。
>
> 约定：**不猜测、不静默 fallback**——未获得明确决策的事项保持 fail-closed。

---

## A. 严格 owner 决策项（7 项，来自 owner-input-request）

### A1. P1-04B — required profile 确认
- 现状：legacy-fixture boundary 门禁已建；需要你确认 required profile。
- 决策点：「确认 required profile（给出 profile 名 / 版本）」；「是否需要 legacy-fixture 比较？」
- 决策记录：外部的fixtures全局信任，不要阻塞

### A2. P3B-02 — Link profile equalizer 子集选择
- 现状：link-kernel singleton 门禁已建；equalizer 子集待选。
- 决策点：「选择 Link profile 的 equalizer 子集（CTLE / FFE 语义与顺序）」
- 决策记录：首先我们的算法得支持这两种，然后仿真时候由用户决定加哪个，并且ctle和ffe实现时要给出详细的配置和建议

### A3. P3B-04 — CDR-lock 语义
- 现状：delegated-policy agreement 已记录（2026-08-11 修订批准）；CDR lock 语义仍缺失。
- 决策点：「phase-acquisition 算法；lock / reset / cancel 规则」
- 决策记录：CDR一般的ibis-ami rxdll都会有，不需要重复定义。我们的代码可以支持一个比较常用的cdr（bangbang或者mm）或者不支持cdr，我建议目前先不用cdr，这一步写成遗留，不阻塞

### A4. P3B-05 — seed / noise / jitter 六项决策面
- 现状：request rejection 已强制（05a）；decision surface 已冻结（05b）。
- 决策点：「required profile；injection position；units / random-vs-timewarp 模型；seed replay；observables；tolerance」
- 决策记录：prbs9,seed：0b000000001，支持发送端注入，用时间

### A5. P3C-01 — 眼折叠 / bathtub 估计器与容差
- 现状：eye folding/bin 与 TIE reference 已由 v2 contract 冻结（01e）；接受 receiver stage。
- 决策点：「bathtub/BER 估计器与 tolerance 语义；accepted receiver stage」
- 决策记录：Q-factor，0.1dB容差

### A6. P4A-01 — required IBIS profile
- 现状：rx candidate inventory 门禁已建。
- 决策点：「IBIS 版本；keyword / model selector / corner / table family 清单」
- 决策记录：5.0 ，C:\Users\z3312\code\SIPI-sim-agent\fixtures\ibis\as4c512m16md4v-053bin.ibs

### A7. P7-08 — drift-gate 退役剩余门禁
- 现状：retirement approval 已记录（2026-08-16）；还差 required profile 接受、同批 drift-gate 移除、release/license/fresh-machine gates。
- 决策点：「接受 required profile；同意同批 drift-gate 移除；确认后续 release gates」
- 决策记录：确认退役下的一串门禁清单

---
## B. 外部资产 / oracle 决策项（4 项，来自 owner-input-request）

### B1. P4B-08 — ADS netlist 端口映射
- 现状：S4P 结构已观察（08a）；矩阵决策面已冻结（08b）；port 映射需 netlist。
- 决策点：「提供/授权 ADS netlist 端口映射（S4P 端口顺序 / victim-aggressor 列），解锁 S4P 派生 AMI_Init 矩阵」
- 决策记录：授权 ADS netlist

### B2. P4B-09 — authorized profile 运行 sipi ami run
- 现状：需要 authorized profile；无静默 fallback。
- 决策点：「提供授权 profile」
- 决策记录：C:\Users\z3312\code\ADS\MyWorkspace_wrk\ibis_ami\ 下都是我认可的，我授权

### B3. P5-02 — canonical R480 parameter JSON 的外部参考
- 现状：02e-02j 已交付（canonical JSON v2 + warning observation + scalar default resolution）。
- 决策点：「授权 MATLAB oracle / agent-com 生成 canonical R480 reference（权威参考）」，用于完成产品 warning contract 与向量/矩阵默认布局。
- 决策记录：授权启用 MATLAB oracle 产出权威 golden 文件

### B4. P5-06 — MATLAB oracle 输出用于 required COM 示例比较
- 现状：06a-06c 已交付（首次 run + metric surface + normalized-input surface）。
- 决策点：「授权 MATLAB oracle 输出（26.56 GHz / 120g C2M TP1a）用于 required COM 示例比较（compare matrix）」
- 决策记录：授权启用比较

---
## C. 分类为 semantics_not_implemented、但实质需要你输入（供参考，非 owner-input-request 严格集合）

### C1. P4A-02 — IBIS 行为 scope
- 决策点：「行为 spec 尚未形成；DLL identity 阻塞黑盒——需要提供 DLL 身份 / 授权行为观察」
- 决策记录：提供，在我之前授权的外部profile里找

### C2. P4A-03 — full typed AST
- 决策点：「需要 profile 的 keyword 规则以完成 full typed AST」
- 决策记录：提供，在我之前授权的外部profile里找

### C3. P3C-02 — bathtub 估计器/容差（决策面已冻结）
- 决策点：「bathtub 估计器与 tolerance 语义（与 A5 相关）」
- 决策记录：

### C4. P3C-03 — metric profile
- 决策点：「profile-compare 用 metric profile」
- 决策记录：COM_dB、ICN_mV、ERL 三项；相对容差 < 1% (Tolerance < 1%)

### C5. P2-06 — 泛化 parsed-circuit / measurements
- 决策点：「是否提供 netlist 面以为 P2-06 提供支撑」
- 决策记录：提供，在我之前授权的外部profile里找


---
## D. 我可主动推进（无需你决策）的下一切片

以下不依赖 owner 决策或外部资产，可继续沿 clean-room + oracle crosscheck 模式实现：
- **P5-02 向量/矩阵默认布局**：`[1 3 2 4]`、`[50,50]`、`[0 0]`、string-matrix `pkg_Z_c`（自包含，可对 _resolve_default oracle 跨检）。
- **P5-08 `sipi com run`**：可按更小切片谨慎接入（此前的尝试因 conformance admission 过大整体回退）。