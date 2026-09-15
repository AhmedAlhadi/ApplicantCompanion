# Architecture

## High-level design (§4)

```
                    ┌──────────────────────┐
                    │   React + TS UI      │   (Vite, nginx in Docker)
                    └──────────┬───────────┘
                               │  REST / SSE
                    ┌──────────▼───────────┐
                    │       FastAPI        │
                    │   Application Layer  │
                    └──────────┬───────────┘
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
 Career Knowledge       Job Intelligence        Document Engine
     Service                Service                 Service
        │                      │                      │
        ▼                      ▼                      ▼
 PostgreSQL              AI Agent Layer         Templates/Renderer
 Qdrant (vectors)        Research Engine        PDF / DOCX export
 MinIO (objects)         Scoring Engine
```

The repository is a monorepo:

```
backend/
  app/
    api/            # REST routers (§52)
    agents/         # specialized agents + orchestrator (§5, §39)
    llm/            # provider abstraction + router + deterministic mock (§3)
    prompts/        # prompt registry loader (§37)
    prompts/ (dir)  # versioned prompt files <name>/<version>/{system,user}.txt
    retrieval/      # embeddings, vector stores, hybrid pipeline (§35-36)
    scoring/        # programmatic scoring engine (§18)
    security/       # auth, SSRF, injection, uploads, rate limiting (§42-43)
    services/       # ingestion, documents, research, settings, storage
    templates/      # data-driven themes + renderer (§28)
    export/         # PDF / DOCX (§50)
    workers/        # background runner + SSE fan-out (§53)
    models/         # SQLAlchemy models (§51)
    schemas/        # Pydantic API + agent output schemas (§38)
  alembic/          # migrations
  tests/            # unit / API / security / scoring / E2E (§56-57)
frontend/
  src/pages/        # Dashboard, Career Knowledge, Jobs, Job Intelligence,
                    # Applications, Documents, Templates, Settings, AI Config
docs/
```

## Agent architecture (§5)

Specialized agents, each an independent module with its own versioned prompt
and structured Pydantic output — coordinated by `agents/orchestrator.py`:

```
CareerKnowledgeAgent          → text → structured entities + provenance
CareerNormalizationAgent      → skill dedup/canonicalization (§7)
… (matching uses skills and professional knowledge separately)
JobAnalysisAgent              → JD → position info, prioritized requirements
OrganizationResearchAgent     → sourced claims about the employer (§12)
HiringTeamResearchAgent       → public hiring-team identification (§13-14)
CandidateMatchingAgent        → requirement × evidence verdicts (§15-17)
ScoringEngine (no LLM)        → weighted, explainable score (§18)
ScoringNarrativeAgent         → qualitative overlay only
ApplicationStrategyAgent      → positioning, priorities, keywords (§22)
CVAgent / CoverLetterAgent    → evidence-cited documents (§23-27)
ATSAnalysisAgent              → compatibility analysis (§25)
```

## Orchestration (§39, §53)

Two workflows run in a background thread pool (`workers/runner.py`, a
Celery-shaped seam — swap `submit()` for a real task queue in multi-process
deployments):

- `job_analysis`: ParseJD → ResearchOrganization → ResearchHiringContext →
  RetrieveCandidateEvidence → MatchRequirements → CalculateScore
- `document_generation`: GenerateApplicationStrategy → AwaitUserDecision →
  GenerateCV → ValidateCV → GenerateCoverLetter → ValidateDocuments →
  ReadyForReview

Every stage is persisted on a `WorkflowRun` row with
PENDING/RUNNING/COMPLETED/FAILED/SKIPPED and streamed to the UI over SSE
(with polling fallback). Agent failures degrade gracefully — research failure
never blocks matching or generation (§54).

## Retrieval (§35-36)

`Query → normalization → embedding → vector search → SQL metadata filter →
keyword re-rank → dedup → top-N evidence`.

- Embeddings: deterministic feature-hashing (offline/default), OpenRouter, or OpenAI.
- Vector store: Qdrant in production; an in-process cosine store with the same
  interface for dev/tests. Lazy per-user re-indexing keeps the in-process
  store correct across process restarts.
- Only retrieved evidence — never the whole database — is handed to the LLM.

## Scoring (§18-21)

`scoring/engine.py` computes the score programmatically:
`requirement status → {MATCHED 1.0, PARTIALLY_MATCHED 0.6, TRANSFERABLE 0.5,
NOT_MATCHED 0.0, UNKNOWN excluded}` → importance-weighted per category →
weighted sum with configurable category weights (defaults from the spec).
The LLM produces only the narrative (strengths/gaps/risks). The threshold
(default 80%) gates generation behind an explicit user decision — advisory,
never a rejection (§21).

## Documents (§28-31, §50)

Templates are pure data (typography, spacing, sections, colors, layout,
rendering rules) with 7 built-in themes × (CV + cover letter). Generated
documents are structured JSON rendered to preview text, PDF (ReportLab) and
DOCX (python-docx). Every change — generation, section regeneration, user
edit, restore — creates an immutable `DocumentVersion` recording model, prompt
version, inputs and validation results.

## Validation pipeline (§41)

Schema → evidence (every cited `evidence_id` must exist in the KB) →
requirement coverage → ATS → hallucination → language quality. Failures are
surfaced in the editor; hallucination-critical failures mark the document for
review.

## Data model (§51)

32 tables: users, career profile/documents/evidence/narratives, experiences,
achievements, projects, skills, education, certifications, languages,
publications, jobs, job requirements, organizations, organization research,
persons, hiring contexts, requirement matches, job scores, application
strategies, applications, CVs, cover letters, document versions, templates,
agent executions, workflow runs, research sources, user settings, audit logs.
UUID primary keys, `created_at`/`updated_at` everywhere, soft deletion on
user-facing entities.
