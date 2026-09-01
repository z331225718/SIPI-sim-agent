# AS-03 pinned scikit-rf custody recovery audit

Date: 2026-09-02

Audit tool: `tools/audit_as03_skrf_custody_recovery.py`

Scope: read-only inspection of local Git repositories, refs/reflogs/all Git
objects, installed Python distributions, uv extracted archives, and wheel
cache metadata. No network access, package import, download, or installation
was used. No Rust solver, CLI, PLAN, ledger, or product-boundary file was
changed.

## Pinned source

The AS-03 source map names scikit-rf 2.0.1 commit
`bd651e923cac6020de49a096e1d7e9b5f949f884`, tree
`e01dc798d1ba119357cc41e96802ac9aca83b9bc`, and these source leaves:

| path | Git blob | bytes | SHA-256 |
| --- | --- | ---: | --- |
| `skrf/network.py` | `be5a55e367628b888a39376b693e7a5368df45a9` | 291611 | `62d5bd5434eb4f2bb6fef2262dd02fac828f93b9742f7c900920fbf313c8b759` |
| `skrf/mathFunctions.py` | `ad356cd00d90799ed483d4efeff83bcffeb3674f` | 32637 | `7ff864b104b672ddcbd06b5fe7c6d6806040827b2d156732948d58a671010462` |
| `skrf/constants.py` | `2064f8b734e449f214c63f7977d83031483c10ff` | 5529 | `be3da422ceefb438b335f0e8dc0b8789a63bf2c6da2eec9ed7adbd52d7acfdf5` |

## Finding

The local Git repositories searched were the SIPI candidate checkout and the
Agent-Spice checkout, together with the bounded local scratch/cache roots.
Neither repository contains the pinned commit or tree, and no refs, reflog,
or all-object tree entry provides complete scikit-rf Git custody.

An extracted scikit-rf 2.0.1 package was found at:

`C:/Users/z3312/code/agent-spice/.venv/Lib/site-packages`

The same source leaves were also present in the uv extracted archive at:

`C:/Users/z3312/AppData/Local/uv/cache/archive-v0/RbEeYeYmc0aNFrF-`

A second uv environment extraction was found at
`C:/Users/z3312/AppData/Local/uv/cache/archive-v0/YCma8cEclmVLQlzQ/Lib/site-packages`.
All three extracted trees had the same result; the duplicate trees are not
treated as independent Git provenance.

For all three trees, the three file sizes, SHA-256 values, and calculated Git blob
SHA-1 values match the pinned source map. The package metadata identifies
`scikit-rf` version `2.0.1`, and the uv cache records a wheel URL/cache entry
for `scikit_rf-2.0.1-py3-none-any.whl`. The wheel archive bytes themselves are
not materialized as a local `.whl` file in the searched cache.

This is a **partial wheel/source-leaf match**, not complete Git custody. The
matching files can support a scoped offline source-leaf observation, but they
cannot serve as an immutable Git-pinned oracle. The exact commit/tree and
full dependency/toolchain provenance remain absent, and this audit does not
claim that the installed distribution is executable under the current Python
runtime. The AS-03 numeric parity
and native fit acceptance status therefore remain unchanged and blocked.

The bounded run wrote 11,273 bytes to
`C:/Users/z3312/AppData/Local/Temp/as03-skrf-custody-recovery-20260902.json`;
its SHA-256 is
`8aa8ad2a19576ce6ebcd4c92f268560d3f182c28bff7ff6456eb3b37c00bca91`.
The uv HTTP cache metadata file was 632 bytes with SHA-256
`cf9ed0260b01a371471a94598760d5ed5d6e41dc676f5eda4cdcc44706377352` and
advertised wheel SHA-256
`aa483acc54a4ba2b9dd59bcb1b49ccd1b7011b1ad625237a38ef35bb2eab1c90`.
That advertised archive digest is metadata only: no local wheel archive bytes
were found, so it is not used as Git or source custody.

## Reproduction

```powershell
python tools/audit_as03_skrf_custody_recovery.py `
  --scan-root C:/Users/z3312/code/SIPI-sim-agent `
  --scan-root C:/Users/z3312/code/agent-spice `
  --scan-root C:/Users/z3312/AppData/Local/uv/cache `
  --json-out C:/Users/z3312/AppData/Local/Temp/as03-skrf-custody-recovery-20260902.json
```

The command is expected to exit with status 1 while the pinned Git custody is
missing. The JSON result is intentionally kept in Temp rather than committed
as a source archive. The focused test suite is:

```powershell
python -m unittest tools.test_audit_as03_skrf_custody_recovery
```

The tests cover exact Git commit/tree detection, extracted-wheel source-leaf
matching, RECORD digest drift, wheel/cache inventory, and all-object blob
presence. They do not claim numeric parity or release readiness.
