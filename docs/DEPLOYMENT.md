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

## Docker Compose (recommended)

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
