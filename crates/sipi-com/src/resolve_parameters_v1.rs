//! COM default-expression set resolver (P5-02l).
//!
//! Resolves a set of named default-rule expressions against a consumed
//! parameter surface, reusing resolve_default_value_v1 (P5-02j/k): each
//! consumed key with a default expression is resolved to a typed
//! ResolvedDefaultV1, and the result map can be merged into a typed COM
//! parameter DTO via merge_com_parameters_v1 (P5-05e). A consumed key
//! without either a workbook value or a resolvable default surfaces as a
//! missing-value error for the caller. Profile-agnostic.

use std::collections::HashMap;

use crate::value_consumption_v1::{resolve_default_value_v1, ResolvedDefaultV1};

/// Stable scope policy of the P5-02l default-set resolver.
pub const RESOLVE_PARAMETERS_POLICY_V1: &str = "sipi.p5-02l.resolve-parameters.v1.default-set";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ResolveParametersErrorV1 {
    MissingExpression(String),
    Unresolved { name: String, reason: String },
}

/// Resolves a set of default expressions to typed values.
///
/// `default_expressions` maps each consumed key to its default-rule
/// expression; `parameters`/`options` provide the consumed surface for
/// expression substitution. Returns a map of resolved defaults, or the
/// first unresolved expression as an error.
pub fn resolve_default_set_v1(
    default_expressions: &HashMap<String, String>,
    parameters: &HashMap<String, ResolvedDefaultV1>,
    options: &HashMap<String, ResolvedDefaultV1>,
) -> Result<HashMap<String, ResolvedDefaultV1>, ResolveParametersErrorV1> {
    let mut resolved = HashMap::new();
    for (name, expression) in default_expressions {
        match resolve_default_value_v1(expression, parameters, options) {
            Ok(value) => {
                resolved.insert(name.clone(), value);
            }
            Err(e) => {
                return Err(ResolveParametersErrorV1::Unresolved {
                    name: name.clone(),
                    reason: format!("{e:?}"),
                });
            }
        }
    }
    Ok(resolved)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scalars(values: &[(&str, f64)]) -> HashMap<String, ResolvedDefaultV1> {
        values.iter().map(|(k, v)| (k.to_string(), ResolvedDefaultV1::Scalar(*v))).collect()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(RESOLVE_PARAMETERS_POLICY_V1, "sipi.p5-02l.resolve-parameters.v1.default-set");
    }

    #[test]
    fn resolves_literal_and_derived() {
        let expressions = HashMap::from([
            ("a_fext".to_string(), "0.5".to_string()),
            ("ctle_fp1".to_string(), "param.fb/4".to_string()),
        ]);
        let params = scalars(&[("fb", 53.125e9)]);
        let resolved = resolve_default_set_v1(&expressions, &params, &HashMap::new()).expect("res");
        assert_eq!(resolved.get("a_fext"), Some(&ResolvedDefaultV1::Scalar(0.5)));
        assert_eq!(resolved.get("ctle_fp1"), Some(&ResolvedDefaultV1::Scalar(53.125e9 / 4.0)));
    }

    #[test]
    fn unresolved_expression_rejected() {
        let expressions = HashMap::from([
            ("missing".to_string(), "param.does_not_exist".to_string()),
        ]);
        let err = resolve_default_set_v1(&expressions, &HashMap::new(), &HashMap::new()).err().expect("err");
        assert!(matches!(err, ResolveParametersErrorV1::Unresolved { .. }));
    }

    #[test]
    fn empty_set_is_ok() {
        let resolved = resolve_default_set_v1(&HashMap::new(), &HashMap::new(), &HashMap::new()).expect("ok");
        assert!(resolved.is_empty());
    }

    #[test]
    fn vector_default_resolved() {
        let expressions = HashMap::from([
            ("snp_port".to_string(), "[1 3 2 4]".to_string()),
        ]);
        let resolved = resolve_default_set_v1(&expressions, &HashMap::new(), &HashMap::new()).expect("res");
        assert_eq!(resolved.get("snp_port"), Some(&ResolvedDefaultV1::Vector(vec![1.0, 3.0, 2.0, 4.0])));
    }
}