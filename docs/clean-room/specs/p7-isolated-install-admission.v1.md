# P7 Isolated Install Admission v1

## Scope

This Windows-only harness re-admits an external P7-03a ZIP and writes its two
allowed files into a new external installation prefix. It then launches the
installed `sipi.exe` directly from that prefix. The environment class is
explicitly `same_host_isolated_prefix`.

## Required Behavior

The archive, composition report, archive policy, and prior archive report are
all explicit external inputs. The harness repeats archive admission, requires
the prior report to bind exactly to the same archive, policy, composition, and
entry identities, and streams only `sipi.exe` and `LICENSE` to a new prefix.
It rehashes the installed executable before execution.

The child starts with only the minimal Windows loader environment plus a
prefix-local TEMP/TMP. Python, Conda, Cargo, Rustup, MATLAB, legacy-engine,
workspace, and caller PATH state are not inherited. It directly runs product
discovery, the fixed TRAN artifact path, verified artifact reporting, and a
recognized unavailable Channel route. Process outputs must follow the existing
single-JSON/NDJSON protocol contract.

The report records only identities, probe output digests, and fixed limitation
states. It sets `fresh_machine: false`, `fresh_user: not_assessed`,
`host_loader_closure: not_assessed`, and `promotion_status: blocked`.

## Non-Claims

This is not a fresh Windows image, fresh-user, installer, signature, system
DLL/driver, registry, VC-runtime, dynamic-loader-closure, or release approval
test. It does not certify all profiles or replace P7-04's final fresh-machine
or VM evidence requirement.
