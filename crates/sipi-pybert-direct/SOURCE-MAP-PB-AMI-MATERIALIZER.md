# PB AMI Materializer Slice

This additive source map covers only the bounded `example_rx.ami` checkpoint;
it does not revise the historical PB external-host source map. Pinned upstream
is commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`.

## Exact Checkpoint

The declaration is `models/ibisami/example_rx.ami`, Git blob
`26a1b03849a0838284dfde7921926668ad1434e0`, 3932 bytes, raw SHA-256
`6d4038a184cb10af355dbd02b9392258d7e2b3bb9b0cddc211349db66ef80c38`.
The archived extracted bytes are 3932 bytes with SHA-256
`876c9653d2d038781ece3167646c642623cfa49f8a0aa32edd1f3b10eff21904`.
The Rust fixture `tests/fixtures/example_rx.ami` is 3373 bytes with SHA-256
`5c0c971be411a9af2a9e1cfdf2222086bf9d0c82946ed740c91b364f1d43113d`; its
Rust test locks the complete serialized checkpoint rather than a substring.

The external oracle creates a clean archive SHA-256
`ee8ff82477f38e5d119d4c6e037b34243fae7ef942e5ed46f13e6b80843a839b` of
3041280 bytes, invokes the pinned `AMIParamConfigurator` through its official
Traits setter (`ctle_mode="Manual"`, yielding the typed value `1`), then calls
the pinned `_ads_style_ami_init_parameters` and real `AMIModel.initialize`.
The Rust test uses the same `ctle_mode 1` runtime selection and asserts the
complete exact byte string:

`(example_rx (AMI_Version "5.1")(Init_Returns_Impulse True)(GetWave_Exists True)(ctle_mode 1)(ctle_freq 5000000000.0)(ctle_mag 0.0)(ctle_bandwidth 12000000000.0)(ctle_dcgain 0.0)(dfe_mode 0)(dfe_ntaps 5)(dfe_tap1 0.0)(dfe_tap2 0.0)(dfe_tap3 0.0)(dfe_tap4 0.0)(dfe_tap5 0.0)(dfe_vout 1.0)(dfe_gain 0.1)(debug (dbg_enable False) (dump_dfe_adaptation False) (dump_adaptation_input False)))`

## Bounded Rust Scope

Rust accepts only this structural profile: direct `Reserved_Parameters` Info
controls, direct `Model_Specific` Input/InOut leaves, nested model containers,
`Description`/`List_Tip` metadata, and fixed `Value`, `Default`, `Range`,
`List`, and `Corner` forms. Integer values are lexical checked `i64`; this is
an intentional safety restriction and not a generic claim about all PyAMI
numeric coercions. Unknown or nested Reserved typed nodes, duplicate tags,
arbitrary runtime paths, overflow, malformed metadata, and missing/false
controls fail closed. Vendor DLL execution and PyAMI execution remain external;
the Rust production binary does not execute PyAMI. The Python oracle alone
executes clean archived PyAMI and is not distributed as a Rust implementation.

## Bound Sources

| Source | Git blob | Raw SHA-256 | Role |
| --- | --- | --- | --- |
| `PyAMI/src/pyibisami/ami/parser.py` | `23389fa558291ef2a06dff1c7cb5ebcaa864a0a4` | `7ab52c1e03893cdd496a4db7672b3213a0d1eec5d2b746a98e9011aa03bf3a7c` | external parser/configurator |
| `PyAMI/src/pyibisami/ami/parameter.py` | `201ed14ef561392d46f385d80e0d3954b0dc67d8` | `95bc003de3a5abd73bfa32f4b5a1db1c0c7d511c5f8cea11d92a967e54c76908` | external typed semantics |
| `PyAMI/src/pyibisami/ami/model.py` | `4cfa4ec87aed1f5caece871271aa3a587bcae21f` | `bf24cff1140e83ec46a8a6c9a5482151cffa90d516dfa056f639893b280e3787` | external serializer/initialize |
| `src/pybert/utility/ibisami.py` | `9f1fb3b1496fd192b77207ffcecc4b2478d5f64e` | `14e1ac37c9673c21bc3bb6c75cf67d1483f658fb6d668b9dd1066693c6613c79` | external parameter projection |

