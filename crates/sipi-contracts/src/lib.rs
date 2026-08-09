#![forbid(unsafe_code)]

//! P1 foundation constants. Versioned request and result types arrive in P1-03.

/// Stable envelope identifier for the P1 capability response.
pub const CAPABILITIES_SCHEMA: &str = "sipi.capabilities.v1";

/// Domains planned by the product specification. None are implemented in P1-01.
pub const PLANNED_DOMAINS: [&str; 4] = ["tran", "channel", "ibis-ami", "com"];
