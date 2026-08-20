# Owner 决策项详解（逐项说明）

> 这是 `owner-decision-checklist.v1.md` 的背景说明。每一项按「这个功能是什么」「已经做了什么」「为什么需要你决策」「选项/影响」四块展开，方便你逐条看懂后再决定。
>
> 重要前提：这些项目都建立了**不猜测、不静默 fallback** 的纪律——没有你的明确选择，就用 `fail-closed`（即默认拒绝/不假装实现）。所以你的决策不是锦上添花，而是**解开卡点的钥匙**。

---

# 第一部分：owner 决策项（选什么语义）

---

## A1. P1-04B — 旧版 fixture（`sipi.*.v1`）要不要纳入比较

**这是什么**：仓库里有一批旧版本的 SIPI fixture 文件（工作流请求/执行这些）。它们只能在 git 工作树外查看，不能被产品 Rust 代码引用。

**已做到的**：P1-04Ba 已用机械门禁锁死边界——证明这批旧 fixture 从未混进产品代码，schema id 也没有出现在 Rust 源码里。

**为什么需要你决策**：这批旧 fixture 是否要和当前产品比较，取决于你说的「required profile」。如果你不需要它们参与比较，这个项目就到此为止。

**选项**：
- 确认 required profile（给出名字/版本）→ 我据此决定是否建比较工程；
- 「不用比较」→ 我直接把这个项目收尾（保持 oracle-only 边界即可）。


## A2. P3B-02 — Link（串行链路）均衡器用哪套

**这是什么**：做链路级仿真的核心算法——接收端怎么把被信道衰减的信号『捞回来』。常见手段是连续时间线性均衡（CTLE）和/或前馈均衡（FFE）。

**为什么需要你决策**：要仿真『指定的链路 profile』，必须先确定这个 profile 默认用哪些均衡器、按什么顺序。不同选择会改变仿真结果。

**选项**：CTLE 优先 / FFE 优先 / 两者都用 / 按你给的 profile 文档定。


## A3. P3B-04 — CDR（时钟数据恢复）的锁定规则

**这是什么**：接收端要从波形里恢复出时钟和数据。『CDR-lock』指接收机是否判断自己已经稳定锁定。当前实现遇到了**无法判定锁定/歧义**（`cdr_ambiguous`），在批准的契约下被阻塞。

**已做到的**：多次 external replay 和产品边界校验都通过了，但独立 evaluator 和产品接收机在双重 replay 上都 `fail-closed cdr_ambiguous`。

**为什么需要你决策**：只有你（owner）修订 phase-acquisition 语义——即采用哪种相位捕获算法、锁定/复位/取消的规则——之后才能重跑，而**禁止复用旧 Rust 接收机**。

**选项**：调整锁定判定（如固定捕获窗口 / 最小信号阈值 / 相位歧义处理策略）。需要你给出或认可一种算法规则。


## A4. P3B-05 — seed / noise / jitter（种子噪声抖动）六项语义

**这是什么**：链路仿真里注入的随机噪声/抖动。六项=required profile、注入位置、单位（随机模型还是时间扭曲模型）、seed 可重放、可观测输出、容差。

**已做到的**：05a 已对所有未支持的 stage 做了 `fail-closed` 拒绝；05b 已冻结决策面。

**为什么需要你决策**：seed 的「种子数/随机源」和抖动模型必须确定，否则仿真不可重放、不能验收。

**选项**：指定随机源与 seed 约定、注入位置（发送端/信道/接收端）、以及用哪种抖动统计模型。


## A5. P3C-01 / C3. P3C-02 — 眼图与 bathtub（浴缸曲线）估计器

**这是什么**：眼图是看信号质量的经典方法；bathtub 曲线估算误码率(BER)与时间裕量。

**已做到的**：眼图折叠/bin 和 TIE reference 已由 v2 契约冻结（01e）；bathtub 决策面已冻结（02d）。

**为什么需要你决策**：用**哪种 BER 估算器**（如 Q-factor / 尾部高斯拟合 / 蒙特卡洛）和**容差**（多少 dB 算通过）目前未定。

**选项**：选择一个估算器算法和一组容差阈值。


## A6. P4A-01 — required IBIS 示例的 profile 清单

**这是什么**：IBIS 是芯片 I/O 建模标准。A6 需要确定要支持哪一版标准、哪些关键字、模型选择器、corner 和 table。

