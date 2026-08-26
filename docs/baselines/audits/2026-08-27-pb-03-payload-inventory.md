# PB-03 sim-rust payload integrity audit

This record binds a caller-recorded member observation. It is not execution
provenance, replay custody, an oracle attestation, whole-payload parity, or a
release result.

Candidate authority is commit `7859a72e00a7a2f4c7699f935e1cee98a3f0c1e6`,
tree `356cc526062817d28a8edd22f5c4325ce0a75ee0`. The Git archive receipt is
statically recomputed from that object. The NPZ and per-member receipts are
caller-recorded integrity observations; this gate does not bind the runner,
toolchain, output directory, or reconstruction procedure that produced them.

The member graph records candidate 140, oracle 150, 127 exact, 11 shared hash
drift, 2 candidate-only, and 12 oracle-only. Removing the 27 members whose
producer is `pb03_serializer_projection` mechanically derives the before graph:
candidate 113, oracle 150, 107 exact, 4 shared drift, 2 candidate-only, and 39
oracle-only.

Seven response members are only logical f64 hash drift. Their source, dtype,
shape, count, and order must match across candidate and oracle. No ULP bound is
claimed. Eye, contour, AMI, IBIS, DLL, GetWave, vendor-noise, class-pickle,
product, global-closure, and release claims remain blocked.

The Git gate binds the full gate commit/tree and the verifier/test blobs. The
record HEAD must be its strict descendant, while candidate `7859a72e` must be
the gate ancestor. This is an integrity gate, not a signature or provenance
claim.

member_map_sha256: 017e6066445c97151d2fe62c6d3e5255bba071c75837754fed84e81e79eae038
verifier_sha256: 9b193af27d525d9d8f4315a1a2a9b522f8d9b5bca97a510a2906f07bc1584681
mutation_test_sha256: 6bd84738e1757c047e64a7baeb2ab3c7fec8ce04c7997ee7ccd4a446424d823c
source_map_sha256: 19b2546170d8a771d6b5b06c8115fbae3094f34a27e9284017a360d171596c88
notice_sha256: cc193bce808949987fa5764bbb5e3539f304816e2f9bbb425bf712c558ea6938
