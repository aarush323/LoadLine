---
name: Setup config design
overview: Two commands only. `loadline run` stays the full path from boot through the report. `loadline load` is the new agentic environment step. Do not add setup, check, or another analyze flow.
todos:
  - id: phase-0-k6
    content: "Phase 0 only: k6 target and status-count fixes. Do not change boot_repository or its callers."
    status: pending
  - id: phase-1-schema
    content: "Phase 1 only: schema accepts existing .loadline.yaml. load_hints stays the parser. No boot change."
    status: pending
  - id: phase-2-resolve
    content: "Phase 2 only: resolve() reuses _infer_app_service and _health_url. Not wired into boot."
    status: pending
  - id: phase-3-wrapper
    content: "Phase 3 only: boot_and_prepare delegates to boot_repository unchanged and writes resolved_target.json."
    status: pending
  - id: phase-4-compose-model
    content: "Phase 4 only: compose config reader used by loadline load. boot_repository still uses load_compose."
    status: pending
  - id: phase-5-load-cmd
    content: "Phase 5 only: add loadline load. It writes config. run ignores that file while detection already finds a target."
    status: pending
  - id: phase-6-prepare
    content: "Phase 6 only: replay prepare when the config list is non-empty. Empty list stays on boot_repository."
    status: pending
  - id: phase-7-auth
    content: "Phase 7 only: profile auth on k6 when present. Keep _sealed_auth_profiles as the fallback."
    status: pending
  - id: phase-8-agent
    content: "Phase 8 only: the load agent, used only by loadline load. run never calls it."
    status: pending
  - id: phase-9-closure
    content: "Phase 9 only: compose.start_set closure, default remains all."
    status: pending
isProject: false
---

# Loadline run and load

Execute one phase, run its gate, stop. Do not start the next phase in the same change set. Do not revert the current uncommitted k6 and investigator edits. Do not `git checkout` those files.

This spec replaces a big-bang rewrite. The working path today is `loadline run` calling `boot_repository` in [loadline/adapters/runtime/compose_boot.py](loadline/adapters/runtime/compose_boot.py), then the investigator, then the report. That already boots unreliable-blind and the FastAPI template when their environment is present. New code is added beside it. The old function remains the implementation of the empty-config boot until a phase below says otherwise.

## Two commands

These are the only commands this work adds or changes. Do not add `setup`, `check`, or a second investigate command. Do not rename `run`. Do not wire this design through `loadline analyze`. Leave [loadline/boot.py](loadline/boot.py) and the `analyze` branch of [loadline/cli.py](loadline/cli.py) untouched for the whole spec.

- `loadline run` is the command that already does the whole job: boot, investigate, report. It stays that command. Later phases make its boot replay a config that `load` wrote (prepare, then auth). `run` never calls the load agent. If detection is already unambiguous, `run` does not need `load` to have been run.
- `loadline load` is the new command. It is the agentic environment step: figure out the config, try a boot, write the config, tear that boot down. It does not investigate and it does not write a report. Nothing calls it automatically. `run` does not call it.

k6's own `setup()` function is unrelated. Do not rename it, and do not treat it as the `load` command.

## Hard rules

1. If a config has no prepare steps, no auth profile, and `start_set` is `all` or absent, `boot_and_prepare` calls `boot_repository` with the same arguments the caller used before (`repo`, `hints`, `teardown`, `require_auth`, `progress`) and returns that outcome unchanged.
2. Do not replace `load_compose` inside `boot_repository` with `docker compose config`. A bare `docker compose config` merges `compose.override.yml`. On this FastAPI pin that switches the backend to `fastapi dev`. Boot keeps parsing the one base file it parses today.
3. Do not delete `_infer_app_service`, `_health_url`, `_health_path_candidates`, `_sealed_auth_profiles`, or `_auth_setup_block`. Later phases call them. A fallback stays until the phase that replaces that fallback has a passing test.
4. Do not edit [loadline/core/sandbox_policy.py](loadline/core/sandbox_policy.py) before phase 9. Default boots must keep today's refuse and drop behavior.
5. Do not edit the investigator agent loop, its tool list (`repo`, `read_file`, `run_k6`), or [agents/investigator_prompt.md](agents/investigator_prompt.md) except for the one sentence named in phase 7.
6. Do not generate a Dockerfile or a compose file. HoH has no HTTP service in compose; the existing "no application service" blocker is the outcome. Do not special-case the string `HoH`.
7. Do not add cookie login, signup, multiple targets, or a call from `run` into `load`. Do not register a subcommand named `setup` or `check`.
8. Do not hardcode service names `app` or `backend`, or the variable names `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD`, in any new file. The existing `_sealed_auth_profiles` may keep those two names. That is the only place they remain.
9. Secrets generated for a boot stay in memory on the boot outcome. Do not write them into the repo, into `loadline.yaml`, or into `resolved_target.json`.
10. `--project-directory` for any new `docker compose` invocation is the repo. A runtime file under `LOADLINE_HOME` is only an `-f` argument, never the project directory.

