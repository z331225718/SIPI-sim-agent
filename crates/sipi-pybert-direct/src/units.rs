use serde::{Deserialize, Serialize};

macro_rules! si_unit {
    ($name:ident) => {
        #[derive(Debug, Clone, Copy, Deserialize, PartialEq, Serialize)]
        #[serde(transparent)]
        pub struct $name(pub f64);

        impl $name {
            pub fn is_finite_positive(self) -> bool {
                self.0.is_finite() && self.0 > 0.0
            }
        }
    };
}

si_unit!(Seconds);
si_unit!(Hertz);
si_unit!(Volts);
si_unit!(Ohms);
