# Loadline reference target: full-stack-fastapi-template

This document describes the pinned third-party application under `integration/targets/full-stack-fastapi-template/`. The clone is gitignored; the pin lives in [`targets.lock.json`](./targets.lock.json).

## Pin

| Field | Value |
| --- | --- |
| Repository | https://github.com/fastapi/full-stack-fastapi-template |
| Commit (full SHA) | `7257e606cb94eada1dca40173e2b7f99dd549bc6` |
| Default branch at clone time | `master` |
| Recorded at (UTC) | `2026-10-10T09:16:42Z` |
| Checkout | Detached HEAD at the pinned commit (not tracking a moving branch) |

## License

MIT License (Copyright (c) 2019 Sebastián Ramírez). See the target’s `LICENSE` file.

## What the project is

Full-stack template: FastAPI backend (SQLModel, PostgreSQL, JWT auth, Alembic), React/Vite/TypeScript frontend (built into the backend image for Compose), Traefik reverse proxy, Adminer, Mailpit for local SMTP, Playwright E2E tests, Pytest backend tests. Primary docs: root `README.md`, `development.md`, `backend/README.md`, `frontend/README.md`.

## Environment configuration

- **Root `.env`** (tracked in the template repo): local development defaults including `PROJECT_NAME`, `SECRET_KEY`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`, `POSTGRES_PASSWORD`, `DATABASE_URL`, and SMTP-related variables. Hostnames use `localhost` for processes on the host; Compose overrides DB/SMTP hosts to service names.
- **`frontend/.env`** (tracked): `VITE_API_URL=http://localhost:8000`, `MAILPIT_HOST=http://localhost:8025`.
- Compose fails fast if required variables are unset (`POSTGRES_PASSWORD`, `SECRET_KEY`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`, `PROJECT_NAME` for backend; deployment compose also requires `DOMAIN`).

The template explicitly states deployment secrets should not live in `.env`; production uses separate deployment guides. For local/CI, the tracked `.env` placeholders (e.g. `changethis`) are sufficient—no undocumented manual secret files are required for the documented local or CI flows.

## Required infrastructure

| Dependency | Role |
| --- | --- |
| **Docker** + **Docker Compose** | Required for all documented full-stack and CI-style test flows |
| **PostgreSQL 18** (`db` service) | Application database |
| **Mailpit** (`mailpit` in override) | Captures outbound email in dev/CI |
| **Traefik** (`proxy` service) | Routes HTTP to backend and Adminer; mounts Docker socket |
| **Backend image build** | `backend:latest` built from `backend/Dockerfile` (multi-stage includes frontend build) |
| **uv** | Python deps and backend commands (local hybrid workflow and CI backend tests) |
| **Bun** | Frontend install/dev/build and Playwright CI |

Optional for local hybrid dev only: run `db` + `mailpit` in Compose while running `uv run fastapi dev` and `bun run dev` on the host.

## How the project expects to be started

### Supporting services only (hybrid local dev)

From the clone root:

```bash
docker compose up -d db mailpit
```

Then from `backend/`: `uv sync`, `uv run bash scripts/prestart.sh`, `uv run fastapi dev`.

From `frontend/` (or root with Bun): `bun install`, `bun run dev`.

Documented URLs: frontend dev `http://localhost:5173`, API `http://localhost:8000`, Mailpit UI `http://localhost:8025`.

### Full stack in Docker Compose (primary integration path)

1. `docker compose run --rm backend bash scripts/prestart.sh` — migrations (`alembic upgrade head`) and seed (`python app/initial_data.py` via `init_db`).
2. `docker compose watch` — starts stack with override (hot reload, published ports).

Documented URLs with override: app `http://localhost:8000`, Swagger `http://localhost:8000/docs`, Adminer `http://localhost:8080`, Traefik dashboard `http://localhost:8090`, Mailpit `http://localhost:8025`.

`compose.yml` is loaded automatically; `compose.override.yml` applies for local dev. `compose.deploy.yml` is for self-hosted HTTPS deployment (Let’s Encrypt, `DOMAIN`) and is not used for the default local stack.

### Root `scripts/test.sh` (Dockerized backend tests)

Builds images, tears down volumes, runs `prestart.sh`, `docker compose up -d`, runs `docker compose exec -T backend bash scripts/tests-start.sh`, then tears down. Requires the full Compose build/up cycle.

## Migrations and seeds

- **Migrations:** Alembic; `backend/scripts/prestart.sh` runs `alembic upgrade head`.
- **Seed:** `backend/app/initial_data.py` calls `init_db(session)` after migrations (creates initial superuser and related data per `init_db` implementation).

Every documented boot path that runs the API against a fresh DB expects `prestart.sh` (or equivalent migrate + seed) before serving traffic.

## Published ports (local `compose.override.yml` only)

Observation from the override file merged with base compose—not an instruction to bind these on the Loadline host:

| Port | Service / purpose |
| --- | --- |
| 80 | Traefik HTTP entrypoint |
| 8090 | Traefik API/dashboard (insecure mode in override) |
| 5432 | PostgreSQL |
| 8080 | Adminer |
| 8000 | Backend (FastAPI dev in container) |
| 8025 | Mailpit web UI |
| 1025 | Mailpit SMTP |
| 9323 | Playwright report host when using `playwright` service |

`compose.deploy.yml` additionally documents 443 for HTTPS when that file is used.

## How tests are documented

| Suite | How upstream runs it |
| --- | --- |
| **Backend (Pytest)** | `uv run bash scripts/test.sh` from `backend/` (with `db` + `mailpit` up), or `docker compose exec backend bash scripts/tests-start.sh` against a running stack; CI: `.github/workflows/test-backend.yml` |
| **Docker Compose smoke** | Build, `prestart.sh`, `up -d --wait backend adminer`, curl health and frontend; `.github/workflows/test-docker-compose.yml` |
| **Playwright** | `prestart.sh`, `up` backend (+ mailpit), `bunx playwright test` on host, or `docker compose run --rm playwright ...` in CI; `.github/workflows/playwright.yml` |
| **Full stack script** | `./scripts/test.sh` at repo root (Compose lifecycle + backend tests inside container) |

Backend tests use `coverage` with a 90% fail-under in CI. Playwright shards across four jobs in CI.

## Blockers and constraints for a future Loadline run

These are factual obstacles observed from upstream docs and compose layout—not workarounds.

1. **Docker Compose is mandatory** for the documented full-application startup and for upstream’s integration test scripts; there is no single-process “run the app” command without Postgres (and typically Mailpit) in containers or equivalent.
2. **Image build required** before a healthy stack: `docker compose build` (or `watch` rebuild paths). First boot needs `docker compose run --rm backend bash scripts/prestart.sh` against a healthy `db`.
3. **Traefik `proxy` service** requires read-only access to `/var/run/docker.sock`; environments that forbid Docker socket mounts cannot run the stack as designed.
4. **Host port surface** is large (80, 443 in deploy file, 8000, 5432, 8080, 8090, 8025, 1025, 9323); collisions with other services on the same machine will prevent startup unless compose files are changed (out of scope for Loadline pin).
5. **Placeholder secrets** in tracked `.env` are intentional for dev; production/deploy paths expect real `SECRET_KEY`, passwords, and `DOMAIN`—Loadline must not treat `changethis` as production-safe, but local documented flows do not require fetching undisclosed secrets.
6. **Toolchain surface:** meaningful reproduction may require **uv**, **Bun**, and **Docker** versions compatible with the template’s CI (Python from `.python-version`, Bun 1.3.12 in Playwright workflow).
7. **Playwright / E2E** adds browser dependencies and the optional `playwright` Compose service; not required for backend-only or compose-smoke paths upstream documents separately.

## Loadline policy for this target

- Do not commit, push, or patch inside the clone.
- Re-pin by updating `targets.lock.json` and re-checking out the new SHA in a clean tree.
- Route paths, handler names, and schema names belong only in this file (or other integration docs)—not in `loadline/` discovery code.
