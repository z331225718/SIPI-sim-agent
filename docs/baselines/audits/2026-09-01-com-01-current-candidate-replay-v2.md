# COM-01 Current Candidate Replay v2 Audit

Date: 2026-09-01

This record binds two fresh immutable replays of the COM-01 public
`config-validate` leaf after the Rust direct port added source-order
consumption provenance. The business candidate is
`5b974ebd799fefd2b89c11a0626dc5c6e555d885` (tree
`329bfc2b08d5593744f498aea18c924c7a41e9dd`); the external reference is
Agent-COM `5272ffe74702cd585054d975559b06f8afae7b6e` (tree
`7094ab6e84989b218730c52432c70da10261f8ea`). Both sides were materialized
from Git archives. The Python reference was invoked only through frozen,
offline `uv` inside its extracted archive.

The 14-scenario public matrix produced seven value matches and seven matching
error categories in each independent run. The complete bounded materialized
JSON projection, including `config_consumption`, matches for the primary XLSX
case. No scenario difference keys or scoped blockers remain.

This is a scoped implementation observation, not a declaration of complete
COM parity, migration-row closure, product promotion, or release readiness.
It stores only bounded hashes, counts, categories, and derived summaries; it
does not store raw workbook configuration values. S-parameter fitting is not
in scope and the channel policy remains impulse-only.
