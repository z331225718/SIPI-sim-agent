# P3C External ADS Reference Metric Binding v1

Each external run independently materializes the selected S4P candidate, reads
the exact hash-bound ADS canonical triple payload, extracts only its RX
differential column, seals separate reference and candidate waveform artifacts,
and invokes the existing PRBS9 metric CLI without alignment or transforms.

Reports retain only artifact identities, payload hashes, and CLI metric JSON.
They retain no paths, S4P/ADS bytes, or waveform arrays. This observes a
provenance-bound metric evaluation only; it cannot promote receiver, physical
causality, AMI/P5, or release gates.
