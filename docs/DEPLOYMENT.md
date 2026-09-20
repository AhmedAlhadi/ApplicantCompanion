# Deployment Guide

## Configuration

All configuration is environment-driven — see [`.env.example`](../.env.example)
for the annotated template. Key groups:

| Group | Variables | Notes |
|---|---|---|
| Core | `SECRET_KEY`, `APP_ENV`, `FRONTEND_ORIGIN` | Set a long random `SECRET_KEY` in production |
| Database | `DATABASE_URL` | `postgresql+psycopg2://…` in prod, `sqlite:///…` for dev |
| Vectors | `VECTOR_STORE`, `QDRANT_URL`, `QDRANT_API_KEY` | `qdrant` or `memory` |
| Objects | `OBJECT_STORE`, `MINIO_*`, `LOCAL_STORAGE_PATH` | `minio` or `local` |
| LLMs | `OPENROUTER_API_KEY`, `OPENROUTER_*`, `LLM_MODEL_*` (optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`) | OpenRouter primary; per-task routing (§45) |
| Research | `RESEARCH_ENABLED`, `RESEARCH_MAX_PAGES`, `RESEARCH_TIMEOUT_SECONDS` | Outbound fetching |
| Uploads | `MAX_UPLOAD_MB`, `ALLOWED_UPLOAD_EXTENSIONS` | |
| Security | `RATE_LIMIT_PER_MINUTE`, `ACCESS_TOKEN_EXPIRE_MINUTES` | |

## Docker Compose (local, full stack)

```bash
cp .env.example .env
docker compose up --build -d
```

Services: `postgres` (16), `qdrant`, `minio`, `backend` (FastAPI), `frontend`
(nginx). On startup the backend runs `python -m app.db_init`, which creates the
schema and seeds templates + the demo account (idempotent).

- Frontend: http://localhost:5173
- API + OpenAPI docs: http://localhost:8000/api/docs
- MinIO console: http://localhost:9001

This local stack is independent of the hosted droplet. It starts its own
Postgres, Qdrant, and MinIO.

## Hosted droplet (shared with Shortlisted)

Serah is hosted on the same DigitalOcean droplet as Shortlisted:

- Product: **https://serah.useshortlisted.app**
- Shortlisted: https://platform.useshortlisted.app
- Droplet: `165.22.93.12`
- Remote tree: `/opt/serah` (Shortlisted stays at `/opt/shortlisted`)

**Shared (one instance, owned by Shortlisted):** Postgres, MinIO, Caddy.
**Serah-only:** Qdrant, backend, frontend.

A Serah deploy does not recreate Shortlisted containers. A Shortlisted deploy
does not stop Serah. Each app has its own Compose project (`serah` vs
Shortlisted’s) and `--remove-orphans` cannot cross that boundary.

### First-time setup

1. DNS: A record `serah.useshortlisted.app` → `165.22.93.12`, **DNS only**
   (grey cloud) so Let’s Encrypt HTTP-01 can complete.
2. Deploy Shortlisted infra **first** (shared network + Caddy `import` of
   `/opt/caddy/sites/*.caddy`):
   ```powershell
   cd e:\projects\Shortlisted
   .\scripts\deploy.ps1
   ```
3. Copy [`infra/compose/.env.example`](../infra/compose/.env.example) to
   `infra/compose/.env`. Set a strong `SECRET_KEY` and `SERAH_DB_PASSWORD`
   (URL-safe). Copy `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` from
   `/opt/shortlisted/infra/compose/.env` on the VM (or the compose defaults
   `minio` / `minio123`).
4. Google Cloud Console: add Authorized JavaScript origin
   `https://serah.useshortlisted.app` (no trailing slash) if Google Sign-In
   is enabled.
5. Deploy Serah:
   ```powershell
   cd e:\projects\ApplicantCompanion
   .\scripts\deploy.ps1 -SyncEnv
   ```

The Serah script creates Postgres role `serah` and database
`applicant_companion` on the existing instance, starts Qdrant + backend +
frontend, writes `/opt/caddy/sites/serah.caddy`, and reloads Caddy.

### Ongoing deploys

```powershell
cd e:\projects\ApplicantCompanion
.\scripts\deploy.ps1              # keep VM .env
.\scripts\deploy.ps1 -SyncEnv     # replace VM .env from local
.\scripts\deploy.ps1 -NoCache     # rebuild images from scratch
.\scripts\deploy.ps1 -Status      # health only
```

Override host/user with `-Target`, `-User`, `-IdentityFile`, or `DEPLOY_HOST`
/ `DEPLOY_USER` / `DEPLOY_SSH_KEY`.

Loopback health (not public): `http://127.0.0.1:8010/api/health`.
Public health: `https://serah.useshortlisted.app/api/health`.

Hosted env template: [`infra/compose/.env.example`](../infra/compose/.env.example).
Compose file: [`infra/compose/docker-compose.hosted.yml`](../infra/compose/docker-compose.hosted.yml).

## Standalone (no Docker)

The application detects missing infrastructure and falls back: SQLite for the
database, an in-process vector store, the local filesystem for objects, and the
deterministic offline LLM provider. The full pipeline works in this mode.

```bash
cd backend && pip install -r requirements.txt
python -m app.db_init
uvicorn app.main:app --host 0.0.0.0 --port 8000

cd ../frontend && npm install && npm run build
# serve frontend/dist with any static server proxying /api to :8000
```

For SQLite in production-like single-user use, set
`DATABASE_URL=sqlite:////data/app.db` on a persistent volume. For multi-process
API deployments, switch the background runner to Celery/Redis (the seam is
`workers/runner.py: submit`) and use PostgreSQL + Qdrant so all state is shared.

## Migrations

```bash
cd backend
alembic upgrade head                     # apply
alembic revision --autogenerate -m "…"   # create a new migration after model changes
```

## Production checklist

1. `APP_ENV=production` (enables DNS validation in the SSRF guard).
2. Strong `SECRET_KEY`; real PostgreSQL/Qdrant/MinIO URLs.
3. HTTPS in front (reverse proxy terminating TLS).
4. `SEED_DEMO_DATA=false` and a unique `SEED_USER_PASSWORD` — or register the
   first account and rotate credentials immediately.
5. `OPENROUTER_API_KEY` + `EMBEDDING_PROVIDER=openrouter` for best retrieval quality.
6. Restrict egress to required domains if your platform supports it.