## What already works and must stay green

After every phase, this unit set must pass with no assertion edits except tests you added in that phase:

- `tests/unit/test_compose_boot_generalization.py`
- `tests/unit/test_readiness.py`
- `tests/unit/test_readiness_budget.py`
- `tests/unit/test_env_policy.py` including `test_literal_stripe_key_cleared_not_needs_input`
- `tests/unit/test_sandbox_policy.py`
- `tests/unit/test_k6_compiler.py`
- `tests/unit/test_k6_operation_metrics.py`
- `tests/unit/test_investigator_tools.py`
- `tests/unit/test_investigator_run.py`
- `tests/unit/test_run_pipeline_auth.py`
- `tests/unit/test_run_pipeline_blocked.py`
- `tests/unit/test_run_pipeline_single_agent.py`
- `tests/unit/test_cli_run.py`
- `tests/unit/test_target_guard.py`

Do not change those assertions to match a new behavior. If one fails, the phase is wrong.

`boot_repository` order today, which the empty-config path must keep: hints, `discover_profile`, one compose file from `_resolve_compose_path`, `load_compose`, `_infer_app_service`, `apply_sandbox_policy`, internal network, `compose up`, egress proof, `_wait_http` on `_health_path_candidates`, optional postgres row count. No migrations. No login.

k6 today: [loadline/investigator/k6_tool.py](loadline/investigator/k6_tool.py) `_app_target` reads `boot["health"]["url"]`. If that URL is missing it falls back to hostname `app` and port `8000`. Auth secrets come from `_sealed_auth_profiles` via `InvestigationDeps.auth_profiles`. `_resolve_auth_secrets` accepts only the profile name `default_user`. Leave that acceptance in place until phase 7 adds other names beside it.

`run_loadline` builds `allowed_hosts` from every service name on the boot record. Leave that line in place through phase 8. Narrowing the allowlist is phase 9 and only for the declared target host, still including that host.

## Phase 0 — k6 measurements only

Files you may edit:

- [loadline/investigator/k6_tool.py](loadline/investigator/k6_tool.py) `_app_target` only
- [loadline/adapters/generator/k6_operation_metrics.py](loadline/adapters/generator/k6_operation_metrics.py) if a unit test shows status `0` is still counted as success
- tests under `tests/unit/test_k6_operation_metrics.py` and `tests/unit/test_investigator_tools.py`

Files you must not edit: `compose_boot.py`, `boot.py`, `run_pipeline.py`, `cli.py`, `run.py`, `k6_compiler.py` except if `handleSummary` already in the working tree is missing per-operation status counts. Do not change `_auth_setup_block`.

Steps:

1. Keep the working-tree status aggregation. Add or extend a unit test that feeds metric names for HTTP 200, 404, and 503 and expects those three counts. An all-zero status bucket is an error, not a successful run. Empty operations are an error.
2. Change `_app_target` so a missing health URL returns a structured error from `run_k6` (`origin_unknown`) instead of hostname `app`. When the health URL is present, host and port still come from that URL. Do not add a new default port.
3. Do not change `allowed_hosts`.

Gate: the unit files listed above. No Docker required. Stop.

## Phase 1 — one parser, old files still load

Add [loadline/config/schema.py](loadline/config/schema.py). Change [loadline/core/hints.py](loadline/core/hints.py) so `load_hints` and `LoadlineHints` remain the names every current caller imports. Implement them by calling the new schema, or have the schema call `load_hints`. One implementation. Callers in `boot.py` and `compose_boot.py` stay on `load_hints`.

