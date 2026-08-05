# ADR-002: Monorepo、多包与独立发布

状态：已接受。

目标形态为 monorepo，但控制面与三领域引擎保持独立包、版本、lock、bundle 和认证环境。不得形成巨型 wheel、共享 venv 或 release 所需的 sibling editable/path dependency。
