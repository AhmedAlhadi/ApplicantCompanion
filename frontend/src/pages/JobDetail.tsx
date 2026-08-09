import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Application, JobAnalysisResponse, JobScore, ResearchResponse, WorkflowRun } from "../api/types";
import { Empty, ProgressStages, ScoreRing, Spinner, useApi, useWorkflow } from "../components/ui";

const CATEGORY_LABELS: Record<string, string> = {
  mandatory_qualifications: "Mandatory Requirements",
  relevant_experience: "Relevant Experience",
  technical_skills: "Technical Skills",
  responsibilities: "Responsibilities",
  domain_knowledge: "Domain Knowledge",
  leadership_management: "Leadership",
  education_certifications: "Education",
  language_other: "Languages",
};

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const analysis = useApi<JobAnalysisResponse>(() => api.get(`/api/jobs/${id}/analysis`), [id]);
  const score = useApi<JobScore>(() => api.get(`/api/jobs/${id}/score`), [id]);
  const research = useApi<ResearchResponse>(() => api.get(`/api/jobs/${id}/research`), [id]);
  const [busy, setBusy] = useState(false);
  const [gateError, setGateError] = useState<{ score: number; threshold: number; gaps: string[] } | null>(null);
  const navigate = useNavigate();

  const job = analysis.data?.job;
  const analyzing = job?.status === "analyzing";
  const workflow = useWorkflow(null, analyzing ? `/api/jobs/${id}/workflow` : null, () => {
    analysis.reload();
    score.reload();
    research.reload();
  });

  const runAnalysis = async () => {
    setBusy(true);
    await api.post(`/api/jobs/${id}/analyze`, { include_research: true });
    analysis.reload();
    setBusy(false);
  };

  const startApplication = async () => {
    setBusy(true);
    const app = await api.post<Application>("/api/applications", { job_id: id });
    await api.post(`/api/applications/${app.id}/strategy`);
    navigate(`/applications/${app.id}`);
  };

  if (analysis.loading) return <p className="muted">Loading…</p>;
  if (!job) return <Empty>Job not found.</Empty>;

  const requirements = analysis.data?.requirements ?? [];
  const s = score.data;

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">{job.position_title || "Untitled role"}</h1>
          <p className="page-sub">
            {job.organization_name || "Unknown organization"}
            {job.location ? ` · ${job.location}` : ""}
            {job.contract_type ? ` · ${job.contract_type}` : ""}
            {job.remote_policy ? ` · ${job.remote_policy}` : ""}
            {job.deadline ? ` · deadline ${job.deadline}` : ""}
          </p>
        </div>
        <div className="row">
          <span className={`badge ${job.status}`}>{job.status}</span>
          <button onClick={runAnalysis} disabled={busy || analyzing}>{analyzing ? <Spinner /> : null} Re-analyze</button>
          <button className="primary" onClick={startApplication} disabled={busy || analyzing || !s}>
            Open Application Workspace
          </button>
        </div>
      </div>

      {analyzing && (
        <div className="panel">
          <h3>Analyzing job…</h3>
          <ProgressStages workflow={workflow} />
        </div>
      )}

      {job.executive_summary && (
        <div className="panel">
          <h3>Executive Summary</h3>
          <p style={{ margin: 0 }}>{s?.explanation || job.executive_summary}</p>
        </div>
      )}

      {s && (
        <div className="grid cols-2">
          <div className="panel">
            <h3>Fit Analysis</h3>
            <ScoreRing score={s.overall_score} threshold={s.threshold} />
            <div className="mt">
              {Object.entries(s.category_scores).map(([key, value]) => (
                <div className="score-row" key={key}>
                  <span className="name">{CATEGORY_LABELS[key] ?? key}</span>
                  <div className="score-bar"><div style={{ width: `${Math.round(value * 100)}%` }} /></div>
                  <span className="pct">{Math.round(value * 100)}%</span>
                </div>
              ))}
            </div>
            {s.unknown_count > 0 && (
              <p className="small muted mt">{s.unknown_count} requirement(s) could not be evaluated — add more career evidence to improve accuracy.</p>
            )}
          </div>
          <div className="panel">
            <h3>Strengths & Gaps</h3>
            {[
              ["Strong matches", s.strong_matches, "var(--ok)"],
              ["Partial matches", s.partial_matches, "var(--warn)"],
              ["Transferable experience", s.transferable, "var(--accent)"],
              ["Gaps", s.gaps, "var(--danger)"],
              ["Risks", s.risks, "var(--danger)"],
              ["Competitive advantages", s.advantages, "var(--accent-2)"],
            ].map(([label, items, color]) =>
              (items as string[])?.length ? (
                <div key={label as string} className="mb">
                  <div className="small" style={{ color: color as string, fontWeight: 700 }}>{label as string}</div>
                  <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
                    {(items as string[]).slice(0, 5).map((item, i) => <li key={i} className="small">{item}</li>)}
                  </ul>
                </div>
              ) : null
            )}
          </div>
        </div>
      )}

      {requirements.length > 0 && (
        <div className="panel">
          <h3>Requirements Matrix</h3>
          <table>
            <thead><tr><th style={{ width: "46%" }}>Requirement</th><th>Type</th><th>Importance</th><th>Match</th><th>Evidence</th></tr></thead>
            <tbody>
              {requirements.map((r) => (
                <tr key={r.id}>
                  <td>{r.text}</td>
                  <td className="muted small">{r.requirement_type}</td>
                  <td><span className={`badge ${r.importance}`}>{r.importance}</span></td>
                  <td>{r.match ? <span className={`badge ${r.match.status}`}>{r.match.status.replace("_", " ")}</span> : <span className="badge UNKNOWN">—</span>}</td>
                  <td className="small muted">
                    {r.match?.evidence?.length
                      ? r.match.evidence.slice(0, 2).map((e, i) => <div key={i}>“{e.evidence.slice(0, 110)}{e.evidence.length > 110 ? "…" : ""}”</div>)
                      : r.match?.explanation ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid cols-2">
        <div className="panel">
          <h3>Organization Intelligence</h3>
          {research.data?.organization_research?.length ? (
            research.data.organization_research.map((claim) => (
              <div key={claim.id} className="mb">
                <div className="small">{claim.claim}</div>
                <div className="small muted">
                  <span className={`badge ${claim.confidence === "HIGH" ? "verified" : claim.confidence === "MEDIUM" ? "unverified" : "UNKNOWN"}`}>{claim.confidence}</span>{" "}
                  {claim.source_url && <a href={claim.source_url} target="_blank" rel="noreferrer">source</a>} · {claim.source_type}
                </div>
              </div>
            ))
          ) : (
            <p className="muted small">Research unavailable — offline mode or no public sources found. The analysis above is unaffected (§54).</p>
          )}
        </div>
        <div className="panel">
          <h3>Hiring Team Intelligence</h3>
          {research.data?.people?.length ? (
            research.data.people.map((p) => (
              <div key={p.id} className="mb">
                <div><strong>{p.name}</strong> — {p.role}</div>
                <div className="small muted"><span className={`badge ${p.confidence === "HIGH" ? "verified" : "unverified"}`}>{p.confidence}</span> {p.evidence?.join("; ")}</div>
              </div>
            ))
          ) : (
            <p className="muted small">{research.data?.hiring_context?.notes || "Hiring manager not identified with sufficient confidence."}</p>
          )}
        </div>
      </div>

      {analysis.data?.parsed?.keywords?.length ? (
        <div className="panel">
          <h3>Extracted Keywords</h3>
          <div className="pill-list">
            {analysis.data.parsed.keywords.map((k) => (
              <span className="pill" key={k.term} title={k.classification}>{k.term}</span>
            ))}
          </div>
        </div>
      ) : null}

      {gateError && (
        <div className="alert warn">
          Fit below threshold ({Math.round(gateError.score * 100)}% &lt; {Math.round(gateError.threshold * 100)}%).
        </div>
      )}
    </>
  );
}