The schema accepts exactly the keys in `ALLOWED_KEYS` today: `schema_version`, `compose_file`, `dockerfile`, `compose_profile`, `app_service`, `container_port`, `health_path`, `command`, `env`, `exclude_operations`, `slo.p95_ms`, `slo.err_rate`. Unknown keys are still an error. `health_path` must still start with `/`.

You may add optional keys only if omitting them leaves parsing identical: `compose.files` (list of strings), `compose.start_set` (`all` or `closure`, default `all`), `prepare` (list, default empty), `auth` (mapping, default empty), `meta` (mapping, ignored by boot). A file that contains only the old keys must produce the same `LoadlineHints` fields as today.

Do not put secret string values in `auth` or `env`. An `env` entry that is a plain string stays valid, because that is the current hints shape. New env kinds (`generate`, `placeholder`, `needs_input`, `set`) are an alternate shape. Do not change `apply_env_policy`.

Tests to add in `tests/unit/test_hints_schema.py`:

- The fixture [tests/fixtures/fx-docker-http/.loadline.yaml](tests/fixtures/fx-docker-http/.loadline.yaml) still loads.
- An unknown key still errors.
- A file with only `app_service`, `container_port`, and `health_path` still yields those three fields.
- `compose.start_set` omitted means `all`.
- `prepare` omitted means an empty list.

Gate: new tests plus `tests/unit/test_compose_boot_generalization.py`. Boot behavior is unchanged because nothing reads the new keys yet. Stop.

## Phase 2 — resolve() matches today's picker

Add [loadline/config/resolve.py](loadline/config/resolve.py) and [loadline/config/target.py](loadline/config/target.py).

`resolve(repo: Path) -> ResolvedConfig` must:

1. Call `load_hints(repo / ".loadline.yaml")`. On a hints error, return that error. Do not boot.
2. Call `discover_profile`. Choose the compose file with the existing `_resolve_compose_path`. Do not also open `compose.override.yml`.
3. Call `load_compose` on that file. Call `_infer_app_service` and `_health_url`. Do not copy those function bodies. Import them. If you move them, re-export the old names from `compose_boot.py` so existing tests still import them.
4. If there is no winner, `ResolvedConfig.blocker` is the same "No application service found in compose." outcome `boot_repository` already returns. Do not invent a service.
5. Build a frozen `Target` with `service`, `port`, `health_path`, `origin` (`http://{service}:{port}{health_path}`). Write nothing to disk.

`ResolvedConfig` fields: `hints`, `compose_file` (repo-relative string), `target` or `blocker`, `prepare` (empty unless the yaml listed steps), `auth` (empty unless the yaml listed a profile), `start_set` (`all` unless the yaml said `closure`).

Tests in `tests/unit/test_resolve.py`, using the compose dicts already built in `tests/unit/test_compose_boot_generalization.py`:

- The service `resolve` picks equals `_infer_app_service` on the same dict.
- The port and path equal `_health_url` on the same dict.
- A tie or zero candidates does not guess.
- Hints `app_service` still wins, because `_infer_app_service` already does that.

Do not call `resolve` from `boot_repository`, `boot.py`, or `run_pipeline.py`. Gate: new tests plus the generalization tests. Stop.

## Phase 3 — wrapper that does not change boot

Add [loadline/adapters/runtime/boot_and_prepare.py](loadline/adapters/runtime/boot_and_prepare.py):

```text
boot_and_prepare(repo, *, hints, teardown, require_auth, progress) -> BootOutcome
```

Body for this phase, the whole body:

1. `outcome = boot_repository(repo, hints=hints, teardown=teardown, require_auth=require_auth, progress=progress)`.
2. If `outcome.status == "booted"` and `outcome.boot` has a health URL, write `run_dir/resolved_target.json` with the service, port, path, and origin taken from that URL. Include `compose_file` from the hints or the file boot already selected. Include `start_set: "all"`. Do not include secrets.
3. Return `outcome`.

Replace the `boot_repository` call in `run_loadline` only, with `boot_and_prepare` using the same keyword arguments. Leave every line after that call as it is, including `hosts = frozenset(s["name"] for s in boot.boot["services"])` and the investigator call. Do not edit `analyze_boot_json`.

Do not add prepare, auth probes, or `docker compose config` inside the wrapper yet. The function exists so later phases have one place to extend. This phase's diff in `compose_boot.py` should be empty.

