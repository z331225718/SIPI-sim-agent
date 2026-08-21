# P4B-02 production parameter adapter selection

The selected ADS TX/RX `.ami` profiles now have a narrow typed production
adapter. `sipi-ami-worker::prepare_forwarded_parameter_subset_v1` parses the
exact bytes, builds a canonical declaration tree, and checks caller-supplied
typed selections. `sipi-ami-host::AmiHostV1::initialize_forwarded_subset`
rechecks the source/tree/subset identity before forwarding unchanged raw text
to the existing AMI initialization sink.

The decision is `external_asset_oracle`, limited to hash-bound host-forwarded
subset identity. The independent hash-only observation records two fresh reads
of each external text asset, eight selected TX values and thirty selected RX
values, and no DLL load or AMI entry-point invocation. The adapter rejects
usage, type, format, finite range, source identity, and canonical digest drift;
it never resolves a declaration default or auto-tunes a missing value.

This does not promote any of the 193 feature-quarantined helper modules. The
selection charter remains authoritative at 0 `keep_for_product`, 34
`quarantine_pending_requirement`, and 159 `delete_candidate` modules. The
159 delete candidates remain a separate deletion batch and no bulk deletion is
performed here. Vendor rights, dynamic dependency closure, isolated runtime
execution, DLL-internal consumption, and waveform parity remain blocked.
