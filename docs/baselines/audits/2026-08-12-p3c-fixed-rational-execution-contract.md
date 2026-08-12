# Independent Audit: P3C-04f Fixed-Rational Execution Contract

审计对象：P3C-04f owner-confirmed fixed-rational execution contract，以及由
`Cargo.lock` 漂移触发的 P2-06d/发布账本一致性修复。Orca OpenCode 只读审计结论为
`0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| real-model boundary | pass: positive-imaginary pole/residue pair 是唯一 canonical member，negative member 只可精确共轭派生；real-constrained fitting、LHP、pair order 与拒绝条件均冻结，04e complex-residue core 未被冒充为 real runtime model |
| execution semantics | pass: product-owned global rational continuation、100 as linear ramp、zero state、first-symbol、half-open strobe 和 analytic pair recurrence 均有确定语义；不声称 ADS 等价 |
| prohibited shortcuts | pass: D/E/delay、phase delay extraction、passivity/pole/residue repair、matrix exponential、ODE、adaptive step、resampling 与任何 alignment/gain/DC/polarity fit 都保持禁止 |
| gate preservation | pass: 仅 execution contract 状态为 specified；real fit hardening、sealed S4P、stepping、candidate waveform/reference/receiver/P4B/release 均保持 false 或 blocked |
| TRAN historical evidence | pass: 04e 造成的 `Cargo.lock` 漂移使 P2-06c v2 只作为 historical observed evidence；release TRAN row 已移除 accepted/external-oracle claim，且 verifier 只接受精确 `evidence_product_source_drift` |
| isolation | pass: Channel historical drift 分支未改变；`uv.lock` 未触碰 |

已执行并通过：

```text
python -B tools/test_verify_p3c_fixed_rational_execution_contract.py
python -B tools/verify_p3c_fixed_rational_execution_contract.py
python -B tools/test_verify_tran_rc_pulse_current_external_compare_evidence.py
python -B tools/test_verify_release_capability_publication.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
cargo test --workspace --locked
```

下一实现顺序仍固定为 real-constrained fit hardening、sealed exact-S4P
admission、analytic stepping、candidate artifact route，最后才是 external reference
binding 与 metric evidence。
