use std::collections::HashMap;

use faer::prelude::Solve;
use faer::sparse::linalg::solvers::{Lu, SymbolicLu};
use faer::sparse::{SparseColMat, Triplet};
use faer::{Mat, c64};

use crate::error::{Error, Result};

#[derive(Default)]
pub struct SymbolicCache {
    symbolic: Option<SymbolicLu<usize>>,
    real_constant_factor: Option<Lu<usize, f64>>,
    complex_matrix: Option<SparseColMat<usize, c64>>,
    complex_entry_slots: Vec<usize>,
    real_factors: Vec<RealFactor>,
    real_value_scratch: Vec<u64>,
}

struct RealFactor {
    values: Vec<u64>,
    factor: Lu<usize, f64>,
}

impl SymbolicCache {
    pub fn has_real_constant_factor(&self) -> bool {
        self.real_constant_factor.is_some()
    }

    pub fn solve_real(
        &mut self,
        n: usize,
        entries: &[Triplet<usize, usize, f64>],
        rhs: &[f64],
    ) -> Result<(Vec<f64>, bool, bool)> {
        self.real_value_scratch.clear();
        self.real_value_scratch
            .extend(entries.iter().map(|entry| entry.val.to_bits()));
        if let Some(index) = self
            .real_factors
            .iter()
            .position(|cached| cached.values == self.real_value_scratch)
        {
            let cached = self.real_factors.remove(index);
            let solution = solve_factor(&cached.factor, n, rhs);
            self.real_factors.push(cached);
            return Ok((solution, false, false));
        }
        let matrix = SparseColMat::<usize, f64>::try_new_from_triplets(n, n, entries)
            .map_err(|error| Error::Sparse(error.to_string()))?;
        let created_symbolic = self.symbolic.is_none();
        let symbolic = match &self.symbolic {
            Some(symbolic) => symbolic.clone(),
            None => {
                let symbolic = SymbolicLu::try_new(matrix.symbolic())
                    .map_err(|error| Error::Sparse(error.to_string()))?;
                self.symbolic = Some(symbolic.clone());
                symbolic
            }
        };
        let factor = Lu::try_new_with_symbolic(symbolic, matrix.as_ref())
            .map_err(|error| Error::Sparse(error.to_string()))?;
        let solution = solve_factor(&factor, n, rhs);
        let factor_capacity = if n <= 512 {
            32
        } else if n <= 2_048 {
            16
        } else {
            8
        };
        if self.real_factors.len() >= factor_capacity {
            self.real_factors.remove(0);
        }
        self.real_factors.push(RealFactor {
            values: self.real_value_scratch.clone(),
            factor,
        });
        Ok((solution, created_symbolic, true))
    }

    pub fn solve_complex(
        &mut self,
        n: usize,
        entries: &[Triplet<usize, usize, c64>],
        rhs: &[c64],
    ) -> Result<(Vec<c64>, bool)> {
        if let Some(matrix) = self.complex_matrix.as_mut() {
            if entries.len() != self.complex_entry_slots.len() {
                return Err(Error::Sparse(
                    "complex matrix stamp structure changed".into(),
                ));
            }
            let values = matrix.val_mut();
            values.fill(c64::new(0.0, 0.0));
            for (entry, slot) in entries.iter().zip(&self.complex_entry_slots) {
                values[*slot] += entry.val;
            }
        } else {
            let matrix = SparseColMat::<usize, c64>::try_new_from_triplets(n, n, entries)
                .map_err(|error| Error::Sparse(error.to_string()))?;
            let coordinate_slots: HashMap<(usize, usize), usize> = matrix
                .as_ref()
                .triplet_iter()
                .enumerate()
                .map(|(index, entry)| ((entry.row, entry.col), index))
                .collect();
            self.complex_entry_slots = entries
                .iter()
                .map(|entry| {
                    coordinate_slots
                        .get(&(entry.row, entry.col))
                        .copied()
                        .expect("triplet coordinate exists in compressed matrix")
                })
                .collect();
            self.complex_matrix = Some(matrix);
        }
        let matrix = self
            .complex_matrix
            .as_ref()
            .expect("complex matrix cache was initialized");
        let created_symbolic = self.symbolic.is_none();
        let symbolic = match &self.symbolic {
            Some(symbolic) => symbolic.clone(),
            None => {
                let symbolic = SymbolicLu::try_new(matrix.symbolic())
                    .map_err(|error| Error::Sparse(error.to_string()))?;
                self.symbolic = Some(symbolic.clone());
                symbolic
            }
        };
        let factor = Lu::try_new_with_symbolic(symbolic, matrix.as_ref())
            .map_err(|error| Error::Sparse(error.to_string()))?;
        Ok((solve_factor(&factor, n, rhs), created_symbolic))
    }

    pub fn solve_real_constant(
        &mut self,
        n: usize,
        entries: &[Triplet<usize, usize, f64>],
        rhs: &[f64],
    ) -> Result<(Vec<f64>, bool, bool)> {
        if let Some(factor) = &self.real_constant_factor {
            return Ok((solve_factor(factor, n, rhs), false, false));
        }
        let matrix = SparseColMat::<usize, f64>::try_new_from_triplets(n, n, entries)
            .map_err(|error| Error::Sparse(error.to_string()))?;
        let created_symbolic = self.symbolic.is_none();
        let symbolic = match &self.symbolic {
            Some(symbolic) => symbolic.clone(),
            None => {
                let symbolic = SymbolicLu::try_new(matrix.symbolic())
                    .map_err(|error| Error::Sparse(error.to_string()))?;
                self.symbolic = Some(symbolic.clone());
                symbolic
            }
        };
        let factor = Lu::try_new_with_symbolic(symbolic, matrix.as_ref())
            .map_err(|error| Error::Sparse(error.to_string()))?;
        let solution = solve_factor(&factor, n, rhs);
        self.real_constant_factor = Some(factor);
        Ok((solution, created_symbolic, true))
    }
}

fn solve_factor<T>(factor: &Lu<usize, T>, n: usize, rhs: &[T]) -> Vec<T>
where
    T: faer::traits::ComplexField,
{
    let rhs = Mat::from_fn(n, 1, |row, _| rhs[row].clone());
    let solution = factor.solve(&rhs);
    (0..n).map(|row| solution[(row, 0)].clone()).collect()
}
