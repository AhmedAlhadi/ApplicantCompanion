# REST API Reference

Base URL: `/api`. All endpoints except `/auth/*` and `/health` require
`Authorization: Bearer <token>`. Request/response validation uses Pydantic
schemas (§52). Interactive OpenAPI docs are served at `/api/docs`.

## Auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create the first (admin) user; closed afterwards |
| POST | `/api/auth/login` | Email + password → JWT |
| GET | `/api/auth/me` | Current user |

## Career Knowledge (§47)

`/api/career/<entity>` for `experiences`, `achievements`, `projects`, `skills`,
`education`, `certifications`, `languages`, `publications`, `narratives`.
Professional knowledge (industry, process, and cross-functional exposure) uses
`/api/career/knowledge`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/career/<entity>` | List (soft-deleted excluded) |
| POST | `/api/career/<entity>` | Create (records provenance, updates vector index) |
| PUT | `/api/career/<entity>/{id}` | Update |
| DELETE | `/api/career/<entity>/{id}` | Soft delete |
| POST | `/api/career/<entity>/{id}/verify?status_value=verified` | Verification status |
| GET/POST | `/api/career/knowledge` | List / create evidenced domain and process knowledge |
| PUT/DELETE | `/api/career/knowledge/{id}` | Update / soft-delete |
| POST | `/api/career/knowledge/{id}/verify` | Verification status |
| POST | `/api/career/knowledge/{id}/contexts` | Link knowledge to a role, project, achievement, or education |
| DELETE | `/api/career/knowledge-contexts/{id}` | Soft-delete a knowledge context |

Plus:

| Method | Path | Description |
|---|---|---|
| GET/PUT | `/api/career/profile` | Professional profile |
| GET/POST | `/api/career/documents` | List / upload (multipart; validated §42) |
| POST | `/api/career/documents/{id}/ingest` | Run extraction agent over the document |
| POST | `/api/career/ingest-text` | Paste text → structured knowledge |
| GET | `/api/career/evidence/{entity_type}/{entity_id}` | Provenance for a claim (§32) |
| GET | `/api/career/search?q=…&limit=…` | Hybrid semantic search (§35) |

## Jobs (§48)

| Method | Path | Description |
|---|---|---|
| POST | `/api/jobs` | Create from pasted JD / URL / notes |
| GET | `/api/jobs` | List (with latest fit score) |
| GET/PUT/DELETE | `/api/jobs/{id}` | Read / update / soft-delete |
| POST | `/api/jobs/{id}/analyze` | Start analysis workflow (202; background) |
| GET | `/api/jobs/{id}/analysis` | Parsed JD + requirements matrix with matches |
| GET | `/api/jobs/{id}/score` | Transparent score breakdown (§19) |
| GET | `/api/jobs/{id}/research` | Organization + hiring-team intelligence |
| GET | `/api/jobs/{id}/workflow` | Latest workflow run + stage statuses |

## Applications (§49)

| Method | Path | Description |
|---|---|---|
| POST | `/api/applications` | Create for a job (idempotent per job) |
| GET | `/api/applications` | List with job + scores |
| GET/PUT/DELETE | `/api/applications/{id}` | Read / update status, notes, lessons / delete |
| GET/POST | `/api/applications/{id}/strategy` | Read / (re)generate application strategy (§22) |
| POST | `/api/applications/{id}/decide` | `continue` / `cancel` / `review_gaps` below threshold (§20) |
| POST | `/api/applications/{id}/generate-cv` | 202 background; 409 `BELOW_THRESHOLD` if undecided |
| POST | `/api/applications/{id}/generate-cover-letter` | Same |
| POST | `/api/applications/{id}/generate-all` | Same |
| GET | `/api/applications/{id}/documents` | Documents + current versions |
| GET | `/api/applications/{id}/workflow` | Generation workflow progress |

## Documents (§29-32, §50)

| Method | Path | Description |
|---|---|---|
| GET | `/api/documents/{id}` | Document + current version + version list |
| PUT | `/api/documents/{id}` | Save user edit as a new version |
| POST | `/api/documents/{id}/regenerate-section` | Regenerate one section, preserve the rest |
| POST | `/api/documents/{id}/restore/{version}` | Restore an older version |
| GET | `/api/documents/{id}/evidence` | Traceability panels for cited evidence |
| POST | `/api/documents/{id}/export?fmt=pdf|docx` | Export with template theme applied |

ATS analysis is advisory. Users who work in professions that do not use
applicant-tracking systems can hide ATS scores in Settings (`ats_relevance=low`).
Documents remain scannable without forcing software-industry vocabulary.

| GET/POST | `/api/coach/conversations` | List / create Career Coach threads |
| GET/DELETE | `/api/coach/conversations/{id}` | Read / soft-delete a thread (owner only) |
| POST | `/api/coach/conversations/{id}/messages` | Ask a grounded question (stricter rate limit) |
| POST | `/api/coach/conversations/{id}/messages/stream` | Same answer as SSE (`data:` JSON then `[DONE]`) |

Coach answers ground on the signed-in user's top retrieved evidence plus a
deterministic context bundle: knowledge-base aggregates (counts, top skills,
experiences, education, certifications, languages), the job's computed
match/score analysis, the application strategy, and excerpts of current
CV/cover-letter versions. Citation IDs are resolved server-side from the
retrieved set only. Message bodies are not written to the ordinary audit log.

## Platform

| Method | Path | Description |
|---|---|---|
| GET | `/api/templates?document_type=cv` | Built-in themes (7 × CV + 7 × cover letter) |
| GET | `/api/dashboard/stats` | Pipeline stats (§33) |
| GET/PUT | `/api/settings` | Score threshold, configurable weights, optional ATS emphasis, templates (§18-20) |
| GET | `/api/models` | Provider availability + task routing (§45) |
| POST | `/api/models/test` | Connectivity test for a provider |
| GET | `/api/prompts` | Prompt registry inventory (§37) |
| GET | `/api/agent-executions` | Agent audit log (§40; raw prompts/outputs excluded) |
| GET | `/api/workflows/{id}/events` | SSE live progress stream (§53) |
| GET | `/api/health` | Liveness |

## Error model

Errors return `{"detail": ...}`. The below-threshold gate returns **409** with
`detail.code == "BELOW_THRESHOLD"`, the score, the threshold, the gap list and
the allowed actions (`continue`, `cancel`, `review_gaps`).