Tests: a unit test that mocks `boot_repository` and asserts `boot_and_prepare` passes `hints`, `teardown`, `require_auth`, and `progress` through unchanged, and writes `resolved_target.json` only when status is `booted`. Existing pipeline tests must pass without edits.

Gate: those tests. Stop.

## Phase 4 — compose model, not used by boot

Add [loadline/config/compose_model.py](loadline/config/compose_model.py). It is not called from `boot_repository` or from the phase-3 wrapper.

Behavior:

1. Read `env_file` paths from the raw YAML of the selected compose file. `docker compose config` is not used to discover them, because a missing file makes `config` fail first.
2. For a missing `env_file` path, if `.env.example` exists, copy it into the run directory and rewrite only that entry in a runtime copy to an absolute path. Do not rewrite `build.context`, `dockerfile`, or volume sources. Never write into the repo.
3. Run `docker compose` through `docker_cmd` with explicit `-f` for each file in `compose.files` or, if that list is empty, the one base file. Always pass `--project-directory` set to the repo. Always pass `--env-file` pointing at the repo `.env` when that file exists, otherwise at the run-directory copy, otherwise at an empty file created in the run directory. Subprocess environment is only `PATH` plus the variables `docker_cmd` already needs to reach the socket. Do not pass the parent process environment through.
4. After `config` succeeds, every resolved build context and bind-mount source for a service that will start must be a named volume or a path inside the repo. A path under the run directory is allowed only for the rewritten env file. Anything else returns blocker code `compose_invalid` and does not launch.

Tests, no daemon required, by faking `docker_cmd`:

- Command line contains `-f` and the base file, and does not omit `-f`.
- Command line contains `--project-directory` equal to the repo and `--env-file`.
- A parent env var `POSTGRES_PASSWORD` is absent from the subprocess environment.
- `compose.files` unset does not add `compose.override.yml` even if that file exists on disk.
- A rewritten build context that lands under the run directory is `compose_invalid`.
- A missing `env_file` is rewritten; a bind of `./db/init.sql` stays under the repo.

Gate: those tests. `boot_repository` still does not call this module. Stop.

## Phase 5 — `loadline load` writes a file, `run` stays on detection

Add one subcommand, `load`, in [loadline/cli.py](loadline/cli.py). Do not add `setup`. This phase does not call a model.

Steps inside `load`:

1. If `docker_cmd` cannot reach the daemon, or `discover_profile` finds no compose file and no Dockerfile, exit `blocked` before any pull. Print the reason. Do not create a Dockerfile.
2. Call `resolve`. If it has a blocker, print it and exit. Do not guess.
3. Call `boot_and_prepare` with `teardown=True`. That boot is thrown away. `load` does not start the investigator and does not write a report.
4. Write `LOADLINE_HOME/configs/<repo-key>/loadline.yaml` containing only values `resolve` already produced: compose file, service, port, health path, `start_set: all`, empty `prepare`, empty `auth`, and `meta.fingerprint`. `--write-to-repo` is the only way a file is copied to the repo `.loadline.yaml`. Default is not to write into the repo.
5. Fingerprint in [loadline/config/fingerprint.py](loadline/config/fingerprint.py) hashes the compose file used, Dockerfiles next to it, `.env.example` if present, and any `meta.evidence` paths. Mismatch on a later `run` prints a warning and still boots. Do not regenerate the yaml because the hash changed.

`run_loadline` does not read the generated file in this phase. It keeps loading repo `.loadline.yaml` through `load_hints`, then detection. A generated file must not be able to change a repo that already boots with no yaml.

Tests: `load` writes under the home dir; the repo is unchanged; a fingerprint mismatch is a warning string and `boot_and_prepare` is still called; no daemon in the unit test (mock `docker_cmd` and `boot_and_prepare`). The CLI parser has `run` and `load` and does not have `setup`.

Gate: those tests plus `tests/unit/test_cli_run.py`. Stop.

## Phase 6 — prepare replay only when the list is non-empty

Extend `boot_and_prepare`. The first lines are:

```text
if not config.prepare:
    return the phase-3 body
```

`config` comes from `resolve`. When the yaml has no `prepare`, behavior is phase 3. Do not reorder `compose up` inside `boot_repository`.

When `prepare` is non-empty, do this in `boot_and_prepare` and [loadline/adapters/runtime/prepare.py](loadline/adapters/runtime/prepare.py), not by editing the health loop:

