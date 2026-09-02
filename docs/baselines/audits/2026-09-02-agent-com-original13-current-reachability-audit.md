# Agent-COM Original-13 Current Reachability Audit

Date: 2026-09-02

## Scope and source identity

This is a read-only runtime observation of the current product candidate. It
does not alter production code, PLAN, or the ledger and is not an acceptance
record.

The authoritative upstream source is Agent-COM commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`. The source entry point is
`matlab_src/com_ieee8023_480.m` (Git blob
`2e226d785c1ed2403f6d0a11288bf75939021814`). Its clean file identity is
469713 bytes and raw SHA-256
`642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad`.
The established normalized-MATLAB-text identity is 458971 bytes and SHA-256
`88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596`;
these are distinct, intentional raw versus normalized receipts.

The source MATLAB path is operational through the upstream wrappers
`tools/matlab_oracle/run_com_oracle.m` and
`tools/matlab_oracle/com_oracle_case_metrics.m`. A R2026a MATLAB Engine TP0V
diagnostic exists outside the repository, but it binds older candidate
`4477f8dff7ff2556690d62b3b743c0d4f47a8cba`; it is useful feasibility
evidence only.

## Current executable observation

At product HEAD `a8d7322d4e81849bd918c8db7d1ae78f0db96781`, a release build
of the direct crate was made in a temporary target directory. Each original-13
workbook passed both `config validate` and the direct public workflow
`load_config -> run_com -> write_artifacts`. TP0V additionally passed the
current root route `sipi com run` and published `result.json`, `report.html`,
and `diagnostics.json`.

| Index | Upstream workbook | Cases | Current Rust workflow |
| --- | --- | ---: | --- |
| 0 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA _TP0V_08_17_2022.xlsx` | 2 | reached |
| 1 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx` | 2 | reached |
| 2 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx` | 2 | reached |
| 3 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120G_ERL_HOST_10_26_2022.xlsx` | 1 | reached |
| 4 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120G_ERL_MODULE_10_26_2022.xlsx` | 1 | reached |
| 5 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_162_ERL_HOST_10_26_2022 .xlsx` | 1 | reached |
| 6 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_CR_CA_08_17_2022.xlsx` | 2 | reached |
| 7 | `config_sheets_100G/config_com_ieee8023_93a=3ck_SA_KR_08_17_2022.xlsx` | 2 | reached |
| 8 | `Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_fr55_C2M_TP1a_11_2022.xlsx` | 3 | reached |
| 9 | `Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_C2C_11_2022.xlsx` | 3 | reached |
| 10 | `Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_C2M_TP1a_11_2022.xlsx` | 3 | reached |
| 11 | `Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_CAKR_11_2022.xlsx` | 3 | reached |
| 12 | `Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_Txpre_C2M_TP1a_11_2022.xlsx` | 3 | reached |

This covers 13 workbooks and 28 package cases. It exercises 100G NRZ,
normal finite ERL, ERL-only, CR/CA, KR, and 200G PAM4/raised-cosine workbook
branches. The 120F result also reports the existing non-MMSE search diagnostic
with TX taps, CTLE selection, DFE taps, and high-pass selection, so that path
is not merely a configuration acceptance.

## What this observation does and does not prove

The historical upstream `benchmarks/original-13/benchmark.json` records 13
MATLAB/Python-passing configurations, 28 cases, and 303 scalar checkpoints.
Against that historical scalar surface, the current probe produced no missing
or non-finite-sign mismatch; the largest per-workbook absolute finite delta
ranged from 0 to `4.519e-12`. This is a useful regression signal only: the
benchmark implementation is commit `3257c2be2d575da870ab603fb5c44ed547fec314`,
not the current Rust candidate.

More importantly, the channel byte identities differ across prior records:

| Record | THRU bytes / SHA-256 | Meaning |
| --- | --- | --- |
| Current local reachability probe | 6425196 / `b14a92e7f844608aaee5b4cbd3dfda08d7af48bfedb4526043a0733b8823e584` | locally registered current fixture |
| Historical original-13 benchmark | SHA-256 `8746c20685b1283cd0c294bdec85653ffb9a79731bb7131293d58c69c4c0b650` | historical benchmark asset |
| Prior formal root matrices | 6393177 / `fcbcce086dbae6bbb9a1f8ca5df775073ebb6303f80a9f062caf1f2ab5607361` | archived matrix asset |

Therefore the current observation is explicitly not a MATLAB parity claim.
It also cannot rebind prior formal records, which name historical candidates
and MATLAB R2024b. The current worktree was dirty during the probe, so it has
no candidate archive or tree receipt either.

The following remain candidate-only or deliberately bounded:

* MATLAB figures and report formatting: Rust emits a diagnostic fallback HTML
  report; it does not claim MATLAB figure or report equivalence.
* Complete MATLAB warning behavior: current Rust declares implemented
  source-mapped calls only; the normal TDR probe records a degraded
  `SIPI-COM-ANTI-CAUSAL-PHASE-SLOPE-BYPASSED` observation for the zero port.
* TD-ILN arrays and the full result graph: available sidecars are diagnostic
  and do not close a public-array or full-output contract.
* The process adapter is a real strict transport for upstream CLI/API, but it
  was not the executable observed in this audit. The observation above is the
  Rust replacement route.

## Narrowest real next step

Use workbook 0, TP0V, as the first current-candidate deep comparison. It is a
real upstream workbook with two package cases, finite normal ERL
(`17.310082883306528` in the prior MATLAB R2026a diagnostic), COM, search,
and crosstalk. It completes quickly enough for two independent MATLAB runs.
It is materially stronger than the ERL-only `+Inf` cases and much smaller than
the 120G C2M / full original-13 matrix.

Before running it, create a clean candidate archive and bind all of the
following in a new COM-only harness record:

1. Current candidate commit, tree, archive SHA-256, and build-binary receipt.
2. The upstream archive at the fixed commit/tree above, plus raw and normalized
   MATLAB source identities.
3. TP0V workbook bytes `67151` and SHA-256
   `54562fa2bbe856f1fb6e96b7c1c873d2b399555b1fb38e50cd6f4ad3ddc69f0a`.
4. One explicitly selected THRU/FEXT/NEXT triple from the same upstream
   archive. Do not mix the three historical fixture identities above.
5. MATLAB R2026a executable/version receipts, fresh preference directory,
   `MW_DISABLE_CONNECTOR=1`, and the Python engine receipt.
6. Scalar comparison plus the existing finite normal-ERL diagnostic sidecar
   vectors (`time_s`, `impedance_ohm`, `ptdr`, `gated`) for both ports.

The resulting record should remain diagnostic until the phase-slope/warning
observation is either matched to source behavior or explicitly excluded from
the selected comparison contract. No S-parameter fitting or new numerical
domain behavior is needed for this step.
