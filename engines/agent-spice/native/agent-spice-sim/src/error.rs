use thiserror::Error;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Error)]
pub enum Error {
    #[error("{0}")]
    Usage(String),
    #[error("{0}")]
    InvalidDeck(String),
    #[error("{0}")]
    Parse(String),
    #[error("{path}:{line}: {message}\n  statement: {statement}{expanded}")]
    Source {
        path: String,
        line: usize,
        statement: String,
        expanded: String,
        message: String,
    },
    #[error("sparse solve failed: {0}")]
    Sparse(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

impl Error {
    pub fn at_source(
        self,
        path: &std::path::Path,
        line: usize,
        statement: &str,
        expanded_statement: &str,
    ) -> Self {
        if matches!(self, Self::Source { .. }) {
            return self;
        }
        let expanded = if expanded_statement == statement {
            String::new()
        } else {
            format!("\n  expanded: {expanded_statement}")
        };
        Self::Source {
            path: path.display().to_string(),
            line,
            statement: statement.to_string(),
            expanded,
            message: self.to_string(),
        }
    }
}
