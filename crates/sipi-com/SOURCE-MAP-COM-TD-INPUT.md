# COM TD input source map

Scope: the additive `sipi-com::td_input_v1` library leaf. The implementation
ports only portable Python signal preparation and does not fit S-parameters.
The typed API requires finite, strictly increasing time, aligned pulse/impulse
arrays and bounded sampled work before convolution or FFT allocation.
`validate_td_pulse_input_v1` uses exact `f64` impulse equality as a bounded
Rust typed-input policy; it is not a claim that the upstream Python dataclass
performs the same validator or that cross-language floating-point results are
bit-identical.

| Upstream path | Role in this leaf | Git blob | Bytes | Content SHA-256 | License |
| --- | --- | --- | ---: | --- | --- |
| `src/agent_com/signal/td_input.py` | `read_td_pulse_csv` pulse/impulse construction and `td_fd_fillin` frequency fill-in | `1d8874fc55351d68bbf8f56356244f5a4c5650b6` | 6671 | `ba1344991ea3310955c5b82dc3500e4e10b87c04b40cbd878a1344ff0003ca76` | MIT |
| `src/agent_com/signal/filters.py` | Bessel-Thomson and Butterworth response primitives consumed by fill-in | `3c43bf74124fb9264576566841facc5b5259ccd7` | 4734 | `79b3218a1315b53ae0e7e518a43d62e043658c105a7022a0fa868d0b34cb74b6` | MIT |
| `src/agent_com/_orchestration.py` | `_load_td_channel` call-site and TD role dispatch reference only | `5d260a0aab941f1a1955fe3abef36d85a56034c0` | 90877 | `069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69` | MIT |
| `src/agent_com/equalization/search.py` | `_td_source_crosstalk_noise` outer-product ordering, FEXT/NEXT amplitudes and frequency-axis consumption | `58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd` | 53859 | `924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d` | MIT |
| `src/agent_com/io/touchstone_r480.py` | TD/FD channel representation and frequency-dependent outer-product input contract | `99300e220c937f9ff73c8e97db47581be2a68241` | 7476 | `f0e037392656a7c70de9a5a2619411f76ae9c940afb4ed3ec44448dc4595fddd` | MIT |
| `LICENSE` | Upstream license text governing the audited source | `55aac2e4f8c36a978d315efb02815972579b8293` | 1067 | `d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2` | MIT |

All rows are fixed to upstream raw Git objects at commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`. The direct CLI admits the narrow
TDMODE CSV/TD THRU plus validated TD FEXT/NEXT outer-product route and feeds it
to the existing COM search consumer. The admitted TD response rows use the
short FD-fill-in SDD21 axis while the outer-product CTLE columns use the full
`noise_frequency_hz` axis, and the resolved `f2` integration limit is kept
distinct from `fb` when supplied. It does not claim full upstream TDMODE or
S-parameter parity; unsupported package-case/non-TD crosstalk remains
fail-closed.
