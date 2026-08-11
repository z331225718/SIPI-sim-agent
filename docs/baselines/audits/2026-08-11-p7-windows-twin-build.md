# P7-01a Windows Twin Build Gate

This slice adds a Windows x86_64 external twin-build verifier. It materializes
two clean source copies from the same pinned Git object, builds the CLI with
`--release --locked --offline` into independent target directories, and accepts
only exact executable size and SHA-256 identity. Reports deliberately exclude
absolute paths, source bytes, executable bytes, and command output.

The fixed `/Brepro` MSVC linker argument is part of the gate environment and
is hashed in the report. It removes linker timestamp drift while preserving the
same pinned source, lockfile, toolchain, target, and Cargo build command.

An external run over commit `127552e7cfa68039d6157073649977e031d522ce`
reported `identical`: both archives produced a 691712-byte `sipi.exe` with
SHA-256 `cf36303e8997124c8bc1f9d53ea410eb09a6b17431453ef1dd2fb0cca73adfd8`.
The report, archive copies, target directories, and executable remained outside
the worktree. The pre-existing dirty `uv.lock` was not an input because the
gate materializes `git archive HEAD`.

One Orca reviewer audited the final staged gate. The reviewer found and the
slice corrected a report-path overwrite/write-inside-worktree defect; the
final re-audit reported `0 P1 / 0 P2`. Invalid or existing report paths now
produce only a static stderr rejection, while a valid external report is
created exclusively.

The gate is intentionally narrower than release certification. It does not
produce an archive, SBOM, NOTICE, PE closure, signature, fresh-machine proof,
or domain/profile claim. P3C-01 remains blocked because the required profiles
do not supply accepted eye/jitter/bathtub semantics or a usable receiver stage.
