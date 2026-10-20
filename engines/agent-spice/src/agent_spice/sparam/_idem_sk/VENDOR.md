# Vendored third-party snapshot: `idem_replica` pole-discovery core

| item | value |
|---|---|
| Upstream project | `idem_replica` — a from-scratch replica of the CST IdEM frequency-domain vector-fitting engine (clean-room, MIT) |
| Upstream location on the author machine | `C:\Users\z3312\code\idem_research\idem_replica` |
| Upstream git commit | `28b76dc` (`idem_research` repository) |
| Upstream version | `0.1.0` |
| Licence | MIT, Copyright (c) 2026 z331225718 — full text in `LICENSE` |
| Files copied | `core/rational_model.py`, `core/vector_fitting.py`, `core/adaptive.py`, `core/passivity.py` (verbatim, SHA-256 verified at copy time) |
| Our usage | pole discovery (Sanathanan–Koerner relocation + adaptive Adding/Skimming search) and the fast Hildreth-QP residue-perturbation passivity enforcement used only by the merged adaptive mode. Residues, DC handling, reports and delivered artifacts are ours; the authoritative post-enforcement passivity audit always remains the native Hamiltonian check. |
| Default participation | none. Only reachable through `fit-sparam --search-mode adaptive` / `agent_spice.sparam.adaptive_search`. |

## Why it is vendored instead of reimplemented

The mechanism this merge buys — a shared-sigma Sanathanan–Koerner relocation
with one batched QR per weight group plus a cumulative Adding/Skimming order
search — is precisely the part where the existing native engine is weakest
(our own retrospective records order/time ratios of 1.30/1.67/2.25 and
4.22/2.88/3.29 against IdEM on the large-port corpus).  Vendoring the upstream
files verbatim keeps the behaviour identical to the measured research artifact
and keeps our normal default path byte-for-byte untouched.  A future change
that promotes this backend to the default path should re-implement it as a
native module with our own tests and drop this snapshot.

## Maintenance rules

1. Do not edit the four vendored `.py` files in place (their SHA-256 must stay
   equal to upstream commit `28b76dc`; `VENDOR.md` and `LICENSE` are ours). If
   upstream changes are wanted, copy a new pinned snapshot and update this table.
2. Do not import this subpackage from `native_vf.py`, `pole_relocation.py`,
   `target_fit.py` or any default `fit-sparam` path.
3. Keep `LICENSE` in this directory and ship it with the package (MIT requires
   the notice in distributions). `pyproject.toml` / `setup.py` list
   `sparam/_idem_sk/LICENSE` and `sparam/_idem_sk/VENDOR.md` in `package-data`
   so both land in the wheel.
