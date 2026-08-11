# P4A Input/TYP Static DC CLI v1

`sipi ibis dc-evaluate --stdin` accepts one JSON request with caller-provided
UTF-8 IBIS text, an explicit lexical IBIS version and model selector, the only
admitted corner `typical`, and independent ground and power clamp drive volts.

The service performs exactly this in-memory sequence: bounded structural parse,
typed semantic envelope, selected Input/TYP DC clamp decode, then in-domain
linear DC clamp evaluation. Both signed branch currents and their signed total
use amperes. `C_comp` is validated as a required selected-model declaration but
has exactly zero current in this static route.

Success returns text byte length and SHA-256, the caller selection, branch and
total currents, and `caller_input_unattested`. It never returns source text,
table rows, paths, files, URLs, external asset identities, or external oracle
results.

Unknown fields, non-UTF-8 encoding, non-Typical corner, invalid selection,
structural or semantic errors, non-Input models, missing or duplicate clamps,
Algorithmic Model attachment, non-finite values, and out-of-domain probes are
rejected. There is no fallback selector, PVT, extrapolation, C_comp transient,
V-T/ramp/package/pin/network/channel/AMI behavior, artifact publication, or
external profile acceptance claim.
