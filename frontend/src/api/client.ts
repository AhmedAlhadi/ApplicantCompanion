// API client — the token lives in localStorage only (never in code) and every
// request goes to the backend; no API keys exist in the frontend (§42).

import type { CareerDocument, IngestResult } from "./types";

const TOKEN_KEY = "ac_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  formData?: FormData
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined && !formData) headers["Content-Type"] = "application/json";

  const resp = await fetch(path, {
    method,
    headers,
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  const publicAuth =
    path === "/api/auth/login" ||
    path === "/api/auth/register" ||
    path === "/api/auth/google" ||
    path === "/api/auth/config";
  if (resp.status === 401 && token && !publicAuth) {
    setToken(null);
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new ApiError(401, "unauthorized");
  }
  const text = await resp.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!resp.ok) {
    const detail = (data as { detail?: unknown })?.detail ?? data;
    throw new ApiError(resp.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, formData: FormData) => request<T>("POST", path, undefined, formData),
};

export async function waitForCareerIngest(
  documentId: string,
  options?: { intervalMs?: number; timeoutMs?: number }
): Promise<IngestResult> {
  const intervalMs = options?.intervalMs ?? 1200;
  const timeoutMs = options?.timeoutMs ?? 16 * 60 * 1000;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const doc = await api.get<CareerDocument>(`/api/career/documents/${documentId}`);
    if (doc.ingest_status === "completed") {
      const result = doc.ingest_result || {};
      return {
        document_id: documentId,
        pending_ingestion_id: result.pending_ingestion_id ?? null,
        auto_applied: result.auto_applied || {},
        proposals_count: result.proposals_count || 0,
        profile: result.profile,
        created: result.created,
        note: result.note,
      };
    }
    if (doc.ingest_status === "failed") {
      throw new ApiError(500, doc.ingest_error || "Ingestion failed");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new ApiError(504, "Ingestion timed out");
}

export async function downloadFile(path: string, fallbackName: string) {
  const token = getToken();
  const resp = await fetch(path, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
  const blob = await resp.blob();
  const disposition = resp.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match ? match[1] : fallbackName;
  a.click();
  URL.revokeObjectURL(url);
}

export function workflowEventsUrl(id: string): string {
  return `/api/workflows/${id}/events`;
}

/** SSE over fetch so the Bearer token can be sent (native EventSource cannot). */
export function subscribeWorkflowEvents(
  id: string,
  onEvent: (data: unknown) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(workflowEventsUrl(id), {
    method: "GET",
    headers,
    cache: "no-store",
    signal,
  })
    .then(async (resp) => {
      if (!resp.ok || !resp.body) return;
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame
            .split("\n")
            .map((line) => line.replace(/\r$/, ""))
            .find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          const payload = dataLine.startsWith("data: ") ? dataLine.slice(6) : dataLine.slice(5);
          try {
            onEvent(JSON.parse(payload));
          } catch {
            /* ignore malformed frames */
          }
        }
      }
    })
    .catch((err: unknown) => {
      if (signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
    });
}
