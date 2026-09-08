import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CalendarDays,
  ExternalLink,
  Gauge,
  MapPin,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { api } from "../api/client";
import type { Application, Job, JobAnalysisResponse, JobScore, ResearchResponse } from "../api/types";
import { Empty, ErrorBox, Link, ScoreRing, Spinner, useApi, useWorkflow } from "../components/ui";
import ThinkingProgress, { THINKING_PHRASES } from "../components/ThinkingProgress";
import { EvidenceGraph } from "../components/EvidenceGraph";
import { dateLocale, useT } from "../lib/i18n";

const TAB_KEYS = ["details", "fit", "intelligence"] as const;

type JobTab = (typeof TAB_KEYS)[number];

type JobForm = {
  position_title: string;
  organization_name: string;
  location: string;
  deadline: string;
  contract_type: string;
  remote_policy: string;
  duration: string;
  grade_level: string;
  department: string;
  team: string;
  reporting_line: string;
  source_url: string;
  notes: string;
  raw_jd_text: string;
};

const EMPTY_FORM: JobForm = {
  position_title: "",
  organization_name: "",
  location: "",
  deadline: "",
  contract_type: "",
  remote_policy: "",
  duration: "",
  grade_level: "",
  department: "",
  team: "",
  reporting_line: "",
  source_url: "",
  notes: "",
  raw_jd_text: "",
};

function dash(value: string | null | undefined) {
  const text = (value || "").trim();
  return text || "—";
}

function formFromJob(job: Job): JobForm {
  return {
    position_title: job.position_title || "",
    organization_name: job.organization_name || "",
    location: job.location || "",
    deadline: job.deadline || "",
    contract_type: job.contract_type || "",
    remote_policy: job.remote_policy || "",
    duration: job.duration || "",
    grade_level: job.grade_level || "",
    department: job.department || "",
    team: job.team || "",
    reporting_line: job.reporting_line || "",
    source_url: job.source_url || "",
    notes: job.notes || "",
    raw_jd_text: job.raw_jd_text || "",
  };
}

function formatDeadlineDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return new Date(`${value}T00:00:00`).toLocaleDateString(dateLocale(), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function describeDeadline(value: string | null | undefined, t: (key: string, vars?: Record<string, string | number>) => string) {
  if (!value) {
    return { label: t("common.notSet"), hint: t("jobDetail.deadlineMissingHint"), tone: "missing" as const };
  }
  const label = formatDeadlineDate(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return { label, hint: "", tone: "ok" as const };
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${value}T00:00:00`);
  const days = Math.round((due.getTime() - today.getTime()) / 86400000);
  if (days < 0) {
    const n = Math.abs(days);
    return { label, hint: n === 1 ? t("jobDetail.daysAgo", { n }) : t("jobDetail.daysAgoPlural", { n }), tone: "overdue" as const };
  }
  if (days === 0) return { label, hint: t("jobDetail.dueToday"), tone: "soon" as const };
  if (days <= 7) return { label, hint: days === 1 ? t("jobDetail.daysLeft", { n: days }) : t("jobDetail.daysLeftPlural", { n: days }), tone: "soon" as const };
  return { label, hint: t("jobDetail.daysLeftPlural", { n: days }), tone: "ok" as const };
}

export default function JobDetail() {
  const { t } = useT();
  const { id } = useParams<{ id: string }>();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: JobTab = (TAB_KEYS as readonly string[]).includes(requested || "")
    ? (requested as JobTab)
    : "details";
  const setTab = (key: JobTab) => {
    setParams(key === "details" ? {} : { tab: key }, { replace: true });
  };

  const analysis = useApi<JobAnalysisResponse>(() => api.get(`/api/jobs/${id}/analysis`), [id]);
  const score = useApi<JobScore>(() => api.get(`/api/jobs/${id}/score`), [id]);
  const research = useApi<ResearchResponse>(() => api.get(`/api/jobs/${id}/research`), [id]);
  const applications = useApi<Application[]>(() => api.get("/api/applications"), [id]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<JobForm>(EMPTY_FORM);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [workflowRunId, setWorkflowRunId] = useState<string | null>(null);
  const navigate = useNavigate();

  const job = analysis.data?.job;
  const analyzing = job?.status === "analyzing";
  const workflow = useWorkflow(workflowRunId, analyzing || workflowRunId ? `/api/jobs/${id}/workflow` : null, () => {
    setWorkflowRunId(null);
    analysis.reload();
    score.reload();
    research.reload();
  });
  const workflowActive = analyzing && workflow?.status !== "FAILED" && workflow?.status !== "COMPLETED";

  useEffect(() => {
    if (job && !editing) setForm(formFromJob(job));
  }, [job, editing]);

  const deadline = describeDeadline(job?.deadline, t);
  const relatedApps = useMemo(
    () => (applications.data ?? []).filter((item) => item.job_id === id),
    [applications.data, id],
  );

  const runAnalysis = async () => {
    setBusy(true);
    try {
      const accepted = await api.post<{ workflow_run_id: string }>(
        `/api/jobs/${id}/analyze`,
        { include_research: true },
      );
      setWorkflowRunId(accepted.workflow_run_id);
      analysis.reload();
    } finally {
      setBusy(false);
    }
  };

  const startApplication = async () => {
    setBusy(true);
    try {
      const existing = relatedApps[0];
      if (existing) {
        navigate(`/applications/${existing.id}`);
        return;
      }
      const app = await api.post<Application>("/api/applications", { job_id: id });
      await api.post(`/api/applications/${app.id}/strategy`);
      navigate(`/applications/${app.id}`);
    } finally {
      setBusy(false);
    }
  };

  const saveDetails = async (e: FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setBusy(true);
    try {
      await api.put(`/api/jobs/${id}`, {
        ...form,
        deadline: form.deadline.trim() || null,
      });
      setEditing(false);
      setSaved(true);
      analysis.reload();
      setTimeout(() => setSaved(false), 2500);
    } catch (err: any) {
      setSaveError(typeof err.detail === "string" ? err.detail : t("jobDetail.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const deleteJob = async () => {
    if (!window.confirm(t("common.confirmDeleteJobLong"))) return;
    setBusy(true);
    try {
      await api.delete(`/api/jobs/${id}`);
      navigate("/jobs");
    } finally {
      setBusy(false);
    }
  };

  if (analysis.loading) return <p className="muted">{t("common.loading")}</p>;
  if (!job) return <Empty>{t("common.untitledRole")}</Empty>;

  const requirements = analysis.data?.requirements ?? [];
  const parsed = analysis.data?.parsed;
  const s = score.data;

  return (
    <>
      <p className="small muted" style={{ marginTop: 0 }}>
        <Link to="/jobs"><ArrowLeft aria-hidden style={{ width: 14, height: 14, verticalAlign: "-2px" }} /> All jobs</Link>
      </p>
      <div className="row spread">
        <div>
          <h1 className="page-title">{job.position_title || t("common.untitledRole")}</h1>
          <p className="page-sub" style={{ marginBottom: 10 }}>
            {job.organization_name || t("common.unknownOrg")}
            {job.location ? ` · ${job.location}` : ""}
            {job.contract_type ? ` · ${job.contract_type}` : ""}
            {job.remote_policy ? ` · ${job.remote_policy}` : ""}
          </p>
        </div>
        <div className="row">
          <span className={`badge ${job.status}`}>{t(`status.${job.status}`)}</span>
          <button onClick={runAnalysis} disabled={busy || workflowActive}>
            {workflowActive ? <Spinner /> : <RefreshCw aria-hidden />} {job.status === "analyzed" ? t("jobDetail.reanalyze") : t("jobDetail.analyze")}
          </button>
          <button className="primary" onClick={startApplication} disabled={busy || workflowActive}>
            {relatedApps.length ? t("jobDetail.openApp") : t("jobDetail.startApp")} <ArrowRight aria-hidden />
          </button>
          <button className="danger" onClick={deleteJob} disabled={busy || workflowActive}>
            <Trash2 aria-hidden /> {t("common.delete")}
          </button>
        </div>
      </div>

      <div className="fact-strip">
        <div className={`fact-chip deadline ${deadline.tone}`}>
          <CalendarDays aria-hidden />
          <div>
            <div className="fact-k">{t("jobDetail.deadline")}</div>
            <div className="fact-v">{deadline.label}</div>
            {deadline.hint && <div className="small muted">{deadline.hint}</div>}
          </div>
        </div>
        <div className="fact-chip">
          <MapPin aria-hidden />
          <div>
            <div className="fact-k">Location</div>
            <div className="fact-v">{dash(job.location)}</div>
          </div>
        </div>
        <div className="fact-chip">
          <Building2 aria-hidden />
          <div>
            <div className="fact-k">Contract</div>
            <div className="fact-v">{dash(job.contract_type || job.remote_policy)}</div>
          </div>
        </div>
        <div className="fact-chip">
          <Gauge aria-hidden />
          <div>
            <div className="fact-k">Fit</div>
            <div className="fact-v">{s ? `${Math.round(s.overall_score * 100)}%` : "Not scored"}</div>
          </div>
        </div>
      </div>

      {analyzing && (
        <div className="panel">
          <ThinkingProgress phrases={THINKING_PHRASES.jobAnalysis} workflow={workflow} />
        </div>
      )}
      {workflow?.status === "FAILED" && (
        <div className="alert error">
          Analysis failed: {workflow.error || workflow.stages.find((stage) => stage.status === "FAILED")?.error || t("jobDetail.unknownError")}
        </div>
      )}
      {saved && <div className="alert ok">Job details saved.</div>}

      <div className="tabs">
        {TAB_KEYS.map((key) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {t(`jobDetail.tabs.${key}`)}
          </button>
        ))}
      </div>

      {tab === "details" && (
        <DetailsTab
          job={job}
          form={form}
          editing={editing}
          busy={busy}
          saveError={saveError}
          parsed={parsed}
          relatedApps={relatedApps}
          onEdit={() => { setForm(formFromJob(job)); setEditing(true); setSaveError(null); }}
          onCancel={() => { setEditing(false); setForm(formFromJob(job)); setSaveError(null); }}
          onChange={(patch) => setForm((current) => ({ ...current, ...patch }))}
          onSave={saveDetails}
        />
      )}

      {tab === "fit" && (
        <FitTab
          job={job}
          score={s}
          requirements={requirements}
          analysis={analysis.data}
          onAnalyze={runAnalysis}
          busy={busy || workflowActive}
        />
      )}

      {tab === "intelligence" && <IntelligenceTab research={research.data} />}
    </>
  );
}

function DetailsTab({
  job,
  form,
  editing,
  busy,
  saveError,
  parsed,
  relatedApps,
  onEdit,
  onCancel,
  onChange,
  onSave,
}: {
  job: Job;
  form: JobForm;
  editing: boolean;
  busy: boolean;
  saveError: string | null;
  parsed: JobAnalysisResponse["parsed"] | undefined;
  relatedApps: Application[];
  onEdit: () => void;
  onCancel: () => void;
  onChange: (patch: Partial<JobForm>) => void;
  onSave: (e: FormEvent) => void;
}) {
  const { t } = useT();
  const deadline = describeDeadline(job.deadline, t);
  const facts: { label: string; value: string; href?: string; className?: string }[] = [
    { label: t("jobDetail.organization"), value: dash(job.organization_name) },
    { label: t("onboarding.position"), value: dash(job.position_title) },
    { label: t("jobDetail.location"), value: dash(job.location) },
    { label: t("jobDetail.deadline"), value: job.deadline ? `${deadline.label}${deadline.hint ? ` · ${deadline.hint}` : ""}` : t("common.notSet"), className: "deadline" },
    { label: t("jobDetail.contract"), value: dash(job.contract_type) },
    { label: t("jobDetail.remote"), value: dash(job.remote_policy) },
    { label: t("jobDetail.duration"), value: dash(job.duration) },
    { label: t("jobDetail.grade"), value: dash(job.grade_level) },
    { label: t("jobDetail.department"), value: dash(job.department) },
    { label: t("jobDetail.team"), value: dash(job.team) },
    { label: t("jobDetail.reporting"), value: dash(job.reporting_line) },
    { label: t("jobDetail.sourceUrl"), value: dash(job.source_url || job.source_type), href: job.source_url || undefined },
  ];

  return (
    <>
      <div className="panel">
        <div className="row spread mb">
          <h3 style={{ margin: 0 }}>Vacancy</h3>
          {!editing && (
            <button className="sm" onClick={onEdit}><Pencil aria-hidden /> {t("common.edit")}</button>
          )}
        </div>
        {editing ? (
          <form onSubmit={onSave}>
            <div className="form-row">
              <div>
                <label>Position</label>
                <input value={form.position_title} onChange={(e) => onChange({ position_title: e.target.value })} />
              </div>
              <div>
                <label>Organization</label>
                <input value={form.organization_name} onChange={(e) => onChange({ organization_name: e.target.value })} />
              </div>
            </div>
            <div className="form-row cols-3">
              <div>
                <label>Location</label>
                <input value={form.location} onChange={(e) => onChange({ location: e.target.value })} />
              </div>
              <div>
                <label>Deadline</label>
                <input value={form.deadline} onChange={(e) => onChange({ deadline: e.target.value })} placeholder="YYYY-MM-DD or 15 September 2026" />
              </div>
              <div>
                <label>Contract type</label>
                <input value={form.contract_type} onChange={(e) => onChange({ contract_type: e.target.value })} placeholder="Fixed term, consultancy…" />
              </div>
            </div>
            <div className="form-row cols-3">
              <div>
                <label>Remote policy</label>
                <select value={form.remote_policy} onChange={(e) => onChange({ remote_policy: e.target.value })}>
                  <option value="">Not specified</option>
                  <option value="on-site">On-site</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="remote">Remote</option>
                </select>
              </div>
              <div>
                <label>Duration</label>
                <input value={form.duration} onChange={(e) => onChange({ duration: e.target.value })} />
              </div>
              <div>
                <label>Grade / level</label>
                <input value={form.grade_level} onChange={(e) => onChange({ grade_level: e.target.value })} />
              </div>
            </div>
            <div className="form-row cols-3">
              <div>
                <label>Department</label>
                <input value={form.department} onChange={(e) => onChange({ department: e.target.value })} />
              </div>
              <div>
                <label>Team</label>
                <input value={form.team} onChange={(e) => onChange({ team: e.target.value })} />
              </div>
              <div>
                <label>Reporting line</label>
                <input value={form.reporting_line} onChange={(e) => onChange({ reporting_line: e.target.value })} />
              </div>
            </div>
            <label>Source URL</label>
            <input value={form.source_url} onChange={(e) => onChange({ source_url: e.target.value })} />
            <label>Notes</label>
            <input value={form.notes} onChange={(e) => onChange({ notes: e.target.value })} />
            <label>Job description</label>
            <textarea rows={14} value={form.raw_jd_text} onChange={(e) => onChange({ raw_jd_text: e.target.value })} />
            <p className="small muted">If you change the JD, re-analyze afterwards so matching uses the updated text.</p>
            <ErrorBox error={saveError} />
            <div className="row mt">
              <button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save details"}</button>
              <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
            </div>
          </form>
        ) : (
          <>
            <div className="dl-grid">
              {facts.map((fact) => (
                <div className={`dl-item ${fact.className || ""}`} key={fact.label}>
                  <div className="dl-k">{fact.label}</div>
                  <div className="dl-v">
                    {fact.href ? (
                      <a href={fact.href} target="_blank" rel="noreferrer">
                        {fact.value} <ExternalLink aria-hidden style={{ width: 12, height: 12 }} />
                      </a>
                    ) : fact.value}
                  </div>
                </div>
              ))}
              {job.notes ? (
                <div className="dl-item span-2">
                  <div className="dl-k">Notes</div>
                  <div className="dl-v">{job.notes}</div>
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>

      {!editing && (
        <div className="panel">
          <h3>Job description</h3>
          {job.raw_jd_text?.trim() ? (
            <pre className="jd-body">{job.raw_jd_text}</pre>
          ) : (
            <p className="muted">No job description text stored yet.</p>
          )}
        </div>
      )}

      {parsed?.responsibilities?.length ? (
        <div className="panel">
          <h3>Responsibilities</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {parsed.responsibilities.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
      ) : null}

      {parsed?.competencies?.length ? (
        <div className="panel">
          <h3>Competencies</h3>
          <div className="pill-list">
            {parsed.competencies.map((item) => <span className="pill" key={item}>{item}</span>)}
          </div>
        </div>
      ) : null}

      {parsed?.keywords?.length ? (
        <div className="panel">
          <h3>Extracted keywords</h3>
          <div className="pill-list">
            {parsed.keywords.map((k) => (
              <span className="pill" key={k.term} title={k.classification}>{k.term}</span>
            ))}
          </div>
        </div>
      ) : null}

      {relatedApps.length > 0 && (
        <div className="panel">
          <h3>Applications</h3>
          {relatedApps.map((app) => (
            <div className="row spread mb" key={app.id}>
              <div>
                <Link to={`/applications/${app.id}`}>{app.status}</Link>
                <div className="small muted">
                  {app.fit_score != null ? `${Math.round(app.fit_score * 100)}% fit` : "No fit score yet"}
                </div>
              </div>
              <Link to={`/applications/${app.id}`}>Open workspace →</Link>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function FitTab({
  job,
  score: s,
  requirements,
  analysis,
  onAnalyze,
  busy,
}: {
  job: Job;
  score: JobScore | null | undefined;
  requirements: JobAnalysisResponse["requirements"];
  analysis: JobAnalysisResponse | null;
  onAnalyze: () => void;
  busy: boolean;
}) {
  const { t } = useT();
  if (!s && !requirements.length) {
    return (
      <div className="panel">
        <Empty>
          No matching results yet.
          <div className="mt">
            <button className="primary" onClick={onAnalyze} disabled={busy}>
              {busy ? <Spinner /> : <RefreshCw aria-hidden />} {t("jobDetail.analyze")}
            </button>
          </div>
        </Empty>
      </div>
    );
  }

  return (
    <>
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
            <ScoreRing score={s.overall_score} threshold={s.threshold} low={s.overall_score_low} high={s.overall_score_high} />
            <div className="mt">
              {Object.entries(s.category_scores).map(([key, value]) => (
                <div className="score-row" key={key}>
                  <span className="name">{t(`category.${key}`)}</span>
                  <div className="score-bar"><div style={{ width: `${Math.round(value * 100)}%` }} /></div>
                  <span className="pct">{Math.round(value * 100)}%</span>
                </div>
              ))}
            </div>
            {s.unknown_count > 0 && (
              <p className="small muted mt">
                {s.unknown_count} requirement(s) could not be evaluated
                {s.coverage != null && s.coverage < 1 ? ` — the score above reflects ${Math.round(s.coverage * 100)}% of the job's requirements` : ""}.
                Add more career evidence to improve accuracy.
              </p>
            )}
          </div>
          <div className="panel">
            <h3>Strengths & Gaps</h3>
            {[
              [t("jobDetail.strongMatches"), s.strong_matches, "var(--ok)"],
              [t("jobDetail.partialMatches"), s.partial_matches, "var(--warn)"],
              [t("jobDetail.transferable"), s.transferable, "var(--accent)"],
              [t("jobDetail.gaps"), s.gaps, "var(--danger)"],
              [t("jobDetail.risks"), s.risks, "var(--danger)"],
              [t("jobDetail.advantages"), s.advantages, "var(--accent-2)"],
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

      {analysis && requirements.length > 0 && <EvidenceGraph analysis={analysis} />}

      {requirements.length > 0 && (
        <div className="panel">
          <h3>Requirements Matrix</h3>
          <table>
            <thead><tr><th style={{ width: "46%" }}>Requirement</th><th>Type</th><th>Importance</th><th>Match</th><th>Evidence</th></tr></thead>
            <tbody>
              {requirements.map((r) => (
                <tr key={r.id}>
                  <td>
                    <div>{r.text}</div>
                    {r.qualification_paths?.length ? (
                      <div className="small muted mt">
                        Any qualifying path: {r.qualification_paths.map((path, index) => (
                          <span key={index}>
                            {index ? " OR " : ""}
                            {path.label || path.predicates.map((predicate) => (
                              predicate.minimum_level
                              || (predicate.minimum_years != null ? `${predicate.minimum_years}+ years` : "")
                              || predicate.value
                              || predicate.terms?.join(", ")
                              || predicate.kind
                            )).join(" + ")}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </td>
                  <td className="muted small">{r.requirement_type}</td>
                  <td><span className={`badge ${r.importance}`}>{r.importance}</span></td>
                  <td>{r.match ? <span className={`badge ${r.match.status}`}>{r.match.status.replace("_", " ")}</span> : <span className="badge UNKNOWN">—</span>}</td>
                  <td className="small muted">
                    {r.match?.qualification_evaluation?.selected_path_index != null && (
                      <div>
                        Qualified through: {r.qualification_paths?.[r.match.qualification_evaluation.selected_path_index]?.label
                          || `path ${r.match.qualification_evaluation.selected_path_index + 1}`}
                      </div>
                    )}
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
    </>
  );
}

function IntelligenceTab({ research }: { research: ResearchResponse | null }) {
  const { t } = useT();
  return (
    <div className="grid cols-2">
      <div className="panel">
        <h3>Organization Intelligence</h3>
        {research?.organization_research?.length ? (
          research.organization_research.map((claim) => (
            <div key={claim.id} className="mb">
              <div className="small">{claim.claim}</div>
              <div className="small muted">
                <span className={`badge ${claim.confidence === "HIGH" ? "verified" : claim.confidence === "MEDIUM" ? "unverified" : "UNKNOWN"}`}>{claim.confidence}</span>{" "}
                {claim.source_url && <a href={claim.source_url} target="_blank" rel="noreferrer">source</a>} · {claim.source_type}
              </div>
            </div>
          ))
        ) : (
          <p className="muted small">Research unavailable — offline mode or no public sources found. The analysis above is unaffected.</p>
        )}
      </div>
      <div className="panel">
        <h3>Hiring Team Intelligence</h3>
        {research?.people?.length ? (
          research.people.map((p) => (
            <div key={p.id} className="mb">
              <div><strong>{p.name}</strong> — {p.role}</div>
              <div className="small muted"><span className={`badge ${p.confidence === "HIGH" ? "verified" : "unverified"}`}>{p.confidence}</span> {p.evidence?.join("; ")}</div>
            </div>
          ))
        ) : (
          <p className="muted small">{research?.hiring_context?.notes || t("jobDetail.hiringUnknown")}</p>
        )}
      </div>
    </div>
  );
}
