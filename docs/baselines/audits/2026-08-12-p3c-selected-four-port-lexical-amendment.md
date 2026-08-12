# Independent Audit: P3C Selected Four-Port Lexical Amendment v1

审计对象：selected four-port 的 `R 50`/`R 50.0` lexical v2 amendment、sealed
S4P v2 intake 与 fresh-custody observer charter。Orca OpenCode 只读审计结论为
`0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| v1 preservation | pass: `parse_selected_four_port_hz_s_ri_50_v1` 仍只接受 `# Hz S RI R 50.0`，`R 50` 继续拒绝 |
| v2 allowlist | pass: v2 只接受 exact `# Hz S RI R 50` 与 `# Hz S RI R 50.0`；`050`、`50.`、`50.00`、`5e1`、`+50`、`49.999` 均拒绝 |
| no hidden normalization | pass: 不使用通用 numeric option parsing，也未放宽 case、内部 whitespace、unit、format、keyword、port map 或 record grammar |
| historical evidence | pass: `ac08d78` clean-archive v1 rejected observation 的 hash-only identity 保留；未改写为 success |
| gate preservation | pass: v2 code/harness 仍不能提升 external custody、fit、stepping、waveform/reference/receiver、P4B 或 release |
| custody | pass: `uv.lock` 未触碰 |

已执行并通过：

```text
python -B tools/test_verify_p3c_selected_four_port_lexical_amendment.py
python -B tools/verify_p3c_selected_four_port_lexical_amendment.py
python -B tools/verify_p3c_selected_s4p_external_static_custody_observation_contract.py
cargo test -p sipi-touchstone --locked
cargo test -p sipi-p3c --locked
```

下一步只能从含此 amendment 的 clean archive 重跑两次 fresh seal/admit；在两次
external report 一致前，static custody 不得标记为 observed。
