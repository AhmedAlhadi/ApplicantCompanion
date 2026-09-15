# Serah

**Job-seeker workspace from Shortlisted** — give the system your career history
once; for every new vacancy it parses the JD, researches the organization,
matches your evidence, honestly scores your fit, and generates a targeted CV
and cover letter **without inventing anything**.

Built to the specification in [`AppSpecs.md`](./AppSpecs.md).

Each account has its own career knowledge, jobs, and applications. The first
user is the workspace admin; they can create further accounts from **Admin →
Users**. Sign-in is email/password and, optionally, **Google**. Resume and
cover-letter themes live in **Settings** (avatar menu), not as separate pages.

## Core principles (enforced in code)

1. **Evidence first** — every generated claim traces back to your Career Knowledge Base (`CareerEvidence` provenance ledger + "View Evidence" UI).
2. **Retrieval before generation** — hybrid semantic + keyword + SQL retrieval selects the evidence *before* any document is written.
3. **Transparent scoring** — the job-fit score is computed **programmatically** from structured requirement matches; the LLM only writes the narrative.
4. **Human-in-the-loop** — below-threshold scores ask before generating; documents are always editable, versioned and restorable.
5. **Anti-hallucination** — the validation pipeline rejects documents citing non-existent evidence.
6. **Modular agents** — 11 specialized agents coordinated by an orchestrator, with per-execution audit logs.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite |
| Backend | Python 3.12 + FastAPI (REST + SSE) |
| Database | PostgreSQL 16 (SQLite for zero-dependency dev/tests) |
| Vector store | Qdrant (in-process fallback for dev/tests) |
| Object storage | MinIO / S3 (local filesystem fallback) |
| LLMs | Provider-agnostic: OpenAI, Gemini, Ollama, deterministic offline mock |
| Export | PDF (ReportLab), DOCX (python-docx) |

## Quick start

### Option A — Docker (full stack: PostgreSQL + Qdrant + MinIO)

```bash
cp .env.example .env          # adjust secrets; set GOOGLE_CLIENT_ID to enable Google Sign-In
docker compose up --build
# Frontend: http://localhost:5173   Backend API: http://localhost:8000/api/docs
```

### Option B — Local, zero infrastructure

The app detects missing infrastructure and falls back to SQLite, an in-process
vector store, the local filesystem, and the deterministic offline LLM — the
entire pipeline still works, with no API keys:

**Windows (PowerShell):**

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db_init                                    # schema + seed data
uvicorn app.main:app --reload                            # http://localhost:8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                                              # http://localhost:5173
```

**Linux/macOS:**

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.db_init && uvicorn app.main:app --reload
cd ../frontend && npm install && npm run dev
```

Seeded login: **demo@example.com / demo-password-123** (override with
`SEED_USER_EMAIL` / `SEED_USER_PASSWORD`; demo career data via `SEED_DEMO_DATA=false`).
That seed user is the workspace admin.

## Accounts and Google Sign-In

- **First user** — `POST /api/auth/register` is open only while the database has
  no users; that account is admin. After that, email registration returns 403.
- **Later users** — an admin creates password accounts in the UI (`/admin/users`)
  or anyone with Google can sign in (new Google users are non-admins). Matching
  emails are linked so the same person can use both methods.
- **Google** — set `GOOGLE_CLIENT_ID` in `.env` to a [Google Identity Services](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
  **Web application** client ID. In Google Cloud Console → Credentials, add these
  **Authorized JavaScript origins** (no trailing slash): `http://localhost:5173`
  and `http://127.0.0.1:5173`. Redirect URIs are not required for this ID-token
  flow. Leave the env var empty to hide the button. The backend verifies the ID
  token; no client secret is required.
- **Isolation** — every query is scoped by `user_id`. Admins manage **accounts
  only**; they cannot open another user’s jobs or career data.
- **UI** — Settings, AI / model config, and Admin are in the avatar menu
  (top-right). The sidebar is Dashboard, Career, Jobs, Applications, Documents.

Default CV and cover-letter themes are chosen on the Settings page and used when
generating new documents (you can still switch a document’s theme in the editor).

## Using real LLMs

OpenRouter is the primary provider. Set your key in `.env` and route tasks to
OpenRouter model IDs (`org/model`) — cheaper models for extraction and
classification, stronger ones for generation (§45 cost management):

```bash
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL_EXTRACTION=openrouter:openai/gpt-4o-mini
LLM_MODEL_MATCHING=openrouter:openai/gpt-4o-mini
LLM_MODEL_CV_GENERATION=openrouter:openai/gpt-4o
LLM_MODEL_COVER_LETTER=openrouter:openai/gpt-4o
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-3-small
```

Optional direct providers (`openai`, `gemini`, `ollama`) remain available.
Any task whose provider is unavailable automatically falls back to the
deterministic offline provider and the fallback is recorded in the agent
execution log.

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest tests/ -q    # Windows
# .venv/bin/python -m pytest tests/ -q      # Linux/macOS
```

Includes the deterministic scoring fixtures of §56 and the full end-to-end
acceptance pipeline of §57 (JD → analysis → matching → scoring → strategy →
CV + cover letter → validation → export).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, agents, orchestration, retrieval
- [docs/API.md](docs/API.md) — REST API reference
- [docs/SECURITY.md](docs/SECURITY.md) — security model (SSRF, injection, auth, uploads)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — deployment & configuration guide
- [docs/WORKFLOWS.md](docs/WORKFLOWS.md) — example job-analysis and CV-generation workflows
