# P4B-02 参数 API 选择基线

## 结论

本票只做需求与可达性裁定，不删除 Rust、不恢复 feature-gated export、不创建逐 API runner。基线为 `805ebb6bbaf588dec08685be4eb78a8ce2fff563`。

当前默认产品没有一个 `sipi-ami-text` 参数语义 export 的生产 consumer：

- `sipi-ami-host` 只消费 `AmiTextBindingV1`、`ParseLimitsV1` 和 `verify_binding_v1`，把原始 `.ami` 字节传给 ABI；
- `sipi-ami-worker` 只消费 `ParseLimitsV1` 和 `parse_and_bind_v1`，不构造参数 catalog、profile 或 runtime table；
- 193 个 module/export 仍统一由 `test` 或 `p4b-self-crosscheck` 隔离，默认 host/worker Cargo 依赖不能访问它们。

因此最小 `keep_for_product` 集合是空集。任何“已有 Rust 自测通过，所以应该保留”的推断都被拒绝。

## 机器可验证分组

| 分组 | 数量 | 裁定 | 依据 |
| --- | ---: | --- | --- |
| `core-parameter-contract` | 7 | `quarantine_pending_requirement` | value/form/catalog/default/runtime table 可能属于未来授权 AMI profile，但 B2 exact profile contract 与生产 consumer 尚未落地 |
| `typed-profile-admission` | 27 | `quarantine_pending_requirement` | typed form、reserved/default、profile assembly/selection/serialization 只有在 B2 profile 给出精确 grammar 后才有需求 |
| `list-algorithm-surface` | 99 | `delete_candidate` | 通用 List 排序、集合、统计、距离、run/sequence 算法没有当前 AMI contract requirement 或 consumer |
| `tree-utility-surface` | 43 | `delete_candidate` | 通用 tree diff/merge/path/traversal/format/mutation/statistics 不属于当前 raw-byte contract |
| `profile-analysis-surface` | 13 | `delete_candidate` | profile diff/merge/canonicalization/fingerprint/equivalence/lookup 等 convenience surface 无生产用途 |
| `text-inspection-and-value-normalization` | 4 | `delete_candidate` | document stats/form heads/value equivalence/normalization 不属于 raw-byte boundary；normalization 在该边界明确禁止 |

完整 charter 位于 [`p4b-02-parameter-selection-charter.v1.yaml`](../p4b-02-parameter-selection-charter.v1.yaml)，以 `lib.rs` 中 193 个 feature-quarantined module 名称的排序 SHA-256 固定 inventory，并要求每个 module 恰好命中一个分组。当前计数为：`keep_for_product=0`、`quarantine_pending_requirement=34`、`delete_candidate=159`。

## AMI contract 与复杂度边界

现有 structural foundation 明确只承诺 parenthesized forms、opaque token、quoted spelling、comments、spans 和 raw-byte identity；其 `semantic_validation_status_v1()` 永远是 `RulesUnavailable`。02b1/02b3/02b5 等 stage charter 也都明确 profile-agnostic，不是 IBIS-AMI catalog、reserved-name catalog、runtime 或 profile acceptance。B2 仅授权 profile 资产目录，尚没有把该 profile 的 exact parameter grammar、defaults、reserved names、consumer route 或 tolerance 变成产品合同。

因此 pending 分组只保留当前已有的 name/value/List bounded construction limits 作为审计事实（name 256 bytes、value token 65536 bytes、List 512 items、双 List 262144 pair cells），不分配新的 public symbol、runtime dependency 或 product compute budget。delete candidate 的产品预算为零；本票不执行删除。

## Evidence 状态

现存 191 份 `p4b-02b*-crosscheck-evidence.v1.yaml` 均必须保持 `status: product_owned_self_crosscheck_unbound`。它们是产品 Rust 与 product-owned self-check 的测试记录，没有 source/runner/independent reference/contract digest，不能证明 AMI compatibility、profile parity、runtime admission 或 release。验证器拒绝任何 `matched_hash_bound` 变体，也不把 evidence 文件存在计数当作执行证明。

## T03 所需 consumer 路径

下一票必须先取得 exact owner-authorized AMI profile contract，再设计唯一的 typed adapter consumer：

`authorized AMI profile -> typed parameter adapter -> sipi-ami-host::AmiHostV1::initialize / sipi-ami-worker::run_one_job`

该路径需要独立 hash-bound oracle（source、runner、reference、contract 四项 digest）后才能把任何 pending API 提升为 keep。不得为了制造 consumer 而把 193 个 API 全部接入 host/worker，也不得把现有 self-crosscheck 当作 oracle。

## 验证

```text
python -B tools/verify_p4b_02_parameter_selection.py
python -B -m unittest tools/test_verify_p4b_02_parameter_selection.py -v
```

两者均通过；mutation tests 覆盖“无 requirement 不能 keep”“无 consumer 不能 keep”“self-crosscheck 不能授权 keep”“inventory selector 漂移”和“191 份 evidence 状态突变”路径。
