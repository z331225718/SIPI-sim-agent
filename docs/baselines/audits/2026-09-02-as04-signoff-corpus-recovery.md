# AS-04 原始 `tune-yparam-tran` 输入恢复审计

日期：2026-09-02  
审计工具：[audit_as04_signoff_corpus_recovery.py](../../../tools/audit_as04_signoff_corpus_recovery.py)  
审计范围：本机候选仓库、Agent-Spice checkout、已存在的 Git worktree/snapshot、AS-04 相关 Temp 回放目录，以及两仓库的 Git refs/reflog/all-object 数据库。未联网，未运行 150 次优化，未运行 HSPICE 作业，未修改生产 Rust、CLI、PLAN、ledger 或 AS policy。

本次机器输出保留在 `C:/Users/z3312/AppData/Local/Temp/as04-signoff-corpus-recovery-20260902.json`，bytes SHA-256 为 `136a03f480041d89c3dc67e06945121943fea69bd8ec25aa940f9290dac63d04`。运行命令为：

```powershell
python tools/audit_as04_signoff_corpus_recovery.py `
  --json-out C:/Users/z3312/AppData/Local/Temp/as04-signoff-corpus-recovery-20260902.json
```

该输出的 `status` 为 `missing_original_signoff_corpus`，命令按设计以退出码 1 表示阻塞；测试命令 `python -m unittest tools.test_audit_as04_signoff_corpus_recovery` 为 5/5 通过，`py_compile` 和 `git diff --check` 也通过。

## 结论

结论为 **`missing_original_signoff_corpus`**。没有恢复到可作为原始签核输入的以下三份文件：

| 原始签核输入 | 候选仓库 | Agent-Spice checkout | 结论 |
| --- | --- | --- | --- |
| `runs/yparam-tran-signoff/vddq_port3_port10.s2p` | 不存在 | 不存在 | 缺失 |
| `runs/yparam-tran-signoff/ybootstrap_blackbox.rfm` | 不存在 | 不存在 | 缺失 |
| `runs/yparam-tran-signoff/ybootstrap_blackbox.sp` | 不存在 | 不存在 | 缺失 |

同名文件在候选仓库、Agent-Spice checkout、已知 snapshots/worktrees 和 AS/SIPI 相关 Temp 目录中均未发现。没有 RMS/peak 的原始 `.mt0`/`.lis`/报告结果，也没有能将这些结果绑定到原始输入的 commit/tree/archive provenance。因此不能把文档中的数值或合成 fixture 当成一对一 signoff 结果。

## Git 对象审计

审计读取了 `git rev-list --objects --all --reflog`、`git cat-file --batch-all-objects --batch-check`，并对每个 all-object tree 的 entry name 及每个 all-object blob 的文本 marker 做了检查。all-object 检查包含可达、reflog 和 pack/loose 中的孤立对象；它不是只看当前工作树。

| Git 数据库 | HEAD | HEAD tree | refs/reflog 路径数 | all objects | trees | blobs | 目标路径命中 | 目标 tree entry 命中 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `C:/Users/z3312/code/SIPI-sim-agent` | `dd122c1f7ff7d6b737c79f79cfc88cef0636fcde` | `aeab704e40a25743c8022d10aa9d8526ba8899e0` | 18,103 | 22,342 | 8,135 | 12,866 | 0 | 0 |
| `C:/Users/z3312/code/agent-spice` | `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` | `b6bde97128030d6cea0d68b2f0a35d807be8c402` | 3,751 | 17,464 | 10,884 | 6,188 | 0 | 0 |

Blob marker 命中不是输入恢复：候选仓库 10 个、Agent-Spice 17 个命中均落在文档、脚本或历史文档 blob 中；没有目标文件名对应的 tree entry。两仓库都没有 `objects/info/alternates`。候选工作树当时有其他 agent 的 dirty/untracked 项，Agent-Spice 也有无关 dirty 项；这些状态不改变 all-object/path 结论。

## 已找到但不能冒充输入的材料

### 1. 研究文档和脚本

| 材料 | Git provenance / SHA | 可复用内容 | 不能证明 |
| --- | --- | --- | --- |
| `C:/Users/z3312/code/agent-spice/docs/yparam-heldout-tran-signoff-report.md` | commit `ec4619f683e00192b88ec366ff204bbf0c766806`，tree `54ed470ad4c7dde9c2a1570f63a0374927991eca`，blob `e732a1755ec8a8caa201eb7372f53123996c042d`，当前 bytes SHA-256 `32931d86885f5e71cc0d9d19d70af15d9b3b918be524a440d8612bd712c2c52a` | 目标路径名、measure 名、极点、带边界、HSPICE 参数和研究性结果叙述 | 原始 S2P/RFM/SP 文件或独立 signoff |
| `C:/Users/z3312/code/agent-spice/scripts/tune_ybootstrap_tran.py` | HEAD blob `0aa63b81f5bd5bbc686460f68e52173dd8c92e14`，当前 bytes SHA-256 `63b5ea0ddd34bf74bc641adade61082a4c763e9d80555aebf26cfa85a9b5d989` | 入口假定 `runs/yparam-tran-signoff` 并读取三份输入 | 这些输入确实曾被保存或仍可恢复 |
| `C:/Users/z3312/code/SIPI-sim-agent/docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml` | 当前 bytes SHA-256 `3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8` | synthetic corpus 名称、external blocker、无 parity 声明 | 原始签核 corpus；manifest 自己明确不是 numerical parity |
| `C:/Users/z3312/code/SIPI-sim-agent/docs/baselines/audits/2026-08-23-as-04-tune-yparam-tran-v2.md` | 当前 bytes SHA-256 `2585655813258816e5122e88b7556d328f2191595b836b60c5c0182268e83408` | 两次 synthetic replay 的 custody 说明 | 原始项目文件或 HSPICE 结果 |

文档里的 `vddq_port3_port10.s2p`、`ybootstrap_blackbox.rfm`、`ybootstrap_blackbox.sp` 是路径和命令参数引用，不是附件。研究报告还明确把当前候选限制为 research candidate，并指出 source inputs/results 未被 tracking。

### 2. Temp 回放记录

已存在的 AS-04 JSON 只记录 synthetic/blocked 流程，没有目标文件名：

| 路径 | bytes | SHA-256 | 记录结论 |
| --- | ---: | --- | --- |
| `C:/Users/z3312/AppData/Local/Temp/as04-replay.json` | 7,585 | `1065042c509ce18c587c7cb3341723c256ed6e48bbe5fdfa86d6ceb39e83ebbe` | `parity_status=open`，synthetic corpus |
| `C:/Users/z3312/AppData/Local/Temp/as04-replay2.json` | 7,585 | `9ef18bd33867ae03e1ac3178a080ee302b1c60c00919365b418a1ed63d3726df` | `parity_status=open`，synthetic corpus |
| `C:/Users/z3312/AppData/Local/Temp/as04-v2-01.json` | 6,101 | `5ce94bbdb1376326f30010f1028981d94e143f09ee26c70cada4fb3554c3c478` | `completed_external_blocker_open`，`numeric_parity=false` |
| `C:/Users/z3312/AppData/Local/Temp/as04-v2-02.json` | 6,101 | `16a1475ccb0bf7b4ef5c428d8ca5b5f26d18a33eb97b411b5d59b5e20705f468` | `completed_external_blocker_open`，`numeric_parity=false` |
| `C:/Users/z3312/AppData/Local/Temp/sipi-as04-continue-20260826-01.json` | 6,104 | `83507db469d4faabb7a8420cdf5ebc25d8dc8a99ebe528629a6826204f4cbe7e` | `completed_external_blocker_open`，`numeric_parity=false` |
| `C:/Users/z3312/AppData/Local/Temp/sipi-as04-continue-20260826-02.json` | 6,104 | `12a703b50895233b15ce662e101b72181bcde54fe1f8497c99650547b8484f1d` | `completed_external_blocker_open`，`numeric_parity=false` |
| `C:/Users/z3312/AppData/Local/Temp/sipi-as04-continue-20260826-aggregate.json` | 3,136 | `f7274691b0685e21b05dbed75608c51a93964d4cd234477cd0e37fe0618b283e` | `completed_external_blocker_open`，input tree `97e8bfcf...` |

上表中的 SHA 必须以 Temp 文件和审计 JSON 为准；它们不是 Git tracked evidence，也不能替代原始 corpus。

## 可复用的签核契约

研究文档提供了以下**参数线索**，可在原始输入恢复后用于 materialization，但它们不是输入数据：

- measure：`yfit_vs_raw_rms`、`yfit_vs_raw_peak`；
- residual poles (Hz)：`0.0628318530718`、`0.8115045878714`、`10.48098478623`、`135.3671238969`、`1748.33363523`、`22580.59720916`、`291639.6276132`、`3766670.63349`、`48648421.94905`、`628318530.718`；
- band boundaries (Hz)：`22580.59720916`、`3766670.63349`；
- CPM/HSPICE 场景：0.8 V VRM、`method=gear`、`reltol=1e-5`、10 ps 输出步长、14 ns stop，measure 窗口 3.5 ns–14 ns；
- 本机 HSPICE runtime：`C:/synopsys/Hspice_T-2022.06-1/WIN64/hspice.exe`，208,896 bytes，SHA-256 `34b36fe40cb10b3c19a1f92567c0fa143c3bffade101d788c40cbbbbad5eb65c`。

### 明确缺失

1. 原始 `vddq_port3_port10.s2p` 的 bytes、格式/端口校验和 Git provenance；
2. 原始 `ybootstrap_blackbox.rfm` 的完整极点/残差文件；
3. 原始 `ybootstrap_blackbox.sp` 及其 HSPICE 网表替换位置；
4. 原始 RMS/peak measure 输出（例如 `.mt0`/`.lis`）和生成命令的绑定；
5. 可独立重放的 input tree/archive、toolchain receipt 和 signoff tolerance。

## 恢复后的验收门

如果后续在本机找到原始目录或收到归档，先只做以下步骤，不立即启动优化：

1. 逐文件记录绝对路径、bytes、SHA-256；若来自 Git，再记录 blob、commit、tree 和 archive SHA；
2. 检查目录是否确实为 `runs/yparam-tran-signoff`，并确认不是 `docs` 示例或 synthetic fixture；
3. 用冻结配置做两次独立 Git-archive replay，分别记录 HSPICE/工具链和 RMS/peak 输出；
4. 仅在两次报告都绑定同一三份原始输入、measure、pole/band 参数且数值比较通过后，才由主代理决定是否关闭 AS-04。

在此之前，`completed_external_blocker_open` 是正确状态；合成的 `line.s2p`/`model.rfm`/`signoff.sp` 或文档中的研究数字不能被提升为原始一对一 signoff。
