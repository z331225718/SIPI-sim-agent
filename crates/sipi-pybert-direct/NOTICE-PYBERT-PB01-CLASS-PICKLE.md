# PB-01 class-pickle notice

This notice covers the additive class-load-compatible result codec in
`src/legacy_runtime.rs`, the explicit `sim --result-format class-pickle`
adapter, and focused tests. It is subordinate to
`NOTICE-PYBERT-PB01-DIRECT-PORT.md` and
`NOTICE-PYBERT-LICENSE-BOUNDARY.md`.

The codec is a clean Rust serialization of the state shape described by the
pinned PyBERT `src/pybert/results.py` at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`. It does not copy upstream Python,
Chaco, Traits, or NumPy source and does not invoke Python at runtime. The
serialized artifact references those runtime class names so a compatible
consumer can reconstruct `PyBertData`; the consumer remains responsible for
having the corresponding packages installed.

The `date_created` and `version` state values are deterministic SIPI codec
metadata (`not-recorded` and a string marked `noncanonical`). They do not
claim to reproduce upstream wall-clock metadata or the upstream PyBERT
package version. The codec migrates the pinned class-load shape and canonical
plot arrays only; it does not claim byte identity, global numeric parity, or
support for arbitrary pickle input.

Python pickle loading executes referenced reducers. The codec's fixed GLOBAL
set constrains only artifacts produced by this Rust writer; it does not make
ordinary `pickle.load` safe for untrusted files. Consumers must load only
trusted, custody-verified artifacts. This slice makes no safe-unpickle,
sandbox, or hostile-input isolation claim.

The PyBERT repository root declares BSD-3-Clause. The exact root license
boundary and all third-party dependency licenses remain governed by the
existing notices and dependency inventory. This file is provenance and scope
documentation, not a license grant or redistribution authorization.
