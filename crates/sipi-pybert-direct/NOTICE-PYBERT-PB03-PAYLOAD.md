PB-03 payload projection notice

The PB-03 files in this crate are a SIPI-owned Rust implementation of a
narrow, mechanical result projection. They do not include copied PyBERT
source code, generated Python artifacts, or a Python runtime dependency.

The semantic reference is the pinned PyBERT repository revision recorded in
SOURCE-MAP-PB03-PAYLOAD.md. Any upstream license obligations remain governed
by the repository's existing NOTICE-PYBERT-LICENSE-BOUNDARY.md and source-map
review. This notice does not relicense upstream code or grant permission to
use external AMI, IBIS, DLL, GetWave, or vendor assets.

This slice makes no claim of whole-payload parity, complete PyBERT feature
coverage, exact class-pickle compatibility, product capability, or release
approval. Remaining eye, contour, external-model, and vendor branches are
explicitly blocked until their owners provide the missing typed contracts and
source evidence.

The contour follow-up only passes PyBERT's existing three statistical BER
levels into the crate's existing typed contour operation. It does not recreate
the pinned 2-D eye extraction/resampling algorithm. The ten eye/native-eye
matrices remain blocked, and seven response magnitudes remain recorded as
pre-serialization telemetry drift rather than being numerically adjusted.
