# 当前剩余 22 项：缺口说明与 Owner 回复表

日期：2026-08-21
基线提交：`58ddf6f9` (`feat: advance bounded simulation semantics`)
权威开放项清单：`docs/baselines/plan-remaining-items-ledger.v1.yaml`

## 1. 这份文档要解决什么

当前 PLAN 还剩 22 项：7 项缺外部资产或权威 oracle，6 项缺产品语义，9 项是发布门。

这 22 项并不都需要 owner 立即作决定：

- 6 项产品语义中，有些可以由 owner 选择明确的收口范围，有些需要继续参考原项目。
- 7 项外部资产/oracle 主要缺文件、Git identity、运行许可、结果 provenance 或分发边界；一般授权不能替代第三方权利事实。
- 9 项 P7 发布门是下游结果，不建议逐项“批准通过”。它们必须等前两类证据闭合后机械重跑。

本文件把“需要你选择的政策”和“需要你提供或授权获取的事实”分开。最后一节提供可直接回复的模板。

## 2. 推荐的总策略

推荐采用以下总原则：

1. 原项目只作为 external-only、hash-bound 的参考输入；未经逐对象许可审计，不复制源码或资产进发布包。
2. 产品实现优先选窄、显式、无自动调参的 profile；不要为了关闭 PLAN 而实现 generic SPICE、generic IBIS、generic AMI 或 generic COM。
3. reference/candidate 默认严格同 index、同 checkpoint；禁止隐式 alignment、gain fit、DC removal、polarity flip、resample 或按结果选择最好参数。
4. owner 可以决定产品政策和范围，但不能代替第三方版权、再分发权、vendor DLL 运行权或 fresh-machine 事实。
5. P7 保持 `release_ready=false`，直到 license/NOTICE、fresh-machine、动态依赖闭包和当前 candidate chain 全部完成。

## 3. 需要 Owner 选择的 6 项产品语义

### D1. P2-06：parsed circuit 与 measurement stage compare

**已经完成**

- 产品已有严格七行 RC/PULSE deck consumer：title、单电压源、单 R、单 C、`.tran`、单一 `.measure TRAN <name> MAX V(out)`、`.end`。
- 复用现有 one-node RC/PULSE 内核，`.op`、`.ac`、额外器件、windowed measurement、泛化 netlist 均拒绝。
- 波形与 pinned Agent-Spice 观察在冻结误差内一致。

**仍缺什么**

- 已执行的 Agent-Spice oracle 没有消费同一份七行 deck，也没有输出其自己的 measurement 结果。
- 因此目前只能证明“产品 bounded consumer 可运行、波形接近”，不能证明 parser/measurement stage 与原项目同输入一致。

**选项**

- `A（推荐）`：保持 P2-06 open，从 Agent-Spice 原项目找到能够执行同一 deck 并导出 parsed circuit、time grid、waveform、measurement 的入口，做 two-fresh external replay。禁止扩大产品 grammar。
- `B`：把 P2-06 的目标正式缩窄为“产品自有七行 profile”，取消外部 parser/measurement parity 要求；完成后只能称 product-owned scoped profile。
- `C`：开始定义 generic netlist/measurement v1。需要另行冻结 grammar、节点/器件集、`.tran`、`.measure` 运算、window/interpolation、错误模型和资源预算，工作量最大。

**请回复**：`D1=A/B/C`。若选 B，请同时确认“P2-06 不再要求 Agent-Spice parser/measurement parity”。

### D2. P3B-02：RX CTLE -> RX FFE 的真实语义

**已经完成**

- 顺序固定为 RX CTLE 后 RX FFE。
- 每级必须显式选择 `Bypass` 或 `ExplicitCausalFir`，禁止 silent default 和 auto-tuning。
- 两级都复用唯一 full-linear convolution，具备 finite、tap、输出长度和 MAC 预算门。
- 公开 wire v1 仍保持 bypass-only。

**仍缺什么**

- CTLE 是参数化 transfer function 还是 caller-supplied impulse；其 grid、归一化、初始状态未定。
- FFE 是 symbol-spaced 还是 sample-spaced；tap 顺序、cursor、单位、符号和 delay 未定。
- 没有选定 profile、外部 oracle、容差或 provenance。

**选项**

- `A（推荐）`：从 PyBERT 原项目审计并选取一个固定 CTLE + FFE profile。产品只实现该 profile；参数显式、无调参、无默认。先 source-map/许可审计，再定义数值语义。
- `B`：把当前两级 caller-supplied causal-FIR 组合定义为 P3B-02 的最终 scoped contract，不再声称模拟参数化 CTLE 或 cursor-aware FFE。
- `C`：设计新的产品自有参数化 profile。需由 owner 明确 CTLE 零极点/增益和 FFE tap/cursor/timebase 全部字段。

