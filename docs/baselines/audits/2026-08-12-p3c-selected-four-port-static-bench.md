# Independent Audit: P3C-04a Selected Four-Port Static Bench

审计对象：限定的四端口 Touchstone lexical parser 与固定 P3C ADS bench
静态差分约简。Orca OpenCode 进行只读审计，结论为 `0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| asset boundary | pass: parser only consumes caller-supplied memory; no external S4P bytes or path is tracked/read |
| fixed port semantics | pass: port order is fixed to TX+, RX+, TX-, RX-; asymmetric synthetic matrix verifies public column-major mapping |
| reduction | pass: only `(S21-S23-S41+S43)/4` is implemented; differential-through and common-mode-only cases remain distinct |
| fail-closed parsing | pass: only four-port `Hz S RI R 50.0`, finite data and strictly increasing frequencies are admitted; malformed continuation and keywords reject |
| time-domain boundary | pass: no IFFT, interpolation, DC/high-frequency fill, causality/passivity repair, waveform generation or CLI route |
| source drift | pass: P3A v4 stays historical, active channel evidence is removed and the exact source-drift blocker is verifier-enforced |

已执行并通过：

```text
cargo test --workspace
python -B tools/verify_p3c_selected_four_port_static_bench.py
python -B tools/test_verify_p3c_selected_four_port_static_bench.py
python -B tools/test_verify_release_capability_publication.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/verify_product_boundary.py
```

保留阻塞：fresh selected-S4P static custody、产品侧时域 network policy、candidate
waveform generation、external reference binding、accepted receiver 和 statistical-eye
contour semantics。该切片不是 ADS transient parity 或 profile/release acceptance。