1. Reject a command that is not found verbatim in a service `command`, an `entrypoint`, a script path those strings reference, a one-shot service command, or a Makefile target. A command found only in a README returns `needs_confirmation` and is not executed. Do not treat verbatim matching as a security check. The command still runs only inside a sandbox container.
2. Dedupe: if the app service command, entrypoint, or a one-shot service that will start already contains that command string, skip it. This FastAPI pin has no prestart service and the Dockerfile `CMD` is `fastapi run --workers 4`, so `bash scripts/prestart.sh` is not deduped and runs once.
3. Start dependency services on the same project and network `boot_repository` would use. Do not start the API process yet. Run the command in a one-off container of the app image on that network. Then call the existing up-and-health path for the API. Required-step failure is blocker `prepare_failed`. Optional-step failure is a limitation on the outcome and the boot may continue.
4. On the next `loadline run`, call this same function again. Do not reuse containers or volumes from `load`. `load` uses `teardown=True`, so those are already gone.

Wire `run` only to pass the resolved config into `boot_and_prepare`. Still ignore a generated yaml when the repo has no prepare steps, so today's repos stay on the empty-list branch.

Tests:

- Empty prepare list mocks show `boot_repository` called once and `prepare` not called.
- A one-shot service whose command equals the prepare command does not run it a second time.
- A README-only command is `needs_confirmation`.
- A command present in a Makefile target is allowed.

Gate: those tests plus the readiness tests. Stop. Do not add the FastAPI prestart string to production code. It belongs only in a fixture yaml used by a test.

## Phase 7 — auth on the real k6 path, old fallback kept

Add [loadline/adapters/runtime/probe.py](loadline/adapters/runtime/probe.py). Call it from `boot_and_prepare` only when `config.auth` is non-empty. When `config.auth` is empty, skip the probe and leave `_sealed_auth_profiles` as the investigator's credential source.

When `config.auth` is non-empty:

1. After prepare and the existing health wait, run the profile's positive request from the k6 image. Then run the same request without the token. Accept 401, 403, or 3xx as the negative result. If the profile has no `verify` path, set limitation `auth_unverified` and do not call the result `verified`.
2. If this boot's positive check disagrees with `meta` recorded by `load` (status class changed, or the verify path failed), `run` stops with `auth_failed`. It does not start the investigator.
3. Pass the profile name, method, path, encoding, token field, service, and port into the existing k6 plan. Fill username and password from the in-memory values this boot injected into the app. Do not read a different copy from `.env` if this boot generated a replacement.
4. In `_resolve_auth_secrets`, if the requested profile is present on `deps.auth_profiles`, use it. If the name is `default_user` and the new map has no entry, keep the current `_sealed_auth_profiles` lookup. Delete that fallback only after a test boots the FastAPI template through a yaml profile and k6 `setup()` gets a token without reading `FIRST_SUPERUSER` inside `k6_tool.py`.
5. Login failure inside k6's `setup()` function stays a thrown error. `run_k6` returns `auth_failed` and does not return success counts. A request marked with an auth profile and no resolved secret is an error return. Do not send it. This function is the k6 lifecycle hook, not the `load` command.
6. No login-like route and empty `auth` may be recorded as `auth: none` plus the evidence string "no login-like route". That outcome is allowed to be `verified`. Do not force `limited` for that case. A login-like route with empty `auth` is `limited` and does not call the agent in this phase; phase 8 does.

One sentence in the investigator prompt: if `run_k6` returns `auth_failed`, say auth failed, and do not describe 401 responses as healthy capacity. Touch no other prompt rule.

Tests in `tests/unit/test_k6_compiler.py` and `tests/unit/test_investigator_tools.py`:

- Profile present: compiled `setup()` posts the configured path and uses the injected secret.
- Profile absent, repo `.env` still has the old variable pair: `default_user` still resolves. This keeps current template runs working.
- Missing secret with a profile requested: error, no script executed.
- Negative status 302 is accepted. Negative status 200 sets a warning and is not `verified`.

Gate: those tests plus `tests/unit/test_k6_compiler.py` and `tests/unit/test_run_pipeline_auth.py`. Stop.

## Phase 8 — load agent, unreachable from run

Add [loadline/load/agent.py](loadline/load/agent.py), [loadline/load/tools.py](loadline/load/tools.py), [agents/load_prompt.md](agents/load_prompt.md), and [skills/load/SKILL.md](skills/load/SKILL.md). Do not create a `loadline/setup/` package or a `setup` subcommand.