**请回复**：`D2=A/B/C`。若选 A，请确认可只读审计 PyBERT 的相关 CTLE/FFE 路径，并采用 external-only/hash-bound 参考。

### D3. P3C-03：COM / ERL / TD-ILN compare contract

**已经完成**

- 产品已有 typed `COM_dB`、`ERL_dB`、`TD_ILN_dB` bundle。
- 每个 metric 都要求 caller 显式给 tolerance；没有默认 tolerance、对齐、单位转换或 oracle。
- 历史 C4 的 `ICN_mV` 不会被冒充为 `TD_ILN_dB`。

**仍缺什么**

- authoritative reference artifact，尤其 TD-ILN reference value。
- clean input/output provenance 与明确 checkpoint。
- 三个 metric 的最终 acceptance tolerance。

**选项**

- `A（推荐）`：以 pinned Agent-COM/MATLAB R4.80 输出为 oracle；严格同 profile、同 checkpoint、无 alignment。三个 dB metric 均采用绝对容差 `0.1 dB`。
- `B`：沿用相对容差 `<1%`，但必须说明 dB 值上的相对误差定义以及 reference 接近 0 时的处理。
- `C`：分别指定三个容差和 checkpoint；按下方字段回复。
- `D`：暂不设置 acceptance，只做 hash-bound 数值 observation，P3C-03 保持 open。

**请回复**：`D3=A/B/C/D`。若选 C，请填写 `COM_dB tolerance`、`ERL_dB tolerance`、`TD_ILN_dB tolerance`、`checkpoint`、`alignment policy`。

### D4. P4A-03：IBIS parser/typed inventory 的收口范围

**已经完成**

- consumer 现在要求完整文档、唯一且无 payload 的最终 `[End]`。
- 对完整 external official object 已观察到 95 models、4 selectors、200 pins 的 bounded inventory。
- tracked IBIS 是严格截断前缀，缺 `[End]`，已明确拒绝 semantic/electrical 使用。

**仍缺什么**

- 完整 AST/rule coverage。
- 产品要用的 model、selector、corner/PVT 和 behavior family。
- 与动态 electrical behavior 的契约。

**选项**

- `A（推荐）`：按 selected model 所需关键字做 scoped parser；未使用关键字继续 fail-closed，不追求完整 IBIS 5.0。
- `B`：实现完整 IBIS 5.0 grammar/AST 与一致性规则。这是较大独立项目。
- `C`：P4A-03 仅定义为 structural inventory，不进入 electrical runtime；当前 scope 可关闭，但 P4A-01/02 继续阻塞。

**请回复**：`D4=A/B/C`。若选 A，请在 E2 中给出 model/selector/corner。

### D5. P4B-02：AMI 参数语义与 193 个 helper 的处置

**已经完成**

- 已确认真实生产路径为 `parse_and_bind -> verify_binding -> AmiTextBinding -> AMI_Init`。
- 193 个泛型 helper 仍是 `keep=0 / pending=34 / delete-candidate=159`，没有被误称生产能力。

**仍缺什么**

- selected vendor `.ami` 的权威参数树。
- Init/GetWave 使用的参数、类型、默认值、约束和方向。
- 哪些 pending helper 有真实生产 consumer。

**选项**

- `A（推荐）`：以 selected vendor `.ami` 为唯一 profile，只实现 production-consumed 参数子集；未被消费的 159 项进入后续删除，34 项逐项判定。
- `B`：维持 raw text binding，不对参数做产品级 typed interpretation；P4B-02 以较窄范围关闭。
- `C`：建立 generic AMI parameter framework。需要标准条文、vendor compatibility corpus 和复杂度预算，不建议当前选择。

**请回复**：`D5=A/B/C`。若选 A，请同时完成 E4 的资产/运行授权字段。

### D6. P5-08：是否公开 `sipi com run`

**已经完成**

- 内部已有完整 bounded composition：sealed `pulse.f64le` -> P5-05g 参数 ingestion -> 既有 COM execution -> immutable `result.json` -> bounded artifact report。
- request 在反序列化和 artifact I/O 前做大小限制；request scalar 必须与 ingestion DTO 精确一致。
- legacy request/result wire 未改。

**仍缺什么**

