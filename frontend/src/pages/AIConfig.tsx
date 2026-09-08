import { useState } from "react";
import { api } from "../api/client";
import type { AgentExecution } from "../api/types";
import { useApi } from "../components/ui";
import { useT } from "../lib/i18n";

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
  const { t } = useT();
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
      <h1 className="page-title">{t("ai.title")}</h1>
      <p className="page-sub">{t("ai.sub")}</p>

      <div className="grid cols-2">
        <div className="panel">
          <h3>{t("ai.providers")}</h3>
          <table>
            <thead><tr><th>{t("ai.provider")}</th><th>{t("ai.configured")}</th><th>{t("ai.available")}</th><th></th></tr></thead>
            <tbody>
              {Object.entries(models.data?.providers ?? {}).map(([name, info]: [string, any]) => (
                <tr key={name}>
                  <td style={{ textTransform: "capitalize" }}>{name}</td>
                  <td>{info.configured ? <span className="badge verified">{t("common.yes")}</span> : <span className="badge UNKNOWN">{t("ai.noKey")}</span>}</td>
                  <td>{info.available ? <span className="badge verified">{t("ai.available")}</span> : <span className="badge NOT_MATCHED">{t("ai.unavailable")}</span>}</td>
                  <td><button className="sm" onClick={() => testProvider(name)} disabled={busy === name}>{t("ai.test")}</button></td>
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
            {t("ai.hint")}
          </p>
        </div>

        <div className="panel">
          <h3>{t("ai.routing")}</h3>
          <table>
            <thead><tr><th>{t("ai.task")}</th><th>{t("ai.model")}</th></tr></thead>
            <tbody>
              {Object.entries(models.data?.routing ?? {}).map(([task, spec]) => (
                <tr key={task}>
                  <td>{t(`ai.tasks.${task}`) !== `ai.tasks.${task}` ? t(`ai.tasks.${task}`) : (TASK_LABELS[task] ?? task)}</td>
                  <td className="mono small">{String(spec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>{t("ai.promptRegistry")}</h3>
        <div className="pill-list">
          {prompts.data?.map((p) => (
            <span className="pill" key={p.name}>{p.name} <span className="muted">({p.versions.join(", ")})</span></span>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>{t("ai.execLog")}</h3>
        <table>
          <thead><tr><th>{t("ai.agent")}</th><th>{t("ai.model")}</th><th>{t("ai.prompt")}</th><th>{t("applications.status")}</th><th>{t("ai.duration")}</th><th>{t("ai.tokens")}</th><th>{t("ai.when")}</th></tr></thead>
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
