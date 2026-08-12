# Independent Audit: P3C-03b PRBS9 Sealed-Artifact Metric CLI

审计对象：`sipi compare prbs9-metrics --stdin --artifact-root <root>` 及其
sealed-artifact reader、strict request/metadata contract 和 release ledger
binding。审查员为 Orca OpenCode，只读审计结论为 `0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| exact sealed consumption | pass: manifest identity、exact file set、same-read payload hash/length 和 manifest reread 均 fail-closed |
| filesystem boundary | pass: symlink and Windows reparse points rejected; specification explicitly retains P1 v1 no-hostile-writer assumption |
| fixed PRBS9 metadata | pass: contract, quantity/unit, timebase, sample count, encoding, byte length and payload digest are exact; unknown fields rejected |
| waveform handling | pass: exact binary64 little-endian decode, finite check, no trailing bytes, no alignment or resampling |
| information boundary | pass: success/failure surfaces omit root, relative file names and samples; both artifacts verify before metrics run |
| admission/release | pass: external reference binding and profile acceptance remain not evaluated; generic compare blocker, P4B, receiver and statistical-eye gates remain unchanged |
| governance | pass: schema inventory, clean-room register and product-boundary inventory validate |

已执行并通过：

```text
cargo test -p sipi-artifacts -p sipi-contracts -p sipi-cli
python -B tools/verify_p3c_prbs9_metric_artifact_cli.py
python -B tools/test_verify_p3c_prbs9_metric_artifact_cli.py
python -B tools/test_verify_release_capability_publication.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_product_boundary.py
python -B tools/verify_release_capability_publication.py --command-manifest <current sipi commands --json>
```

审查员记录的非阻塞建议：future response schemas can be tracked if the
project later admits response-schema inventory, and a Windows reparse-specific
negative test may be added when a portable test fixture is available. Neither
changes the current fail-closed route or admission state.
