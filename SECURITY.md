# Security Policy

## Reporting a vulnerability

Please use GitHub Private Vulnerability Reporting for security issues. Do not
open a public issue containing credentials, private paths, exploit details, or
data recovered from another user's machine.

Include:

- the affected version or commit;
- the execution mode (`restricted_batch` or `trusted_full`);
- the smallest safe reproduction;
- expected and observed behavior;
- whether files, credentials, network access, or command execution are involved.

## Trust boundaries

- `restricted_batch` is designed for bounded, read-only input analysis and
  project-scoped outputs.
- `trusted_full` can execute an unsandboxed host terminal. Explicit user
  authorization does not make unknown input trustworthy.
- Network access and optional external services require a separate opt-in.
- Codex, Hermes, local model servers, MCP servers, skills, browsers, and command
  line tools have independent update and security boundaries.

Never commit `.env`, generated `.codex/config.toml`, `work`, SQLite databases,
logs, local model credentials, Hermes profiles, or private research data.
