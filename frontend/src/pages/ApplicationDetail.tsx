import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { AppDocument, Application, JobScore, Strategy, Template } from "../api/types";
import { Empty, ErrorBox, ProgressBar, ProgressStages, ScoreRing, Spinner, useApi, useWorkflow } from "../components/ui";

type ThresholdGate = {
  code?: string;
  score: number;
  threshold: number;
  message: string;
  gaps: string[];
};

function isThresholdGate(detail: unknown): detail is ThresholdGate {
  return (
    typeof detail === "object" &&
    detail !== null &&
    "score" in detail &&
    "threshold" in detail &&
    typeof (detail as ThresholdGate).score === "number" &&
    typeof (detail as ThresholdGate).threshold === "number"
  );
}

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const app = useApi<Application>(() => api.get(`/api/applications/${id}`), [id]);
  const strategy = useApi<Strategy>(() => api.get(`/api/applications/${id}/strategy`), [id]);
  const docs = useApi<AppDocument[]>(() => api.get(`/api/applications/${id}/documents`), [id]);
  const templates = useApi<Template[]>(() => api.get("/api/templates"));
  const [templateKey, setTemplateKey] = useState("minimal-ats");
  const [busy, setBusy] = useState<string | null>(null);
  const [workflowRunId, setWorkflowRunId] = useState<string | null>(null);
  const [gate, setGate] = useState<ThresholdGate | null>(null);
  const [error, setError] = useState<string | null>(null);

  const a = app.data;
  const score = useApi<JobScore | null>(
    () => (a?.job_id ? api.get<JobScore>(`/api/jobs/${a.job_id}/score`) : Promise.resolve(null)),
    [a?.job_id]
  );

  const workflowPoll = useWorkflow(
    workflowRunId,
    workflowRunId ? `/api/applications/${id}/workflow` : null,
    () => {
      setBusy(null);
      setWorkflowRunId(null);
      docs.reload();
      app.reload();
      strategy.reload();
    },
  );

  const belowThreshold =
    !!score.data &&
    score.data.overall_score < score.data.threshold &&
    !!a &&
    !a.user_approved;

  const activeGate: ThresholdGate | null =
    gate ??
    (belowThreshold
      ? {
          code: "BELOW_THRESHOLD",
          score: score.data!.overall_score,
          threshold: score.data!.threshold,
          message:
            "Generation is blocked until you approve continuing with a below-threshold fit score. " +
            "Approve below to generate documents, or cancel the application.",
          gaps: score.data!.gaps ?? [],
        }
      : null);

  const decide = async (decision: "continue" | "cancel" | "review_gaps") => {
    await api.post(`/api/applications/${id}/decide`, { decision });
    setGate(null);
    setError(null);
    app.reload();
    if (decision === "review_gaps" && a?.job_id) {
      navigate(`/jobs/${a.job_id}`);
    }
  };

  const generate = async (kind: "cv" | "cover-letter" | "all") => {
    setBusy(kind);
    setError(null);
    setGate(null);
    try {
      const accepted = await api.post<{ workflow_run_id: string }>(
        `/api/applications/${id}/generate-${kind}`,
        { template_key: templateKey },
      );
      setWorkflowRunId(accepted.workflow_run_id);
    } catch (err) {
      setBusy(null);
      if (err instanceof ApiError && err.status === 409 && isThresholdGate(err.detail)) {
        setGate({
          ...err.detail,
          message:
            typeof err.detail.message === "string"
              ? err.detail.message
              : "Generation is blocked until you approve the below-threshold fit score.",
          gaps: Array.isArray(err.detail.gaps) ? err.detail.gaps : [],
        });
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Generation failed");
      }
    }
  };

  const runStrategy = async () => {
    setBusy("strategy");
    setError(null);
    try {
      const accepted = await api.post<{ workflow_run_id: string }>(`/api/applications/${id}/strategy`);
      setWorkflowRunId(accepted.workflow_run_id);
    } catch (err) {
      setBusy(null);
      setError(err instanceof Error ? err.message : "Strategy generation failed");
    }
  };

  if (app.loading) return <p className="muted">Loading…</p>;
  if (!a) return <Empty>Application not found.</Empty>;

  const cvTemplates = (templates.data ?? []).filter((t) => t.document_type === "cv");

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">{a.job?.position_title || "Application"}</h1>
          <p className="page-sub">
            {a.job?.organization_name} {a.job?.location ? `· ${a.job.location}` : ""}{" "}
            <Link to={`/jobs/${a.job_id}`} className="small">View job intelligence →</Link>
          </p>
        </div>
        <span className={`badge ${a.status}`} style={{ fontSize: 13 }}>{a.status}</span>
      </div>

      {a.fit_score != null && (
        <div className="panel">
          <ScoreRing score={a.fit_score} threshold={score.data?.threshold} />
        </div>
      )}

      {activeGate && (
        <div className="alert warn">
          <strong>Approval required</strong>
          <div className="mt">{activeGate.message}</div>
          <div className="small mt">
            Estimated fit: {Math.round(activeGate.score * 100)}% (threshold {Math.round(activeGate.threshold * 100)}%)
            {a.user_approved ? "" : " — not yet approved"}
          </div>
          {!!activeGate.gaps?.length && (
            <ul className="small" style={{ marginBottom: 0 }}>
              {activeGate.gaps.slice(0, 4).map((g, i) => <li key={i}>{g}</li>)}
            </ul>
          )}
          <div className="row mt">
            <button className="success sm" onClick={() => decide("continue")}>Continue anyway</button>
            <button className="sm" onClick={() => decide("review_gaps")}>Review gaps</button>
            <button className="danger sm" onClick={() => decide("cancel")}>Cancel application</button>
          </div>
        </div>
      )}
      <ErrorBox error={error} />

      <div className="panel">
        <h3>Application Strategy</h3>
        {strategy.data ? (
          <>
            <p><strong>Positioning:</strong> {strategy.data.positioning}</p>
            <p><strong>Messaging:</strong> {strategy.data.messaging_strategy}</p>
            {!!strategy.data.priority_skills?.length && (
              <><div className="small muted mb">Priority skills</div>
              <div className="pill-list mb">{strategy.data.priority_skills.map((s) => <span className="pill" key={s}>{s}</span>)}</div></>
            )}
            {!!strategy.data.keywords?.length && (
              <><div className="small muted mb">Keywords to use naturally</div>
              <div className="pill-list mb">{strategy.data.keywords.map((s) => <span className="pill" key={s}>{s}</span>)}</div></>
            )}
            {!!strategy.data.concerns?.length && (
              <><div className="small muted mb">Concerns to address</div>
              <ul className="small" style={{ marginTop: 0 }}>{strategy.data.concerns.map((c, i) => <li key={i}>{c}</li>)}</ul></>
            )}
            {!!strategy.data.evidence_plan?.length && (
              <><div className="small muted mb">Evidence plan</div>
              <ul className="small" style={{ marginTop: 0 }}>{strategy.data.evidence_plan.map((e, i) => <li key={i}>{e.requirement}</li>)}</ul></>
            )}
          </>
        ) : (
          <p className="muted small">No strategy yet.</p>
        )}
        <button className="sm mt" onClick={runStrategy} disabled={!!busy}>
          {busy === "strategy" ? <Spinner /> : null} {strategy.data ? "Regenerate strategy" : "Generate strategy"}
        </button>
        {busy === "strategy" && (
          <div className="mt">
            <ProgressBar label="Generating application strategy…" />
            <ProgressStages workflow={workflowPoll} />
          </div>
        )}
      </div>

      <div className="panel">
        <h3>Generate Documents</h3>
        {activeGate && (
          <div className="alert warn mb">
            Document generation is blocked until you approve the below-threshold fit score
            ({Math.round(activeGate.score * 100)}% &lt; {Math.round(activeGate.threshold * 100)}%).
          </div>
        )}
        <div className="row mb">
          <label style={{ margin: 0 }}>Theme</label>
          <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)} style={{ width: "auto" }}>
            {cvTemplates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
        </div>
        <div className="row">
          <button className="primary" onClick={() => generate("cv")} disabled={!!busy || !!activeGate}>{busy === "cv" ? <Spinner /> : null} Generate Targeted CV</button>
          <button onClick={() => generate("cover-letter")} disabled={!!busy || !!activeGate}>{busy === "cover-letter" ? <Spinner /> : null} Generate Cover Letter</button>
          <button onClick={() => generate("all")} disabled={!!busy || !!activeGate}>{busy === "all" ? <Spinner /> : null} Generate Both</button>
        </div>
        {busy && busy !== "strategy" && (
          <div className="mt">
            <ProgressBar label={busy === "all" ? "Generating CV and cover letter…" : `Generating ${busy.replace("-", " ")}…`} />
            <ProgressStages workflow={workflowPoll} />
          </div>
        )}
      </div>

      <div className="panel">
        <h3>Documents</h3>
        {docs.data?.length ? (
          <table>
            <thead><tr><th>Document</th><th>Template</th><th>Version</th><th>Validation</th><th>ATS</th><th></th></tr></thead>
            <tbody>
              {docs.data.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td className="muted">{d.template_key}</td>
                  <td>v{d.current_version?.version_number ?? 0} {d.current_version?.user_edited ? "(edited)" : ""}</td>
                  <td>
                    {d.current_version?.validation_results
                      ? Object.values(d.current_version.validation_results.issues ?? {}).length === 0
                        ? <span className="badge verified">passed</span>
                        : <span className="badge unverified" title={(d.current_version.validation_results.issues ?? []).join("\n")}>review</span>
                      : "—"}
                  </td>
                  <td>{d.current_version?.ats_analysis?.ats_score != null ? `${Math.round((d.current_version.ats_analysis.ats_score as number) * 100)}%` : "—"}</td>
                  <td><Link to={`/documents/${d.id}`}>Open editor</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No documents generated yet.</Empty>
        )}
      </div>

      <div className="panel">
        <h3>Notes & Lessons Learned</h3>
        <NotesEditor app={a} onSaved={app.reload} />
      </div>
    </>
  );
}

function NotesEditor({ app, onSaved }: { app: Application; onSaved: () => void }) {
  const [notes, setNotes] = useState(app.user_notes ?? "");
  const [lessons, setLessons] = useState(app.lessons_learned ?? "");
  const [outcome, setOutcome] = useState(app.outcome ?? "");
  return (
    <form onSubmit={async (e) => { e.preventDefault(); await api.put(`/api/applications/${app.id}`, { user_notes: notes, lessons_learned: lessons, outcome }); onSaved(); }}>
      <label>User notes</label>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="form-row">
        <div><label>Outcome</label><input value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="e.g. invited to interview" /></div>
        <div><label>Lessons learned</label><input value={lessons} onChange={(e) => setLessons(e.target.value)} /></div>
      </div>
      <button className="primary sm mt">Save</button>
    </form>
  );
}
