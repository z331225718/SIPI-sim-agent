//! # agent-spice-sim
//!
//! Project-owned sparse PI/SI circuit simulator library.
//!
//! ## Circuit API version
//! [`CIRCUIT_API_VERSION = 1`], [`RESULT_SCHEMA = "agent-spice.simulation-result.v1"`].
//!
//! ## Units (SI, no newtype wrappers)
//! time s · frequency Hz · angular frequency rad/s · voltage V · current A ·
//! resistance Ω · capacitance F · inductance H · admittance S · complex
//! frequency `s` = j·2π·f [rad/s]. `SimulationPoint::x` depends on `analysis`:
//! - `"op"` → 0.0 (dimensionless placeholder)
//! - `"dc"` → sweep source value (V or A, depending on the bound source)
//! - `"ac"` → frequency [Hz]
//! - `"tran"` → time [s]
//!
//! `SimulationPoint::values` keys: node name → node voltage [V]; voltage source name → branch current [A].
//!
//! ## Port indexing
//! Library-internal is 0-based: `rfm::RfmModel::{impedance_response,
//! loaded_impedance_response}`, `response::ResponseLoads::shorted_ports`,
//! `response::RcShunt::port`. The CLI is 1-based; the binary's
//! `parse_ports`/`checked_port` perform the ±1 conversion and the
//! `rfm-response.v1` metadata writes 1-based.
//!
//! ## Process-global state (caller contract)
//! 1. **Working directory**: before calling `netlist::Deck::parse_file` or
//!    `simulator::export_lin_touchstone`, the caller MUST set the process cwd
//!    to the deck directory. `.lin FILENAME=` relative paths resolve via
//!    `std::env::current_dir()`; `PWL PWLFILE=` and `.include` use the deck's
//!    explicit `root_directory`. This library does NOT call `set_current_dir`
//!    itself; it does not support running multiple decks concurrently in one
//!    process — use subprocess isolation.
//! 2. **Logging**: `logging` is a process-global `OnceLock` singleton. If
//!    `logging::initialize` is never called, `logging::line` is a silent
//!    no-op. `initialize` succeeds only once per process.
//!
//! ## Panic / Error contract
//! `Result`-returning (recoverable): deck parsing, parameter evaluation,
//! file reads, sparse LU failures, semantic validation. panic (unrecoverable,
//! API misuse): RFM state-machine preconditions not met and parser internal
//! invariants. `[profile.release] panic = "abort"` means release builds
//! cannot `catch_unwind`; in-process embedding with fault tolerance requires
//! changing the profile (a behavioral change, not covered by this API
//! version).

pub const RESULT_SCHEMA: &str = "agent-spice.simulation-result.v1";
pub const CIRCUIT_API_VERSION: u32 = 1;

pub mod compatibility;
pub mod error;
pub mod logging;
pub mod netlist;
pub mod response;
pub mod result;
pub mod rfm;
pub mod simulator;

mod expression;
mod sparse;