- 是否将此内部能力发布为公共 CLI/API。
- authoritative COM profile/oracle acceptance。
- external provenance、hostile-writer、安全 custody 和用户可理解的错误面。

**选项**

- `A（推荐）`：先发布 narrow `specified/non-oracle` artifact CLI，只支持当前 exact artifact/schema；明确不是 Agent-COM parity，也不是 acceptance。
- `B`：等 P5-02/P5-06 oracle 闭合后再开放公共 route；当前保持 internal-only。
- `C`：不开放 CLI，把它保留为库内组合 consumer，并把 P5-08 收口为 internal capability。

**请回复**：`D6=A/B/C`。

## 4. 需要外部材料或权威事实的 7 项

这些项目不是简单的“同意/不同意”。如果选择让我们继续，需要给出可验证的对象身份或允许我们从指定原项目读取、运行并生成仓外 hash-only 报告。

### E1. P1-04B：旧 external fixtures

**缺少**：14 个旧资产中实际 required profile 的选择、精确 Git/file identity、custody、运行/比较权以及分发边界。

**推荐回复**：允许从现有 Agent-Spice、PyBERT、Agent-COM pinned Git objects 读取并执行；仅 external-only/hash-bound；禁止把 fixture bytes 放入仓库或发行包；逐项目另行确认 profile。

**需要填写**：selected fixture IDs、source repo/commit/path、是否允许执行、是否允许保存 hash/aggregate、是否允许再分发。若再分发权不确定，请填 `external-only, redistribution not authorized`。

### E2. P4A-01：完整官方 IBIS 资产

**缺少**：完整文件 bytes/hash、合法 custody、model/selector/corner、使用和分发边界。

**推荐回复**：使用完整官方对象作为 external-only 输入，不跟踪原文件；选定唯一 model/selector/corner 后实现 scoped consumer。

**需要填写**：完整文件位置或获取方式、SHA-256（可由我们计算）、model 名、selector、corner/PVT、table family、运行权、再分发权。

### E3. P4A-02：动态 IBIS endpoint

**缺少**：reference/supply 节点、初始状态、积分法、timebase/grid、stimulus、channel return、资源上限、容差和 acceptance oracle。

**选项**

- `A（推荐）`：本阶段明确不实现 dynamic endpoint；P4A 只保留 static/declaration，等待权威 profile。
- `B`：采用产品自有固定 transient profile；需要把上述 11 类字段全部给出。
- `C`：从指定外部 reference implementation/profile 审计并移植窄语义；需给出来源与许可边界。

**请回复**：`E3=A/B/C`。

### E4. P4B-08 / P4B-09：vendor AMI runtime

**缺少**：vendor DLL/AMI 文件运行权、精确 identity、参数兼容、动态依赖闭包、隔离 worker、fresh runtime evidence。

**选项**

- `A（推荐）`：允许在隔离、仓外环境执行 selected vendor AMI；资产不进入仓库/发行包；报告只保留 hash、PE/import/runtime aggregate。
- `B`：只做静态 identity/parameter observation，不执行 vendor DLL；P4B-08/09 保持 open。
- `C`：停止 vendor AMI 路线，仅保留公开 AMI text/host contract。

**需要填写**：selected `.ami`/DLL 路径或获取方式、SHA-256、允许的平台、运行权来源、是否允许隔离执行、是否允许保存 hash-only report、已知依赖安装说明。

### E5. P5-02：Agent-COM 参数/default/warning oracle

**缺少**：完整 warning/default contract、权威 MATLAB/Agent-COM 输入输出和 clean provenance。当前只有 MLSE 的有限 source-observed subset。

**推荐回复**：允许对 pinned Agent-COM/IEEE 相关对象做逐路径来源/许可审计，并在仓外 clean checkout 执行；只保留 canonical JSON、hash 和 bounded scalar/vector metadata，不保留 MATLAB workspace bytes。

**需要填写**：权威 repo/commit、允许执行的入口、required profile、输入文件、期望输出/checkpoint、是否允许 hash-only report。

### E6. P5-06：COM / ERL / TD-ILN oracle compare

**缺少**：current clean MATLAB oracle/input provenance、TD-ILN reference、checkpoint/alignment、最终 tolerance。

**推荐回复**：允许从 pinned Agent-COM clean checkout 运行同一 selected profile；reference/candidate 严格同 checkpoint、无 alignment；采用 D3 选择的 tolerance。

**需要填写**：oracle repo/commit、entry point、输入 asset identity、checkpoint、三项 reference 的输出字段、alignment policy、tolerance policy、是否允许保存 hash-only report。

