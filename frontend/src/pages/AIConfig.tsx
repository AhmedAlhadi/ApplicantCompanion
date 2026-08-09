import { useState } from "react";
import { api } from "../api/client";
import type { AgentExecution } from "../api/types";
import { useApi } from "../components/ui";

const TASK_LABELS: Record<string, string> = {
  extraction: "Extraction",
  classification: "Classification",
  research: "Research synthesis",
  scoring: "Scoring narrative",
  matching: "Candidate matching",
  strategy: "Application strategy",
  cv_generation: "CV generation",
  cover_letter: "Cover-letter generation",
  ats: "ATS analysis",
};

export default function AIConfig() {
  const models = useApi<any>(() => api.get("/api/models"));
  const prompts = useApi<any[]>(() => api.get("/api/prompts"));
  const executions = useApi<AgentExecution[]>(() => api.get("/api/agent-executions?limit=40"));
  const [testResult, setTestResult] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const testProvider = async (provider: string) => {
    setBusy(provider);
    const result = await api.post<any>("/api/models/test", { provider, model: "" });
    setTestResult((prev) => ({ ...prev, [provider]: result }));
    setBusy(null);
  };

  return (
    <>
      <h1 className="page-title">AI / Model Configuration</h1>
      <p className="page-sub">Provider-agnostic LLM layer (§3) with per-task model routing for cost control (§45).</p>

      <div className="grid cols-2">
        <div className="panel">
          <h3>Providers</h3>
          <table>
            <thead><tr><th>Provider</th><th>Configured</th><th>Available</th><th></th></tr></thead>
            <tbody>
              {Object.entries(models.data?.providers ?? {}).map(([name, info]: [string, any]) => (
                <tr key={name}>
                  <td style={{ textTransform: "capitalize" }}>{name}</td>
                  <td>{info.configured ? <span className="badge verified">yes</span> : <span className="badge UNKNOWN">no key</span>}</td>
                  <td>{info.available ? <span className="badge verified">available</span> : <span className="badge NOT_MATCHED">unavailable</span>}</td>
                  <td><button className="sm" onClick={() => testProvider(name)} disabled={busy === name}>Test</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {Object.entries(testResult).map(([provider, r]) => (
            <p key={provider} className="small" style={{ color: r.ok ? "var(--ok)" : "var(--danger)" }}>
              {provider}: {r.ok ? `OK (${r.provider}:${r.model})` : r.detail}
            </p>
          ))}
          <p className="small muted mt">
            Configure providers via environment variables (OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_BASE_URL) and route
            tasks with LLM_MODEL_* settings. Without keys, the deterministic offline provider runs the full pipeline.
          </p>
        </div>

        <div className="panel">
          <h3>Task routing (§45)</h3>
          <table>
            <thead><tr><th>Task</th><th>Model</th></tr></thead>
            <tbody>
              {Object.entries(models.data?.routing ?? {}).map(([task, spec]) => (
                <tr key={task}>
                  <td>{TASK_LABELS[task] ?? task}</td>
                  <td className="mono small">{String(spec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Prompt registry (§37)</h3>
        <div className="pill-list">
          {prompts.data?.map((p) => (
            <span className="pill" key={p.name}>{p.name} <span className="muted">({p.versions.join(", ")})</span></span>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Agent execution log (§40)</h3>
        <table>
          <thead><tr><th>Agent</th><th>Model</th><th>Prompt</th><th>Status</th><th>Duration</th><th>Tokens</th><th>When</th></tr></thead>
          <tbody>
            {executions.data?.map((e) => (
              <tr key={e.id}>
                <td>{e.agent_name}</td>
                <td className="mono small">{e.model}</td>
                <td className="small muted">{e.prompt_name} {e.prompt_version}</td>
                <td><span className={`badge ${e.status}`}>{e.status}</span></td>
                <td className="small">{Math.round(e.duration_ms)} ms</td>
                <td className="small muted">{(e.token_usage?.prompt_tokens ?? 0) + (e.token_usage?.completion_tokens ?? 0)}</td>
                <td className="small muted">{new Date(e.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
