# COM ERL exact-profile replay v3 linker prep

Status: preparation only; no formal replay or numeric parity claim was generated.

The frozen clean-archive runner now resolves an explicit linker when `--linker` is omitted by probing the supplied `rustc --print sysroot` and selecting the pinned `x86_64-pc-windows-msvc` `rust-lld.exe`. The build environment sets `CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER` to that resolved file and keeps `RUSTC`, offline, locked, incremental, and wrapper controls explicit.

`rust-lld --version` is a documented generic-driver probe on this host and exits 1. The immutable linker identity records role, basename, file SHA256, version-output SHA256, exit code, path redaction, timeout, and the exact admission strategy. Any other nonzero result, timeout, missing file, or hash drift is fail-closed.

The manifest, verifier, and aggregator bind the linker role and resolution contract. The native environment now resolves and binds MSVC 14.44.35207, Windows SDK 10.0.26100.0, explicit x64 include/lib ordering, complete `.lib` inventories, and key-library hashes; inherited `LIB`/`INCLUDE` are not admitted. Focused mutation coverage rejects a missing linker, arbitrary linker override, non-admitted probes, and native-control drift. A clean candidate archive release build completed with this explicit environment (`exit=0`, 4m51s). Formal two-run evidence remains blocked until the successor harness commit contains these prep changes and is executed from a clean archive.