**已做到的**：01a–01f 已经做了候选盘点、接收端拓扑边界、electrical/IBIS 发现、选定 P/N/REF 100Ω+1pF 差分 RC 核心甚至 CLI。这些都不选 required profile。

**为什么需要你决策**：现在卡在『required profile』这一步——即你要用哪一版 IBIS 和哪份示例。

**选项**：给出 IBIS 版本（如 7.x）和示例文件名；或授权某份官方 `.ibs`。


## A7. P7-08 — 退役 drift-gate 的收尾

**这是什么**：之前决定退役（retire）某批『环境漂移检查门』，改用路径范围化的替换方案。retirement approval 已记录。

**已做到的**：退役批准已记录（2026-08-16），替换 map/策略已建。

**为什么需要你决策**：还需你接受 required profile、同意同批 drift-gate 移除，并确认后续 release/license/fresh-machine 门。

**选项**：确认退役下的一串门禁清单。

---
# 第二部分：外部资产/oracle 决策项（提供或授权某种资源）
---

## B1. P4B-08 — ADS netlist 端口映射

**这是什么**：把 S-参数文件（S4P）转成 AMI 建模矩阵时，必须知道每个端口对应 victim/aggressor 哪一列。这需要 ADS（仿真工具）的 netlist 来确认端口顺序。

**已做到的**：S4P 结构已观察（6 个 Gen5 文件）；矩阵决策面已冻结为 `prohibited_without_port_mapping`。

**为什么需要你决策**：没有端口映射，就无法安全构造 AMI 矩阵，也不能把 RX 链路交给 Channel。

**选项**：提供/授权一份 ADS netlist（或确认端口顺序映射）。


## B2. P4B-09 — 授权 profile 运行 `sipi ami run`

**这是什么**：运行 AMI 仿真 CLI。纪律要求只允许显式、已认证 profile，**不允许静默默认**。

**为什么需要你决策**：需要一份你授权认可的 profile 才是合法的运行输入。

**选项**：提供你认可的 profile 名称。


## B3. P5-02 — 生成权威 R480 参考的 Oracle 授权

**这是什么**：COM(IEEE 802.3) 的权威基准。02e-02j 已经做了参数键、JSON、warning 观察、scalar 默认值解析并跨检通过。

**已做到的**：canonical JSON v2（160 literal + 7 resolved + 3 evaluated + 20 oracle + 39 none）、warning 观察（25）、scalar 默认解析（20/20 跨检）。

**为什么需要你决策**：产品要完成 **warning contract** 和**向量/矩阵默认布局**，需要授权 MATLAB oracle / agent-com 生成真正的权威参考（R480），而不仅是观察。

**选项**：授权启用 MATLAB oracle 产出权威 golden 文件；或暂缓（保持观察级）。


## B4. P5-06 — 用 MATLAB oracle 输出做 required COM 示例比较

**这是什么**：拿 MATLAB 算出的 COM 示例（26.56 GHz / 120g C2M TP1a）和产品做比较。

**已做到的**：06a 首次 run 成功（~11 min）、06b 指标面、06c 归一化输入面。

**为什么需要你决策**：要做 compare matrix（逐项比较），需要你授权把这批 MATLAB oracle 输出作为比较基准。

**选项**：授权启用比较；或暂缓。

---
# 第三部分：备注（当前标为『语义未实现』，但要推进同样需要你）
---

## C1. C2. P4A-02 / P4A-03 — IBIS 行为规格与 typed AST

**是什么**：P4A-02 从公开标准+授权黑盒形成 IBIS 行为规格；P4A-03 用 clean-room 实现 Rust 解析器与 typed AST。

**已做到**：02a 做了 scope preflight；03a/03b-preflight/03c 已做了 structural parser、typed semantic envelope。

**卡点**：行为 spec 需要 DLL 身份/授权行为观察；typed AST 需要 profile 的 keyword 规则。→ 需要你提供 DLL 身份或授权某份官方 `.ibs`。


## C5. P2-06 — 泛化 parsed-circuit/measurements

**是什么**：从电路解析后直接比较测量值。

**卡点**：需要 netlist 面（电路定义）作为支撑。→ 需要你决定是否提供 netlist。


---
# 第四部分：我能自己推进、不用你决策的
---

- **P5-02 向量/矩阵默认布局**：`[1 3 2 4]`、`[50,50]`、`[0 0]`、string-matrix `pkg_Z_c`。自包含、可对 oracle 跨检。**（我建议的下一步）**
- **P5-08 `sipi com run`**：按更小切片谨慎接入。
