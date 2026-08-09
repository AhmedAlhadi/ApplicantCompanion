# Example Workflows (§64)

## 1. Job-analysis workflow (§9, §57)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"demo-password-123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 1. Create the job from a pasted JD
JOB=$(curl -s -X POST localhost:8000/api/jobs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d @examples/job.json | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2. Run analysis (background): parse JD → research → match → score
curl -s -X POST localhost:8000/api/jobs/$JOB/analyze \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"include_research": true}'
# → {"status":"accepted","workflow_run_id":"…"}

# 3. Watch stage progress (SSE) or poll
curl -N localhost:8000/api/workflows/$RUN/events -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/api/jobs/$JOB/workflow -H "Authorization: Bearer $TOKEN"

# 4. Read results
curl -s localhost:8000/api/jobs/$JOB/analysis -H "Authorization: Bearer $TOKEN"   # requirements matrix
curl -s localhost:8000/api/jobs/$JOB/score    -H "Authorization: Bearer $TOKEN"   # explainable score
curl -s localhost:8000/api/jobs/$JOB/research -H "Authorization: Bearer $TOKEN"   # org + hiring team
```

Pipeline stages: `ParseJD → ResearchOrganization → ResearchHiringContext →
RetrieveCandidateEvidence → MatchRequirements → CalculateScore`.

Example score output (demo data vs. the seeded UNICEF JD): overall **0.91**,
recommendation `strong_fit`, with per-category breakdown, strong matches,
partial matches, gaps, transferable items, risks and advantages.

## 2. CV-generation workflow (§22-31)

```bash
# 1. Create the application and its strategy
APP=$(curl -s -X POST localhost:8000/api/applications \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"job_id\": \"$JOB\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/api/applications/$APP/strategy -H "Authorization: Bearer $TOKEN"

# 2. Generate both documents (409 BELOW_THRESHOLD first if score < threshold —
#    confirm via /decide to proceed; the score never hard-blocks)
curl -s -X POST localhost:8000/api/applications/$APP/decide \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"decision": "continue"}'
curl -s -X POST localhost:8000/api/applications/$APP/generate-all \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"template_key": "international-un"}'

# 3. Inspect documents, validation, ATS analysis, evidence traceability
curl -s localhost:8000/api/applications/$APP/documents -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/api/documents/$DOC/evidence -H "Authorization: Bearer $TOKEN"

# 4. Edit → new version; regenerate one section; restore; export
curl -s -X PUT localhost:8000/api/documents/$DOC -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content": …}'
curl -s -X POST localhost:8000/api/documents/$DOC/regenerate-section \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"section": "summary"}'
curl -s -X POST localhost:8000/api/documents/$DOC/restore/1 -H "Authorization: Bearer $TOKEN"
curl -s -X POST "localhost:8000/api/documents/$DOC/export?fmt=pdf" \
  -H "Authorization: Bearer $TOKEN" -o cv.pdf
curl -s -X POST "localhost:8000/api/documents/$DOC/export?fmt=docx" \
  -H "Authorization: Bearer $TOKEN" -o cv.docx
```

## 3. Career ingestion workflow (§6)

```bash
# Upload a CV file → extract structured knowledge with provenance
curl -s -X POST localhost:8000/api/career/documents \
  -H "Authorization: Bearer $TOKEN" -F "file=@my_cv.pdf" -F "doc_type=cv"
curl -s -X POST localhost:8000/api/career/documents/$DOCID/ingest \
  -H "Authorization: Bearer $TOKEN"
# → {"experiences": 3, "skills": 14, "achievements": 5, …}

# …or paste text directly
curl -s -X POST localhost:8000/api/career/ingest-text \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text": "…", "doc_type": "cv"}'
```

Extracted items arrive as `needs_review`; verify them in the Career Knowledge
UI so generated documents can rely on them.
