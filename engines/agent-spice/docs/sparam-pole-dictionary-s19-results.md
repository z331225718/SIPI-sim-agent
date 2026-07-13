# s19 Pole Dictionary Sparse Selection 结果

## 结论

**[FACT] 判定为 `NO-GO / condition_or_residue_explosion`。** Native 与可复现再生的 global-modal 两类来源组成了71个稳定共轭 blocks、effective capacity 82；冻结 top-K group selection 完成 orders `56/60/68/74` 的完整826点 LS。order74 raw RMS为 `0.00593317`，condition为 `4.511e13`，最大 residue/input 比为 `6.719e18`，未过数值门或 promotion gate，因此未运行 enforcement。

## 来源审计

- D4/D5 Native Test16 artifacts逐SHA读取，展开后各8 poles；二者属于同一Native类别。
- 原 stabAAA、RKFIT、modal worktree artifacts确已缺失，均保留 `artifact_missing` 记录，没有从Markdown或IdEM重建。
- global-modal来源由冻结提交 `35dea90` 的 rank8/24 traces/48 scalar fits/no-oracle代码从原始s19重新生成；`selected-poles-74.json` SHA为 `3199251e1046d8e5b16a8709cfbd63c0da809108f75657aac93bd66a6d8cebbd`。
- 再生来源与原缺失来源在source audit中分开记录；IdEM poles/topology从未进入manifest或字典。

## 冻结搜索

字典聚类后有71 blocks、capacity 82。每个block只做一次64点screening；每轮只把冻结top-K=4送入full-826 LS，接受只看full-grid authority。每个target additions不超过target order，全流程仅一轮same-cost swap（最多4个full候选）。中断恢复只复用同时存在的order JSON与selection trace，没有改变参数。

| Order | Raw RMS | Raw max sigma | Condition | Max residue/input | 结果 |
|---:|---:|---:|---:|---:|---|
| 56 | 0.009293412062 | 1.036024496 | 4.212e13 | 6.930e16 | 数值门失败 |
| 60 | 0.008632527165 | 1.040987017 | 4.352e13 | 3.098e16 | 数值门失败 |
| 68 | 0.007682066829 | 1.052387377 | 4.499e13 | 9.648e18 | 数值门失败 |
| 74 | 0.005933172542 | 1.024419599 | 4.511e13 | 6.719e18 | 数值门与promotion均失败 |

order74仍为canonical Native order74 raw RMS `0.001721840685` 的约 `3.45x`，也远高于absolute promotion门 `0.0015`。相较纯modal order74 raw `0.00769684` 有改善，但不足以形成竞争性共享分母。

## 证据边界

**[FACT]** 当前实现与冻结字典均为NO-GO，不进入Native生产路径。

**[STRONG INFERENCE]** 多源subset selection能从同一候选池中改善纯modal结果，但候选块本身高度相关且使LS严重病态；“更聪明地选已有poles”没有弥合IdEM差距。

## Artifact

- `runs-sparam/pole-dictionary-s19-v4/summary.json` SHA：`62eda02b12d6a4a5605434782e1dde377c5687062bc04069126b0274fea7d856`
- `runs-sparam/pole-dictionary-s19-v4/ledger.json` SHA：`4bbd28cfb443654a286c7101e1f6e0e7850c032c316638009e320493153a8792`
- `runs-sparam/pole-dictionary-s19-v4/report.md` SHA：`5ef228f96b3525478fed0fbc89f640e23354b8df9daa1c6688b66cd745899a9d`
- 四个order JSON与selection trace均由ledger记录。
