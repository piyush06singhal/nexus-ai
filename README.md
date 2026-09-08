# NEXUS

**An Autonomous AI Workforce & Company OS.**

NEXUS lets you hand a high-level business objective to a system of AI agents that plans, coordinates, and executes toward it. It combines three long-term ambitions into one platform:

1. **AI Company in a Box** — a full company operating on AI.
2. **AI Employee OS** — a runtime for individual AI workers with memory, tools, and supervision.
3. **Autonomous Startup / Business Engine** — continuously drives a business mission end to end.

> **Status: Phase 0 (Foundation).** This repository is a clean, runnable foundation for the platform. Nothing agent-like exists yet — the dashboard, API, database, and provider-agnostic AI abstraction are in place, and every future area is clearly marked as a placeholder.

---

## Quick Start

The fastest way to see the whole stack running is Docker Compose:

```bash
# 1. Create your environment file
cp .env.example .env

# 2. Build and start everything (Postgres, Redis, API, Web)
docker compose up --build
```

Then open:

- Frontend dashboard: <http://localhost:3000>
- API docs (Swagger): <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>

### Applying database migrations

Migrations run separately from the app so schema concerns stay distinct from the runtime. With Postgres up:

```bash
cd apps/api
source .venv/bin/activate
alembic upgrade head
```

---

## Local Development (without Docker for the app)

Run Postgres and Redis in Docker, and the app servers directly on the host:

```bash
# One-shot bootstrap (recommended)
./scripts/setup.sh
```

Or, step by step:

```bash
# Backend
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend (in a second terminal)
cd apps/web
npm install
npm run dev                            # http://localhost:3000

# Infrastructure (Postgres + Redis)
cd <repo root>
docker compose up -d postgres redis
```

---

## Running Tests & Checks

```bash
# Backend tests
cd apps/api && source .venv/bin/activate
pytest -v

# Backend lint + format
ruff check app tests
ruff format --check app tests

# Frontend lint + typecheck + build
cd apps/web
npm run lint
npm run build
```

---

## Project Structure

```
nexus-ai/
├── apps/
│   ├── api/        # FastAPI backend (Python)
│   │   ├── app/
│   │   │   ├── core/       # config, logging, errors, redis
│   │   │   ├── api/v1/     # versioned HTTP endpoints
│   │   │   ├── db/         # SQLAlchemy engine, sessions, models
│   │   │   └── ai/         # provider-agnostic model abstraction
│   │   ├── alembic/        # database migrations
│   │   └── tests/
│   └── web/        # Next.js frontend (TypeScript, Tailwind)
│       ├── src/app/        # App Router pages + layout
│       ├── src/components/ # sidebar, header, dashboard, placeholders
│       └── src/lib/        # API client, shared types, nav config
├── docs/           # architecture, roadmap
├── infrastructure/
│   └── docker/     # Dockerfiles for api and web
├── scripts/        # developer tooling (setup.sh)
├── docker-compose.yml
└── .env.example    # documented environment variables
```

---

## Environment Variables

All configuration flows through environment variables — **no secrets or hardcoded values** are committed. Copy `.env.example` to `.env` and adjust. Key variables:

| Variable                | Description                          | Default (dev)                         |
| ----------------------- | ------------------------------------ | ------------------------------------- |
| `ENVIRONMENT`           | `development` / `test` / `production` | `development`                         |
| `LOG_LEVEL`             | Application log level                | `INFO`                                |
| `DATABASE_URL`          | SQLAlchemy Postgres connection URL   | `postgresql+psycopg://...@localhost:5432/nexus` |
| `POSTGRES_USER`         | Postgres user                        | `nexus`                               |
| `POSTGRES_PASSWORD`     | Postgres password                    | `nexus_dev`                           |
| `POSTGRES_DB`           | Postgres database name               | `nexus`                               |
| `REDIS_URL`             | Redis connection URL                 | `redis://localhost:6379/0`            |
| `API_HOST` / `API_PORT` | API bind address and port            | `0.0.0.0` / `8000`                    |
| `CORS_ORIGINS`          | Allowed browser origins              | `["http://localhost:3000"]`           |
| `API_BASE_URL`          | Frontend→backend proxy target        | `http://localhost:8000`               |

AI provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, …) are reserved for later phases and are not required now.

> **Important:** never commit `.env` files. They are git-ignored by default.

---

## How the Frontend Reaches the Backend

The Next.js app proxies `/api/*` to the backend through a rewrite in `next.config.ts`. The browser only ever talks to its own origin, so there is no CORS friction in local dev or in Docker. Set `API_BASE_URL` if the backend is not on `localhost:8000`.

---

## Documentation

- [Architecture](docs/architecture.md) — system design, components, and key decisions.
- [Roadmap](docs/roadmap.md) — the phased plan from foundation to autonomous business engine.

---

## Contributing

This is an active, phased build. Before contributing, read the [roadmap](docs/roadmap.md) to see which phase is current. Keep changes small, typed, and tested; follow the existing lint/format conventions (ruff for Python, ESLint + strict TypeScript for the web app).