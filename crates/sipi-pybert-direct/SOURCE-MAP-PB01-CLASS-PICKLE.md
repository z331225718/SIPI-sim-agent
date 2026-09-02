# PB-01 class-pickle source map

This additive map covers the portable result-codec slice that emits the
object graph consumed by the pinned PyBERT result loader. It does not copy
PyBERT or the NumPy/Traits/Chaco implementations and it does not add a second
simulation engine.

## Pinned provenance

The reference is PyBERT commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`.

| Upstream path | Blob SHA-1 | Bytes | Blob SHA-256 | Rust adaptation |
| --- | --- | ---: | --- | --- |
| `src/pybert/results.py` | `4d8eafa77a20ef8a3ac307f6ae8c0397deb8e907` | 5835 | `b8655be9eb47311a030adfe2ce4e54169bab502b6c6ccdde24ca182aaec08635` | `src/legacy_runtime.rs`: `PyBertData` state keys and canonical 23-item order |
| `src/pybert/cli.py` | `4c1116007d31bcebf8db3252363eed7774c7b349` | 12806 | `3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9` | `src/bin/sipi-pybert-direct.rs`: `sim` defaults to the source-compatible class result; the SIPI dictionary is explicit |
| `src/pybert/models/bert.py` | `f04340c1028078175b26d7882efeeaf96f001abf` | 70571 | `145cb77bd1c864a41c307e76581beb19c6de7ec1a5764cada9df82882bbf4d10` | `src/legacy_runtime.rs`: seven plot frequency responses use magnitude dB after removing DC |
| `src/pybert/utility/math.py` | `d9c5de2ba9d24ee2981a197e24e8c7489406f0ec` | 4721 | `a8b1df23e87ac5580940eae6c7bb539b5342e68bc1ef18fde5794c0ddb97dc42` | `src/legacy_runtime.rs`: `safe_log10` floor of `1e-20` (`-400 dB`) |

The class pickle also names the runtime-owned classes
`chaco.array_plot_data.ArrayPlotData`,
`traits.trait_dict_object.TraitDictObject`, and the NumPy ndarray/dtype
reducers. Those globals are references, not vendored source. Their package
licenses remain governed by the normal dependency inventory.

## Implemented slice

The crate-private class codec serializes protocol 3 with root global
`pybert.results.PyBertData`. Its state contains `the_data`, `date_created`, and
`version`; `the_data` contains an `ArrayPlotData`, whose `arrays` contains a
`TraitDictObject` with the pinned 23 canonical item names. The 22 plotted
numeric entries are one-dimensional little-endian NumPy `float64` ndarrays.
As in `results.py`, `tx_out` is instead a zero-dimensional NumPy object array
whose item is `None`; it is a plot-data placeholder, not the internal native
transmitter waveform. The seven `*_H` arrays are
`20*log10(max(abs(H[1:]), 1e-20))`; the DC bin is not serialized. When the
native output carries the legacy frequency/stage telemetry, the class codec
uses that fixed grid and the disabled CTLE/DFE padded identity plot vectors,
matching the source result shape. It otherwise falls back to the scoped Rust
FFT presentation and is not claimed to equal every upstream `len_f_GHz`
truncation.

`LegacyResultCodecV1` and `run_legacy_sim_with_codec_v1` are the only new
public selection surface. The class writer and pickle opcode writer remain
private. Like upstream `pybert sim`, the CLI defaults to `class-pickle`;
`sim --result-format sipi-dictionary` retains the SIPI-owned dictionary,
including its historical interleaved real/imaginary `*_H` values. The
dB/removed-DC projection applies only to the class codec. The class path streams arrays
without a 23-array clone, enforces checked logical-payload and codec-owned
buffer budgets, verifies the complete temporary file by SHA-256 and length,
and publishes with a same-directory no-clobber hard link. The budget excludes
the caller-owned `SimulationOutputV1`, allocator bookkeeping, and internal
FFT planner/scratch memory.

The SIPI-owned dictionary writer and `run_legacy_sim_v1` remain unchanged for
Rust callers. The CLI default changes only to mirror the source command-line
artifact contract; callers can request the historical dictionary explicitly.

## Boundary

Focused Rust tests bind frequency values, no-clobber publication, and canonical
key order. A feature-gated pinned-environment test
fixes the pickle GLOBAL allowlist, unpickles the result as
`pybert.results.PyBertData` and confirms `ArrayPlotData`/
`TraitDictObject` reconstruction, then checks every numeric ndarray's exact
type, shape, C-contiguity, and logical f64 digest plus the `tx_out` object
scalar semantics. A separate feature-gated oracle test requires the pinned
source commit and a clean `src/` tree, runs its `pybert sim` command and the
Rust CLI over the same fixture, and compares all 22 numeric plot arrays with
their exact dtype/shape and a documented `1e-7 + 1e-6 * max(abs(values), 1)`
tolerance; it also requires the `tx_out` object placeholder to agree. The
fixed metadata is explicitly noncanonical. This is bounded class-load and
scoped numeric compatibility, not byte identity with Python's pickle stream,
GUI state parity, or global PyBERT branch parity. AMI/IBIS/DLL and other
external model branches remain outside this codec.
