//! R480 network-ingest pipeline: touchstone four-port -> file-to-internal
//! port reorder -> mixed-mode transform -> sdd21.
//!
//! The file port order is TX+, RX+, TX-, RX- (observed manifest fact and
//! the sipi-channel FourPortS convention); the COM internal order is
//! TX+, TX-, RX+, RX-, so the permutation is [1,3,2,4] (config sheet
//! Port Order). This pipeline performs the standard linear steps only.

use crate::mixed_mode_v1::{FourPortSMatrixV1, sdd21_v1};

/// File-to-internal port permutation: file ports (TX+,RX+,TX-,RX-) map
/// internal ports (TX+,TX-,RX+,RX-) via indices [0,2,1,3].
pub const FILE_TO_INTERNAL_ORDER_V1: [usize; 4] = [0, 2, 1, 3];

/// Apply the file-to-internal port permutation to a single-ended 4x4
/// matrix: `result[i][j] = s[file_of(i)][file_of(j)]`.
pub fn apply_internal_port_order_v1(s: &FourPortSMatrixV1) -> FourPortSMatrixV1 {
    let mut result = [[crate::mixed_mode_v1::com_t_v1()[0][0]; 4]; 4];
    // com_t_v1()[0][0] is a valid finite Complex64 placeholder; overwritten below.
    for row in 0..4 {
        for column in 0..4 {
            result[row][column] = s[FILE_TO_INTERNAL_ORDER_V1[row]][FILE_TO_INTERNAL_ORDER_V1[column]];
        }
    }
    result
}

/// One ingested sdd21 sample at a frequency.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Sdd21SampleV1 {
    frequency_hz: f64,
    sdd21: sipi_types::Complex64,
}

impl Sdd21SampleV1 {
    pub const fn frequency_hz(self) -> f64 {
        self.frequency_hz
    }

    pub const fn sdd21(self) -> sipi_types::Complex64 {
        self.sdd21
    }
}

/// Ingest one four-port row into its differential sdd21 value.
pub fn ingest_row_v1(matrix: &FourPortSMatrixV1) -> sipi_types::Complex64 {
    sdd21_v1(&apply_internal_port_order_v1(matrix))
}

/// Explicit scope policy of the ingest pipeline.
pub const INGEST_POLICY_V1: &str =
    "sipi.p5-04b.network-ingest-v1.read-reorder-transform";

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_types::Complex64;

    fn cm(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("complex")
    }

    #[test]
    fn reorder_maps_file_to_internal() {
        // Diagonal marker matrix in file order: s[i][i] = 1+i.
        let mut s = [[cm(0.0, 0.0); 4]; 4];
        for index in 0..4 {
            s[index][index] = cm(1.0, index as f64);
        }
        let reordered = apply_internal_port_order_v1(&s);
        // internal 1 (TX-) maps to file 3 (index 2).
        assert_eq!(reordered[1][1], cm(1.0, 2.0));
        // internal 2 (RX+) maps to file 2 (index 1).
        assert_eq!(reordered[2][2], cm(1.0, 1.0));
    }

    #[test]
    fn differential_file_path_yields_unit_sdd21() {
        // File ports: 1=TX+, 2=RX+, 3=TX-, 4=RX-.
        // Path RX+<-TX+ (file 2<-1) and RX-<-TX- (file 4<-3) with gain 1.
        let mut s = [[cm(0.0, 0.0); 4]; 4];
        s[1][0] = cm(1.0, 0.0);
        s[3][2] = cm(1.0, 0.0);
        let sdd21 = ingest_row_v1(&s);
        assert!((sdd21.real() - 1.0).abs() < 1e-12, "sdd21 real {:?}", sdd21.real());
        assert!(sdd21.imaginary().abs() < 1e-12);
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            INGEST_POLICY_V1,
            "sipi.p5-04b.network-ingest-v1.read-reorder-transform",
        );
    }
}
