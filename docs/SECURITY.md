# Security Model (§42-43)

This application stores sensitive career and personal information. The threat
model and controls:

## Authentication & authorization

- JWT bearer tokens (HS256, `SECRET_KEY` from env, configurable expiry).
- Passwords hashed with bcrypt. Google Sign-In users may have no password;
  the backend verifies a Google ID token (`GOOGLE_CLIENT_ID`) and issues the
  same JWT. Email/password registration is open **only for the first user**;
  afterwards it returns 403. Google Sign-In can provision later users as
  non-admins. An existing admin can create password accounts via `/api/admin/users`.
- Admin routes (`/api/admin/*`) require `is_admin`. Admins manage accounts only
  and cannot read another user's career, jobs, or applications.
- Every query is scoped by `user_id`; object lookups verify ownership, so users
  can never read each other's career data (tested in `test_security.py` /
  `test_career_api.py`).
- Soft deletion preserves auditability.

## Secrets

- All secrets arrive via environment variables (`.env`, never committed).
- No API keys exist in or are sent to the frontend; LLM calls are backend-only.
- Agent execution logs store input *references* and output *summaries* — raw
  prompts and full outputs are never exposed via the API (§40).

## Prompt-injection protection (§43)

External content (job descriptions, web pages, uploaded documents) is treated
as DATA, never as instructions:

1. **Structural**: every prompt that consumes untrusted content states the rule
   explicitly; content is wrapped in delimited tags.
2. **Sanitization**: `security/injection.py` detects and neutralizes known
   injection phrases ("ignore previous instructions…", "reveal your system
   prompt", fake `system:` turns, …) in the copy sent to the model. The
   original is preserved untouched in the database.
3. **Detection logging**: matches are available for audit.

## SSRF protection (§42)

The research engine fetches external URLs. `security/ssrf.py` validates every
URL before fetching:

- only `http`/`https` schemes;
- no credentials in the URL;
- literal IPs must be public (blocks loopback, RFC-1918, link-local such as
  the `169.254.169.254` cloud metadata endpoint, multicast, reserved);
- in production, DNS resolution is checked against the same rules (rebinding
  defense); hostname resolution is relaxed in dev/test so offline fixtures work;
- research responses are size-limited, time-limited and cached by content hash
  (§44), and HTML is stripped to text before reaching any LLM.

## Upload validation

- Extension allow-list (`.pdf`, `.docx`, `.txt`, `.md`), configurable.
- Size limit (`MAX_UPLOAD_MB`, default 15).
- Magic-byte verification for PDF/DOCX so a renamed executable is rejected.
- Files land in object storage (MinIO/local) — never executed, never served
  with executable content types.

## Rate limiting & transport

- Sliding-window per-IP rate limit middleware (`RATE_LIMIT_PER_MINUTE`).
- CORS restricted to `FRONTEND_ORIGIN`.
- Deploy behind HTTPS (see DEPLOYMENT.md); cookies are not used, so no CSRF
  surface for the API.

## Audit logging (§42, §55)

`audit_logs` records auth events and all mutations (who/what/when/IP) without
recording sensitive payloads. Structured JSON access logs record method, path,
status and latency — never request bodies.
