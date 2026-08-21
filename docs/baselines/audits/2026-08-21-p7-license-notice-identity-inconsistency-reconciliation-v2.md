# P7 License/NOTICE Historical Identity Reconciliation v2

This additive record does not rewrite the historical build or normalization
evidence. It records that seven digests described as clean/archive identities
are CRLF materialization digests rather than the canonical Git blob bytes.

For every bound path, the verifier reads the exact Git object, records its
canonical SHA-256, and proves that it differs from the historical recorded
digest. Six code/config identities are explained by an LF-to-CRLF diagnostic
transform; the historical license-manifest digest is not. EOL equivalence is
never accepted as byte identity.

Consequently the historical 86-package and normalized metadata observations
are not current evidence. The external reports are missing, dependency and
NOTICE review remains incomplete, and release promotion remains blocked.
