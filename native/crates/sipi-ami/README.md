# SIPI AMI

`sipi-ami` is the project-owned, clean-room Rust foundation for the IBIS/AMI
work in M5A-09. It is authored from public IBIS/AMI specifications; it does
not import, execute, translate, or inherit code from PyAMI or PyBERT.

The initial slice implements only a strict IBIS keyword/record scanner. It
requires `[IBIS Ver]` as the first keyword and preserves keyword values, data
records, and physical source lines for the later semantic layers. It is not a
claim of complete IBIS or AMI specification coverage, nor a vendor DLL or
cross-platform certification claim.
