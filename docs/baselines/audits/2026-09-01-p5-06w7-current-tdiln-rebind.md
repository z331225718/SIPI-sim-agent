# P5-06w7 Current TDILN Rebind

The normal-TDR zero-reflection correction changed production COM code after the previous TDILN array acceptance. This record therefore replays the complete original-13 TDILN diagnostic matrix twice against the same immutable `b9b195a1` archive used by the current public-root scalar acceptance.

Each replay uses the pinned Agent-COM archive and MATLAB R2024b source-core harness. The diagnostic binary supplies only named TDILN sidecars; the separately built default production binary supplies the performance measurement. Every named vector passes without S-parameter fitting. Rust semantic output repeats exactly, and the hard per-workbook and total speed gates pass: MATLAB best total is 1758.8355904 seconds, Rust worst total is 190.41138859995408 seconds, for a 9.237029377981356x floor.

This is a named TDILN intermediate checkpoint. It does not accept a full result graph, a complete warning catalog, public diagnostic sidecar wire, IEEE certification, or release.