### E7. P4A/P4B/P5 外部权利的统一边界

为避免每次重复询问，可以给出一条统一授权，但它只能覆盖操作权限，不能创造第三方权利：

> 允许 Codex 对我指定的 external repositories/assets 做只读、逐路径来源与许可审计；允许在仓库外 clean/isolated 环境运行；允许仓内保存 hash、长度、结构化 aggregate 和审计结论；禁止保存或发布第三方源码、模型、DLL、IBIS/AMI 原始 bytes；没有明确分发证明时一律标记 external-only / redistribution not authorized。

请回复是否接受这条统一边界：`E7=接受/修改如下`。

## 5. P7-01 至 P7-09 为什么还没完成

P7 的 9 项不是 9 个需要 owner 点击“同意”的功能，而是一条发布链：

| 项目 | 当前含义 | 主要剩余阻塞 |
|---|---|---|
| P7-01 | Windows twin build | current candidate 变化后需重建并证明 byte identity |
| P7-02 | composition | license manifest 仍 provisional，动态/运行闭包未完成 |
| P7-03 | archive | archive 结构已验证，但不是 release approval |
| P7-04 | isolated install | 仅 same-host；fresh machine/user/loader closure 未评估 |
| P7-05 | capability publication | ledger 是 pre-release，领域 profile 仍有未接受项 |
| P7-06 | evidence anchor | candidate drift 后需整链重绑，不能继承旧 executable |
| P7-07 | license/NOTICE | 仅观察 86-package build closure；dependency、NOTICE、first-party、SBOM 尚未批准 |
| P7-08 | retirement | owner 已批准计划；仍需同批删除、drift-gate retirement 和 release gate |
| P7-09 | external history | registry 已完成；最终删除/发布审计未完成 |

**推荐决策**：现在不单独批准 P7-01..09。先完成 D/E 项；之后以同一个 committed candidate fresh 重跑 twin -> layout -> composition -> archive -> install -> performance -> evidence anchor，最后做 license/NOTICE/fresh-machine 审核。

如果你的发布目标有变化，请补充：

- 目标平台：默认 `Windows x86_64 MSVC`。
- 最低系统：建议 `Windows 10 / Server 2016`。
- 分发形式：建议仅 `sipi.exe + LICENSE`，第三方外部资产不打包。
- 是否要求 fresh-machine：建议正式 release 前必须。

## 6. 推荐的一次性回复

下面是我建议的默认组合。你可以直接回复“全部按推荐”，或逐项覆盖。

```text
总原则：接受第 2 节五条原则。

D1=A  # 继续寻找 Agent-Spice 同 deck/parser/measurement external replay
D2=A  # 从 PyBERT 选择并审计固定 CTLE -> FFE profile
D3=A  # Agent-COM R4.80；COM/ERL/TD-ILN 各 0.1 dB；strict same-checkpoint/no alignment
D4=A  # 只实现 selected IBIS model 所需 grammar
D5=A  # 只实现 selected vendor AMI 的 production-consumed 参数
D6=A  # 公开窄的 specified/non-oracle artifact CLI

E1=允许 pinned Agent-Spice/PyBERT/Agent-COM external-only hash-bound 读取与执行；不授权再分发
E2=<完整 IBIS 文件位置/获取方式>；model=<...>；selector=<...>；corner=<...>
E3=A  # 暂不实现 dynamic IBIS endpoint
E4=A  # 允许 selected vendor AMI 在仓外隔离执行
E5=允许 pinned Agent-COM clean checkout 运行参数/default/warning oracle
E6=允许 pinned Agent-COM clean checkout 运行 COM/ERL/TD-ILN oracle
E7=接受统一 external-only 审计边界

P7 target=Windows x86_64 MSVC
P7 minimum OS=Windows 10 / Server 2016
P7 package=sipi.exe + LICENSE only
P7 fresh-machine required=yes
```

## 7. 回复后的执行顺序

收到回复后，建议按以下顺序推进：

1. 先处理无需 vendor DLL 的 D1、D2、D3、D4、D6。
2. 并行完成 E1/E2/E5/E6 的 external clean custody 与 hash-only observations。
3. 资产与权利闭合后处理 D5/E4；vendor DLL 始终隔离执行。
4. 更新 PLAN/ledger，只关闭真正满足 gate 的项目。
5. 最后冻结一个 current candidate，完整重跑 P7 发布链。

任何 external compare 失败都记录真实 rejected evidence；不调整容差、参数、alignment 或 profile 去追结果。
