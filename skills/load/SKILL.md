# Load Skill

Agentic environment step for `loadline load`.

- Called only when `resolve` found a login-like route and `auth` is empty, or when a prepare candidate is ambiguous.
- Inputs are the `ResolvedConfig` service, port, health path. Correct only with `file:line` citations.
- Tools: `check_config`, `try_boot` (max 5), `write_config`. No shell.
- Never invent hostnames, ports, or commands outside the detection report.
