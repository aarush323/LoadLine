# 12 — Tools and dependencies by layer (BOM, v3)

Pins for the tools in `tech_doc.md` R9: Docker and Compose, k6, git (read-only metadata), ripgrep, Entire, and the dependency clients for Postgres first. Versions below were noted on 2026-10-09 and must be re-checked at the spike (`uv lock`, `docs/toolchain.txt`).

## 1. Core (always installed)

| Purpose | Tool | Pin | Licence | Notes |
|---------|------|-----|---------|-------|
| Language | Python 3.12 | `>=3.12,<3.13` | PSF | |
| Env/deps | uv | 0.12.24 | MIT/Apache-2.0 | commit `uv.lock` |
| CLI | Typer | 0.27.3 | MIT | |
| Terminal UI | Rich | 15.0.0 | MIT | |
| Agent harness | Pydantic AI | 2.54.0 | MIT | core only |
| Typing/settings | pydantic 2.14.0, pydantic-settings 2.15.0 | | MIT | |
| Model SDKs | openai 3.27.0 and/or anthropic 1.13.0 | | Apache-2.0 / MIT | via `LOADLINE_MODEL`; OpenAI-compatible local endpoints supported |
| Tracing (partner) | neatlogs[pydantic-ai] | 1.4.26 | MIT | |
| HTTP client | httpx | 0.28.1 | BSD-3 | spec fetch, health, smoke |
| Process utils | psutil | 7.2.2 | BSD-3 | host metrics, process groups |
| JSON ledger | orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | |
| Templates | Jinja2 | 3.1.6 | BSD-3 | report.md |
| Logging | structlog | 26.1.0 | MIT/Apache-2.0 | |
| Env files | python-dotenv | 1.2.4 | BSD-3 | CLI keys only |
| Git | git CLI ≥2.36 (subprocess) | | GPL-2.0 | read-only metadata |
| Search | ripgrep | *pin at spike* | MIT/Unlicense | literal code search |
| Stats | numpy + scipy | *pin at spike* | BSD-3 | prediction evaluator |
| YAML | PyYAML or ruamel.yaml | *pin at spike* | MIT | packs, catalogue |

Dev: pytest 9.1.1, hypothesis 6.168.5 (verdict/bracket/confidence properties), ruff 0.16.10, pyright 1.1.414, pre-commit 4.6.2, gitleaks v8.30.1.

## 2. Adapter tools (optional per tier; absent ⇒ capability `degraded`/`unsupported`, never a crash)

| Layer | Tool | Role | Tier | Notes |
|-------|------|------|------|-------|
| Runtime | Docker Engine ≥24 / Podman, Compose v2 | containers | A | rootless preferred |
| Runtime | gVisor `runsc`, Kata, Firecracker | T1/T2 isolation | B | doctor detects |
| Runtime | Cloud Native Buildpacks (`pack`) / Railpack / Nixpacks | buildpack adapter | B | *pin at spike S-BUILD* |
| Generator | k6 (grafana/k6) | open-model generator | A | AGPL-3.0; external unmodified process/container; version pinned at spike (v2 BOM: v2.3.0 verified 2026-09-21) |
| Generator | Locust / ghz / vegeta | alternate generators | C | optional adapters |
| Fault injection | toxiproxy-class proxy | `dependency_perturb` | A/B | *pin at spike* |
| Stubs | WireMock-compatible / Mockoon | external HTTP dependency stubs | B | *pin at spike* |
| Code intel | ripgrep | literal search when Entire is missing or partial | A | |
| Code intel | Entire CLI + graph plugin | `query`, `def`, `neighbors`, `impact` | A | flags from the installed `--help` |
| Code intel | LSP servers (pyright, tsserver, gopls, jdtls) | call hierarchy | C | optional |
| Observability | cgroup v2 files, `docker stats`/engine API | universal tier | A | |
| Observability | Postgres (`psycopg[binary]` 3.3.6, LGPL-3.0-only), Redis client, MongoDB client, MySQL client | dependency adapters | A/B | optional extras; not core dependencies |
| Observability | Prometheus text parser | app metrics | B | |
| Profilers | py-spy, async-profiler/JFR, pprof, Node inspector | `profile_capture` | B | in-sandbox |
| Fix/verify | per-ecosystem test runners (pytest, npm/pnpm test, go test, mvn/gradle) | repo's own commands | A (Py, Node) / B | executed in sandbox |
| Partners | neatlogs, Entire, cfo.ai | | | `15` in contract |

## 3. Fixtures and corpus dependencies (never in `loadline/` dependencies)

Fixture applications carry their own manifests under `tests/fixtures/<name>/` (their own languages, frameworks and datastores). Corpus and canary repos are pinned by URL + commit in `tests/corpus/manifest.yaml`. Nothing under `tests/fixtures` or `tests/corpus` is importable from `loadline/` (lint).

## 4. Licence notes

k6 AGPL-3.0: run unmodified as an external process/container; document in `docs/SUBMISSION.md`. psycopg LGPL: dynamic wheel only, optional extra. orjson MPL-2.0: file boundary. Container images from the catalogue carry their own licences; the catalogue records them.

## 5. Replaced/removed from v2 BOM

FastAPI, SQLAlchemy, asyncpg, uvicorn (reference app deps) moved to fixtures; `psycopg` moved from core to the Postgres adapter extra; OpenAPI "stdlib json only" decision replaced by a spec-parsing adapter (library chosen at spike).