`loadline load` calls this agent only when `resolve` found a login-like route and `auth` is empty, or when a prepare candidate is ambiguous (more than one allowed source, or a README-only command). Service, port, and health path are already on the `ResolvedConfig` the prompt receives. The agent may correct them by citing `file:line`. It may not invent a hostname, port, or command that is not in the detection report.

Tools, no shell: `check_config` (schema only), `try_boot` (calls `boot_and_prepare` with `teardown=True`), `write_config` (home directory, or `loadline.proposed.yaml` on `--refresh`). Cap `try_boot` at 5 calls. On cap, write the best config and the limitations. Do not overwrite a yaml the user edited; `--refresh` prints a diff against a proposed file.

`run_loadline` must not import `loadline.load`. Grep is the test: [loadline/run_pipeline.py](loadline/run_pipeline.py) and [loadline/boot.py](loadline/boot.py) have zero matches for `loadline.load`. Only the `load` branch in [loadline/cli.py](loadline/cli.py) imports it.

After this phase, `run` may load the generated yaml only when the repo has no `.loadline.yaml` and `resolve` without that yaml would return a blocker. If `resolve` already returns a target, `run` ignores the generated file. That preserves zero-config repos.

Gate: the grep test, a unit test that an unambiguous no-login repo does not construct the agent, and the phase 3 mock that `boot_repository` still receives the old arguments when prepare and auth are empty. Stop.

## Phase 9 — start set, default stays `all`

Only now edit [loadline/core/sandbox_policy.py](loadline/core/sandbox_policy.py). Add an optional argument `started_services: set[str] | None = None`. When it is `None` or `start_set` is `all`, the function body behaves as it does today. Existing sandbox tests call it without that argument and must pass with no assertion edits.

When `start_set` is `closure`:

- Started set = target service, transitive `depends_on`, plus services whose names appear as whole hostname tokens in the target service environment. Do not substring-match. The service name `app` must not match inside another token.
- Do not scan command arguments or config files for hostnames.
- A policy violation on a service outside the started set becomes a note. A violation inside the set still refuses. `ipc: host` and a Docker socket mount follow that rule.
- The boot record lists `not_started`.
- `run_loadline` allowlist becomes the target host from `resolved_target.json`. The database service name is not in the k6 allowlist. The target host is.

Default remains `all` until a manual acceptance note is added to this file saying both repos passed closure. Do not flip the default inside the implementation.

Closure acceptance, checked by hand or by a sandbox test, not by hardcoding repo names in production code:

- unreliable-blind with closure still starts the service named by `DOWNSTREAM_URL`, because that hostname is a whole token. `db` starts because of `depends_on`.
- FastAPI base file with closure starts `backend` and `db` only. It does not start `proxy`. Mailpit is not in the base file. Including `compose.override.yml` via `compose.files` is a separate explicit choice and the report must show the resulting command, which on this pin is `fastapi dev`.

Gate: `tests/unit/test_sandbox_policy.py` unchanged and passing, plus a new test that `started_services=None` matches a golden policy result from before the parameter existed. Stop.

## Placeholder env kind

Do this inside phase 7, not before. In [loadline/core/env_policy.py](loadline/core/env_policy.py), keep clearing literal third-party keys when the config does not mention them. `test_literal_stripe_key_cleared_not_needs_input` must stay true.

When the yaml says `placeholder: true` for a key, put a non-empty value in the in-memory env, record limitation `dependency not replaced`, and do not use the word stub. A stub is only recorded when a compose service in the started set is the hostname for that dependency. Do not create a local Stripe stand-in.

## Out of scope for every phase

Cookie or CSRF login, multiple targets, signup bootstrap, calling `load` from `run`, a `setup` or `check` subcommand, generating Dockerfiles, merging `compose.override.yml` by default, persisting generated secrets, changing pool sizes or worker counts, editing the investigator's tool set, and any edit to `loadline analyze`.

## Done

Phase 9's gate is green, empty prepare and empty auth still call `boot_repository` with the original arguments, `loadline analyze` is byte-for-byte unchanged, and a repo that boots today still boots through `loadline run` on the empty-config branch without a generated yaml. The CLI exposes `run` and `load` for this work, and no `setup` command.
