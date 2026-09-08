import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FileText, Files, Mail, RefreshCw, Sparkles } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { AppDocument, Application, JobScore, Strategy, Template } from "../api/types";
import { Empty, ErrorBox, ScoreRing, Spinner, useApi, useWorkflow } from "../components/ui";
import ThinkingProgress, { THINKING_PHRASES } from "../components/ThinkingProgress";
import { useT } from "../lib/i18n";

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
  const { t } = useT();
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
          message: t("application.gateMessage"),
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
              : t("application.gateMessage"),
          gaps: Array.isArray(err.detail.gaps) ? err.detail.gaps : [],
        });
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : t("application.generateFailed"));
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
      setError(err instanceof Error ? err.message : t("application.strategyFailed"));
    }
  };

  if (app.loading) return <p className="muted">{t("common.loading")}</p>;
  if (!a) return <Empty>{t("application.notFound")}</Empty>;

  const cvTemplates = (templates.data ?? []).filter((t) => t.document_type === "cv");

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">{a.job?.position_title || "Application"}</h1>
          <p className="page-sub">
            {a.job?.organization_name} {a.job?.location ? `· ${a.job.location}` : ""}{" "}
            <Link to={`/jobs/${a.job_id}`} className="small">{t("application.viewJob")}</Link>
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
          <strong>{t("application.approvalRequired")}</strong>
          <div className="mt">{activeGate.message}</div>
          <div className="small mt">
            {t("application.estimatedFit", { score: Math.round(activeGate.score * 100), threshold: Math.round(activeGate.threshold * 100) })}
            {a.user_approved ? "" : t("application.notApproved")}
          </div>
          {!!activeGate.gaps?.length && (
            <ul className="small" style={{ marginBottom: 0 }}>
              {activeGate.gaps.slice(0, 4).map((g, i) => <li key={i}>{g}</li>)}
            </ul>
          )}
          <div className="row mt">
            <button className="success sm" onClick={() => decide("continue")}>{t("application.continueAnyway")}</button>
            <button className="sm" onClick={() => decide("review_gaps")}>{t("application.reviewGaps")}</button>
            <button className="danger sm" onClick={() => decide("cancel")}>{t("application.cancelApp")}</button>
          </div>
        </div>
      )}
      <ErrorBox error={error} />

      <div className="panel">
        <h3>{t("application.strategy")}</h3>
        {strategy.data ? (
          <>
            <p><strong>{t("application.positioning")}</strong> {strategy.data.positioning}</p>
            <p><strong>{t("application.messaging")}</strong> {strategy.data.messaging_strategy}</p>
            {!!strategy.data.priority_skills?.length && (
              <><div className="small muted mb">{t("application.prioritySkills")}</div>
              <div className="pill-list mb">{strategy.data.priority_skills.map((s) => <span className="pill" key={s}>{s}</span>)}</div></>
            )}
            {!!strategy.data.keywords?.length && (
              <><div className="small muted mb">{t("application.keywords")}</div>
              <div className="pill-list mb">{strategy.data.keywords.map((s) => <span className="pill" key={s}>{s}</span>)}</div></>
            )}
            {!!strategy.data.concerns?.length && (
              <><div className="small muted mb">{t("application.concerns")}</div>
              <ul className="small" style={{ marginTop: 0 }}>{strategy.data.concerns.map((c, i) => <li key={i}>{c}</li>)}</ul></>
            )}
            {!!strategy.data.evidence_plan?.length && (
              <><div className="small muted mb">{t("application.evidencePlan")}</div>
              <ul className="small" style={{ marginTop: 0 }}>{strategy.data.evidence_plan.map((e, i) => <li key={i}>{e.requirement}</li>)}</ul></>
            )}
          </>
        ) : (
          <p className="muted small">{t("application.noStrategy")}</p>
        )}
        <button className="sm mt" onClick={runStrategy} disabled={!!busy}>
          {busy === "strategy" ? <Spinner /> : <RefreshCw aria-hidden />} {strategy.data ? t("application.regenStrategy") : t("application.generateStrategy")}
        </button>
        {busy === "strategy" && (
          <ThinkingProgress phrases={THINKING_PHRASES.strategy} workflow={workflowPoll} />
        )}
      </div>

      <div className="panel">
        <h3>{t("application.generateDocs")}</h3>
        {activeGate && (
          <div className="alert warn mb">
            {t("application.genBlocked", { score: Math.round(activeGate.score * 100), threshold: Math.round(activeGate.threshold * 100) })}
          </div>
        )}
        <div className="row mb">
          <label style={{ margin: 0 }}>{t("application.theme")}</label>
          <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)} style={{ width: "auto" }}>
            {cvTemplates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
        </div>
        <div className="row">
          <button className="primary" onClick={() => generate("cv")} disabled={!!busy || !!activeGate}>{busy === "cv" ? <Spinner /> : <FileText aria-hidden />} {t("application.generateCv")}</button>
          <button onClick={() => generate("cover-letter")} disabled={!!busy || !!activeGate}>{busy === "cover-letter" ? <Spinner /> : <Mail aria-hidden />} {t("application.generateCl")}</button>
          <button onClick={() => generate("all")} disabled={!!busy || !!activeGate}>{busy === "all" ? <Spinner /> : <Sparkles aria-hidden />} {t("application.generateBoth")}</button>
        </div>
        {busy && busy !== "strategy" && (
          <ThinkingProgress phrases={THINKING_PHRASES.docGeneration} workflow={workflowPoll} />
        )}
      </div>

      <div className="panel">
        <h3>{t("application.documents")}</h3>
        {docs.data?.length ? (
          <table>
            <thead><tr><th>{t("application.document")}</th><th>{t("application.template")}</th><th>{t("application.version")}</th><th>{t("application.validation")}</th><th>ATS</th><th></th></tr></thead>
            <tbody>
              {docs.data.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td className="muted">{d.template_key}</td>
                  <td>v{d.current_version?.version_number ?? 0} {d.current_version?.user_edited ? t("editor.edited") : ""}</td>
                  <td>
                    {d.current_version?.validation_results
                      ? Object.values(d.current_version.validation_results.issues ?? {}).length === 0
                        ? <span className="badge verified">{t("application.passed")}</span>
                        : <span className="badge unverified" title={(d.current_version.validation_results.issues ?? []).join("\n")}>{t("application.review")}</span>
                      : "—"}
                  </td>
                  <td>{d.current_version?.ats_analysis?.ats_score != null ? `${Math.round((d.current_version.ats_analysis.ats_score as number) * 100)}%` : "—"}</td>
                  <td><Link to={`/documents/${d.id}`}>{t("application.openEditor")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon={Files}>{t("application.noDocs")}</Empty>
        )}
      </div>

      <div className="panel">
        <h3>{t("application.notes")}</h3>
        <NotesEditor app={a} onSaved={app.reload} />
      </div>
    </>
  );
}

function NotesEditor({ app, onSaved }: { app: Application; onSaved: () => void }) {
  const { t } = useT();
  const [notes, setNotes] = useState(app.user_notes ?? "");
  const [lessons, setLessons] = useState(app.lessons_learned ?? "");
  const [outcome, setOutcome] = useState(app.outcome ?? "");
  return (
    <form onSubmit={async (e) => { e.preventDefault(); await api.put(`/api/applications/${app.id}`, { user_notes: notes, lessons_learned: lessons, outcome }); onSaved(); }}>
      <label>{t("application.userNotes")}</label>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="form-row">
        <div><label>{t("application.outcome")}</label><input value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder={t("application.outcomePh")} /></div>
        <div><label>{t("application.lessons")}</label><input value={lessons} onChange={(e) => setLessons(e.target.value)} /></div>
      </div>
      <button className="primary sm mt">{t("common.save")}</button>
    </form>
  );
}
