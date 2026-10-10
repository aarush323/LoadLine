---
name: loadline-run
description: >-
  Run Loadline load-testing and scalability investigation on the user's repository
  using analyze --boot --json, optional .loadline.yaml hints, and loadline run.
---

## 1. When to use this skill

Use this skill when the user wants **load-testing**, **capacity investigation**, or a **scalability investigation** of **their own** repository with Loadline. Do not use it to patch application code, weaken sandbox policy, or substitute another project. Install Loadline from the project clone (`uv sync`, `uv run loadline`); do not claim a PyPI package or invent install commands.

## 2. Prerequisites

Before running Loadline, confirm:

- **Docker or Podman** is available for sandboxed boots and load (k6 runs as a container on the run network).
- **Git** is installed (Entire Graph and repository metadata depend on it).
- A **model API key** is configured for the provider named in `LOADLINE_MODEL` (Loadline checks credentials before Docker on `run` and `analyze --boot`).
- **Entire** is provisioned by Loadline (`loadline doctor`); you do not install Entire separately for the agent workflow.
- **k6** is provided as a **pinned container image digest** inside Loadline, not as a binary on `PATH`.

Run `loadline --version` and `loadline doctor` (without `--check-model` unless the user accepts provider billing).

## 3. Boot JSON

From the repository root, run:

```bash
loadline analyze --boot --json
```

Read **`status`**, **`blocker`**, **`attempts`**, and **`config_schema`** (`loadline-hints/1`). If the JSON is malformed, stop and show the raw output. Do not guess fields that are absent.

Allowed hint keys when editing `.loadline.yaml` are only those in `tech_doc.md` §16.3: `schema_version`, `compose_file`, `dockerfile`, `compose_profile`, `app_service`, `container_port`, `health_path`, `command`, `env`, `exclude_operations`, `slo.p95_ms`, `slo.err_rate`.

## 4. Retryable blocked boots

If **`status`** is `blocked`, **`blocker.retryable`** is true, and **`blocker.security`** is false:

- Apply **only** a `remediation.field` from the boot JSON that appears in the §16.3 key table above.
- Make the **smallest** edit to `.loadline.yaml` (create the file if needed with `schema_version: 1`). Do not add unknown keys, secrets, or host URLs.
- Re-run `loadline analyze --boot --json`.
- Stop after **two corrections** (three boot attempts total including the first).

Do **not** edit application source, Compose files, or Dockerfiles.

## 5. Stop conditions

If **`status`** is `needs_input`, or **`blocker.security`** is true, **stop** and show the blocker to the user. Do **not** invent a secret, credential, or policy exception. Do **not** weaken sandbox policy (privileged mode, host mounts, `docker.sock`, published ports, egress). Ask the user for values only when `user_can_provide` names them; never write secrets into `.loadline.yaml` or the chat.

## 6. Successful boot and report

If **`status`** is `booted`, run:

```bash
loadline run --repo .
```

Then open the run directory's **`report.md`** and **`report.json`** (under Loadline's home, not inside the target repo). Summarise measured numbers, findings, hypotheses, limitations, and any `investigation_incomplete` state honestly. Do **not** edit application source, Compose, or Dockerfiles. Do **not** invent bottlenecks, trace URLs, or numbers that are not in the report.
