# SIPI AMI

`sipi-ami` is the project-owned, clean-room Rust foundation for the IBIS/AMI
work in M5A-09. It is authored from public IBIS/AMI specifications; it does
not import, execute, translate, or inherit code from PyAMI or PyBERT.

The current foundation implements a strict IBIS keyword/record scanner and a
small AMI S-expression parameter-tree reader. The IBIS scanner requires
`[IBIS Ver]` as the first keyword and preserves keyword values, data records,
and physical source lines. The AMI reader preserves named parameter metadata
and validates the host-facing `AMI_Version`, `Init_Returns_Impulse`, and
`GetWave_Exists` value types. It also defines an explicit, non-numerical
`AMI_Init` / `AMI_GetWave` waveform contract for a future DLL host. It is not a
claim of complete IBIS or AMI specification coverage, nor a vendor DLL or
cross-platform certification claim. The current host owns a Rust `libloading`
handle and the public `AMI_Init` / optional `AMI_GetWave` / `AMI_Close`
lifecycle, while keeping vendor memory and strings at the FFI boundary. It
bundles no vendor DLL and is not vendor or cross-platform certification.
