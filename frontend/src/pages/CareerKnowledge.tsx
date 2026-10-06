import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, FileSearch, Inbox, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { api, ApiError, waitForCareerIngest } from "../api/client";
import type {
  CareerAchievement,
  CareerDocument,
  CareerExperience,
  CareerProject,
  IngestResult,
  PendingIngestion,
  ProfessionalKnowledge,
  ReconciliationAction,
  ReconciliationProposal,
} from "../api/types";
import { CareerOverview, type CareerTabKey } from "../components/CareerMap";
import { ExperienceRoleCard } from "../components/ExperienceRoleCards";
import { openCoachWidget } from "../components/coach/CoachWidget";
import { Empty, ErrorBox, Link, useApi } from "../components/ui";
import { t, useT } from "../lib/i18n";
import { usageMessage } from "../lib/usageErrors";

/* Field-driven CRUD tabs keep every career entity editable with provenance
   badges (§47: Verified / Unverified / Needs Review). */

type Field = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "list" | "number" | "checkbox" | "select";
  required?: boolean;
  /** When type=select, load options from this career API path */
  optionsPath?: string;
  optionLabel?: (row: any) => string;
  emptyLabel?: string;
};

type EntityConfig = {
  key: string;
  label: string;
  path: string;
  fields: Field[];
  title: (row: any) => string;
  subtitle?: (row: any) => string;
  verifiable?: boolean;
};

const ENTITIES: EntityConfig[] = [
  {
    key: "experience", label: "Experience", path: "/api/career/experiences", verifiable: true,
    title: (r) => `${r.job_title} — ${r.organization}`,
    subtitle: (r) => [r.start_date, r.end_date || "Present"].filter(Boolean).join(" – ") + (r.location ? ` · ${r.location}` : ""),
    fields: [
      { name: "organization", label: "Organization", required: true },
      { name: "job_title", label: "Job title", required: true },
      { name: "start_date", label: "Start (YYYY-MM)" },
      { name: "end_date", label: "End (YYYY-MM, empty = current)" },
      { name: "employment_type", label: "Employment type" },
      { name: "location", label: "Location" },
      { name: "description", label: "Description", type: "textarea" },
      { name: "responsibilities", label: "Responsibilities (one per line)", type: "list" },
      { name: "technologies", label: t("career.fields.technologies"), type: "list" },
      { name: "domains", label: "Domains (one per line)", type: "list" },
      { name: "leadership", label: "Leadership (one per line)", type: "list" },
      { name: "stakeholders", label: "Stakeholders (one per line)", type: "list" },
    ],
  },
  {
    key: "projects", label: "Projects", path: "/api/career/projects", verifiable: true,
    title: (r) => r.name,
    subtitle: (r) => [r.role, r.experience_id ? "Linked to experience" : "Independent project"].filter(Boolean).join(" · "),
    fields: [
      { name: "name", label: "Project name", required: true },
      {
        name: "experience_id",
        label: "Linked experience (optional)",
        type: "select",
        optionsPath: "/api/career/experiences",
        optionLabel: (r) => `${r.job_title} — ${r.organization}`,
        emptyLabel: "— None (independent project) —",
      },
      { name: "role", label: "Your role" },
      { name: "description", label: "Description", type: "textarea" },
      { name: "technologies", label: t("career.fields.technologies"), type: "list" },
      { name: "outcomes", label: "Outcomes (one per line)", type: "list" },
      { name: "urls", label: "URLs (one per line)", type: "list" },
    ],
  },
  {
    key: "achievements", label: "Achievements", path: "/api/career/achievements", verifiable: true,
    title: (r) => r.title || r.description.slice(0, 80),
    subtitle: (r) => {
      const links = [
        r.experience_id && "Experience",
        r.project_id && "Project",
        r.education_id && "Education",
      ].filter(Boolean);
      const parent = links.length ? `Linked: ${links.join(", ")}` : "No parent link";
      return [r.quantified_result, parent].filter(Boolean).join(" · ");
    },
    fields: [
      { name: "title", label: "Title" },
      { name: "description", label: "Description", type: "textarea", required: true },
      { name: "quantified_result", label: "Quantified result" },
      {
        name: "experience_id",
        label: "Linked experience",
        type: "select",
        optionsPath: "/api/career/experiences",
        optionLabel: (r) => `${r.job_title} — ${r.organization}`,
        emptyLabel: "— None —",
      },
      {
        name: "project_id",
        label: "Linked project (optional)",
        type: "select",
        optionsPath: "/api/career/projects",
        optionLabel: (r) => r.name,
        emptyLabel: "— None —",
      },
      {
        name: "education_id",
        label: "Linked education (optional)",
        type: "select",
        optionsPath: "/api/career/education",
        optionLabel: (r) => [r.degree, r.field_of_study, r.institution].filter(Boolean).join(" · ") || r.institution,
        emptyLabel: "— None —",
      },
      { name: "skills", label: "Related skills (one per line)", type: "list" },
    ],
  },
  {
    key: "skills", label: "Skills", path: "/api/career/skills", verifiable: true,
    title: (r) => r.canonical_name || r.name,
    subtitle: (r) => [r.category, r.proficiency, r.synonyms?.length ? `aka: ${r.synonyms.join(", ")}` : ""].filter(Boolean).join(" · "),
    fields: [
      { name: "name", label: "Skill", required: true },
      { name: "category", label: t("career.fields.category") },
      { name: "proficiency", label: "Proficiency" },
      { name: "years_experience", label: "Years of experience", type: "number" },
    ],
  },
  {
    key: "education", label: "Education", path: "/api/career/education", verifiable: true,
    title: (r) => [r.degree, r.field_of_study].filter(Boolean).join(", ") || r.institution,
    subtitle: (r) => r.institution,
    fields: [
      { name: "institution", label: "Institution", required: true },
      { name: "degree", label: "Degree" },
      { name: "field_of_study", label: "Field of study" },
      { name: "start_date", label: "Start (YYYY-MM)" },
      { name: "end_date", label: "End (YYYY-MM)" },
    ],
  },
  {
    key: "certifications", label: "Certifications", path: "/api/career/certifications", verifiable: true,
    title: (r) => r.name, subtitle: (r) => r.issuer,
    fields: [
      { name: "name", label: "Certification", required: true },
      { name: "issuer", label: "Issuer" },
      { name: "issue_date", label: "Issue date (YYYY-MM)" },
      { name: "credential_id", label: t("career.fields.credential_id") },
      { name: "credential_type", label: t("career.fields.credential_type") },
      { name: "url", label: t("career.fields.url") },
    ],
  },
  {
    key: "languages", label: "Languages", path: "/api/career/languages",
    title: (r) => r.language, subtitle: (r) => r.proficiency + (r.is_native ? " (native)" : ""),
    fields: [
      { name: "language", label: "Language", required: true },
      { name: "proficiency", label: "Proficiency" },
      { name: "is_native", label: "Native", type: "checkbox" },
    ],
  },
  {
    key: "publications", label: "Publications", path: "/api/career/publications",
    title: (r) => r.title, subtitle: (r) => r.publisher,
    fields: [
      { name: "title", label: "Title", required: true },
      { name: "publisher", label: "Publisher" },
      { name: "publication_date", label: "Date (YYYY-MM)" },
      { name: "url", label: "URL" },
      { name: "description", label: "Description", type: "textarea" },
    ],
  },
];

function EntityForm({ config, initial, onSaved, onCancel }: { config: EntityConfig; initial?: any; onSaved: () => void; onCancel: () => void }) {
  const [form, setForm] = useState<Record<string, any>>(() => {
    const base: Record<string, any> = {};
    for (const f of config.fields) {
      const v = initial?.[f.name];
      if (f.type === "list") base[f.name] = (v ?? []).join("\n");
      else if (f.type === "select") base[f.name] = v ?? "";
      else base[f.name] = v ?? (f.type === "checkbox" ? false : "");
    }
    return base;
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectOptions, setSelectOptions] = useState<Record<string, any[]>>({});

  useEffect(() => {
    const selectFields = config.fields.filter((f) => f.type === "select" && f.optionsPath);
    if (!selectFields.length) return;
    let cancelled = false;
    (async () => {
      const next: Record<string, any[]> = {};
      await Promise.all(
        selectFields.map(async (f) => {
          try {
            next[f.name] = await api.get(f.optionsPath!);
          } catch {
            next[f.name] = [];
          }
        }),
      );
      if (!cancelled) setSelectOptions(next);
    })();
    return () => { cancelled = true; };
  }, [config]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload: Record<string, any> = {};
    for (const f of config.fields) {
      const v = form[f.name];
      if (f.type === "list") payload[f.name] = String(v).split("\n").map((s) => s.trim()).filter(Boolean);
      else if (f.type === "number") payload[f.name] = v === "" ? null : Number(v);
      else if (f.type === "checkbox") payload[f.name] = Boolean(v);
      else if (f.type === "select") payload[f.name] = v === "" ? null : v;
      else payload[f.name] = v === "" ? (f.required ? v : null) : v;
    }
    try {
      if (initial?.id) await api.put(`${config.path}/${initial.id}`, payload);
      else await api.post(config.path, payload);
      onSaved();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h3>{initial?.id ? "Edit" : "Add"} {config.label.slice(0, -1)}</h3>
      {config.fields.map((f) => (
        <div key={f.name}>
          <label>{f.label}</label>
          {f.type === "textarea" || f.type === "list" ? (
            <textarea value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required} rows={f.type === "list" ? 4 : 3} />
          ) : f.type === "checkbox" ? (
            <input type="checkbox" style={{ width: "auto" }} checked={!!form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.checked })} />
          ) : f.type === "select" ? (
            <select value={form[f.name] ?? ""} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required}>
              <option value="">{f.emptyLabel || "— None —"}</option>
              {(selectOptions[f.name] || []).map((opt) => (
                <option key={opt.id} value={opt.id}>{(f.optionLabel || ((r) => r.id))(opt)}</option>
              ))}
            </select>
          ) : (
            <input value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required} type={f.type === "number" ? "number" : "text"} step="any" />
          )}
        </div>
      ))}
      <ErrorBox error={error} />
      <div className="row mt">
        <button className="primary" disabled={busy}>Save</button>
        <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function EvidencePanel({ entityType, entityId }: { entityType: string; entityId: string }) {
  const evidence = useApi<any[]>(() => api.get(`/api/career/evidence/${entityType}/${entityId}`), [entityType, entityId]);
  if (evidence.loading) return null;
  if (!evidence.data?.length) return <div className="evidence-pop muted">No provenance recorded yet.</div>;
  return (
    <div className="evidence-pop">
      {evidence.data.map((ev) => (
        <div key={ev.id} className="mb">
          <div><strong>Source:</strong> {ev.source_document ?? "manual entry"}{ev.source_section ? ` · ${ev.source_section}` : ""}{ev.source_page ? ` · page ${ev.source_page}` : ""}</div>
          {ev.original_text && <div className="muted">“{ev.original_text}”</div>}
          <div className="small"><span className={`badge ${ev.verification_status}`}>{ev.verification_status}</span> <span className="muted">confidence {Math.round((ev.confidence ?? 0) * 100)}%</span></div>
        </div>
      ))}
    </div>
  );
}

function EntityTab({ config }: { config: EntityConfig }) {
  const { t } = useT();
  const { data, reload, loading } = useApi<any[]>(() => api.get(config.path));
  const [editing, setEditing] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);
  const needsParents = config.key === "achievements" || config.key === "projects";
  const isExperience = config.key === "experience";
  const experiences = useApi<any[]>(
    () => (needsParents ? api.get("/api/career/experiences") : Promise.resolve([])),
    [needsParents],
  );
  const projects = useApi<CareerProject[]>(
    () => (config.key === "achievements" || isExperience ? api.get("/api/career/projects") : Promise.resolve([])),
    [config.key, isExperience],
  );
  const nestedAchievements = useApi<CareerAchievement[]>(
    () => (isExperience ? api.get("/api/career/achievements") : Promise.resolve([])),
    [isExperience],
  );
  const knowledge = useApi<ProfessionalKnowledge[]>(
    () => (isExperience ? api.get("/api/career/knowledge") : Promise.resolve([])),
    [isExperience],
  );
  const education = useApi<any[]>(
    () => (config.key === "achievements" ? api.get("/api/career/education") : Promise.resolve([])),
    [config.key],
  );

  const parentLabels = useMemo(() => {
    const expMap = Object.fromEntries((experiences.data || []).map((e) => [e.id, `${e.job_title} — ${e.organization}`]));
    const projMap = Object.fromEntries((projects.data || []).map((p) => [p.id, p.name]));
    const eduMap = Object.fromEntries(
      (education.data || []).map((e) => [e.id, [e.degree, e.field_of_study, e.institution].filter(Boolean).join(" · ") || e.institution]),
    );
    return { expMap, projMap, eduMap };
  }, [experiences.data, projects.data, education.data]);

  const subtitleFor = (row: any) => {
    if (config.key === "achievements") {
      const links = [
        row.experience_id && parentLabels.expMap[row.experience_id] && `Exp: ${parentLabels.expMap[row.experience_id]}`,
        row.project_id && parentLabels.projMap[row.project_id] && `Project: ${parentLabels.projMap[row.project_id]}`,
        row.education_id && parentLabels.eduMap[row.education_id] && `Edu: ${parentLabels.eduMap[row.education_id]}`,
      ].filter(Boolean);
      return [row.quantified_result, links.length ? links.join(" · ") : "No parent link"].filter(Boolean).join(" · ");
    }
    if (config.key === "projects") {
      const expLabel = row.experience_id ? parentLabels.expMap[row.experience_id] : null;
      return [row.role, expLabel ? `Under: ${expLabel}` : "Independent project"].filter(Boolean).join(" · ");
    }
    return config.subtitle?.(row);
  };

  const remove = async (id: string) => {
    if (!confirm(t("career.confirmDelete"))) return;
    await api.delete(`${config.path}/${id}`);
    reload();
  };
  const verify = async (id: string, status: string) => {
    await api.post(`${config.path}/${id}/verify?status_value=${status}`);
    reload();
  };

  return (
    <>
      <div className="row spread mb">
        <p className="muted" style={{ margin: 0 }}>{data?.length ?? 0} entr{data?.length === 1 ? "y" : "ies"}</p>
        <button className="primary sm" onClick={() => { setAdding(true); setEditing(null); }}><Plus aria-hidden /> {t("common.add")}</button>
      </div>
      {(adding || editing) && (
        <EntityForm config={config} initial={editing} onSaved={() => { setAdding(false); setEditing(null); reload(); }} onCancel={() => { setAdding(false); setEditing(null); }} />
      )}
      {loading && <p className="muted">Loading…</p>}
      {!loading && !data?.length && <Empty icon={Inbox}>Nothing here yet — add entries manually or ingest a document.</Empty>}
      {isExperience
        ? (data as CareerExperience[] | undefined)?.map((row) => (
          <ExperienceRoleCard
            key={row.id}
            experience={row}
            projects={(projects.data || []).filter((p) => p.experience_id === row.id)}
            achievements={nestedAchievements.data || []}
            knowledge={(knowledge.data || []).filter((item) =>
              (item.contexts || []).some((ctx) => ctx.experience_id === row.id),
            )}
            evidenceOpen={evidenceFor === row.id}
            evidencePanel={<EvidencePanel entityType="experience" entityId={row.id} />}
            onToggleEvidence={() => setEvidenceFor(evidenceFor === row.id ? null : row.id)}
            onEdit={() => { setEditing(row); setAdding(false); }}
            onRemove={() => remove(row.id)}
            onVerify={() => verify(row.id, "verified")}
          />
        ))
        : data?.map((row) => (
        <div className="list-item" key={row.id}>
          <div className="row spread">
            <div>
              <div className="title">{config.title(row)}</div>
              <div className="meta">{subtitleFor(row)}</div>
            </div>
            <div className="row">
              {row.verification_status && <span className={`badge ${row.verification_status}`}>{row.verification_status.replace("_", " ")}</span>}
              <button className="sm ghost" onClick={() => setEvidenceFor(evidenceFor === row.id ? null : row.id)}>View Evidence</button>
              {config.verifiable && row.verification_status !== "verified" && (
                <button className="sm" onClick={() => verify(row.id, "verified")}><Check aria-hidden /> Mark verified</button>
              )}
              <button className="sm" onClick={() => { setEditing(row); setAdding(false); }}><Pencil aria-hidden /> Edit</button>
              <button className="sm danger" onClick={() => remove(row.id)}><Trash2 aria-hidden /> Delete</button>
            </div>
          </div>
          {evidenceFor === row.id && <EvidencePanel entityType={config.key === "education" ? "education" : config.key.replace(/s$/, "")} entityId={row.id} />}
        </div>
      ))}
    </>
  );
}

function ProfileTab() {
  const { t } = useT();
  const { data, reload, loading } = useApi<any>(() => api.get("/api/career/profile"));
  const [form, setForm] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const f = form ?? data ?? {};
  if (loading) return <p className="muted">{t("common.loading")}</p>;
  const set = (k: string, v: any) => setForm({ ...f, [k]: v });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    await api.put("/api/career/profile", {
      full_name: f.full_name ?? "", headline: f.headline ?? "", summary: f.summary ?? "",
      email: f.email ?? "", phone: f.phone ?? "", location: f.location ?? "",
      links: f.links ?? {}, preferred_positioning: f.preferred_positioning ?? "",
      career_narratives: f.career_narratives ?? [],
      primary_profession: f.primary_profession ?? "",
      target_sectors: String(f.target_sectors_text ?? (f.target_sectors || []).join("\n"))
        .split("\n").map((s: string) => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setForm(null);
    reload();
    setTimeout(() => setSaved(false), 2000);
  };
  const sectorsText = f.target_sectors_text ?? (f.target_sectors || []).join("\n");
  return (
    <form className="panel" onSubmit={save}>
      <div className="form-row">
        <div><label>{t("career.fullName")}</label><input value={f.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} /></div>
        <div><label>{t("career.headline")}</label><input value={f.headline ?? ""} onChange={(e) => set("headline", e.target.value)} /></div>
      </div>
      <label>{t("career.professionalSummary")}</label>
      <textarea value={f.summary ?? ""} onChange={(e) => set("summary", e.target.value)} />
      <div className="form-row">
        <div><label>{t("onboarding.email")}</label><input value={f.email ?? ""} onChange={(e) => set("email", e.target.value)} /></div>
        <div><label>{t("onboarding.phone")}</label><input value={f.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></div>
      </div>
      <div className="form-row">
        <div><label>{t("onboarding.location")}</label><input value={f.location ?? ""} onChange={(e) => set("location", e.target.value)} /></div>
        <div><label>{t("career.linkedinUrl")}</label><input value={f.links?.linkedin ?? ""} onChange={(e) => set("links", { ...(f.links ?? {}), linkedin: e.target.value })} /></div>
      </div>
      <div className="form-row">
        <div>
          <label>{t("career.profession")}</label>
          <input value={f.primary_profession ?? ""} onChange={(e) => set("primary_profession", e.target.value)} placeholder={t("onboarding.professionPh")} />
        </div>
        <div>
          <label>{t("career.sectors")}</label>
          <textarea value={sectorsText} onChange={(e) => set("target_sectors_text", e.target.value)} placeholder={t("onboarding.sectorsPh")} rows={3} />
        </div>
      </div>
      <label>{t("career.preferredPositioning")}</label>
      <textarea value={f.preferred_positioning ?? ""} onChange={(e) => set("preferred_positioning", e.target.value)} />
      <div className="row mt">
        <button className="primary">{t("career.saveProfile")}</button>
        {saved && <span className="badge verified">{t("common.saved")}</span>}
      </div>
    </form>
  );
}

function proposalSummary(p: ReconciliationProposal): string {
  const payload = p.payload || {};
  if (p.entity_type === "experience") {
    return `${payload.job_title || "Role"} at ${payload.organization || "Organization"}`;
  }
  if (p.entity_type === "project") {
    return String(payload.name || payload.description || "Project");
  }
  return String(payload.description || payload.title || "Achievement").slice(0, 140);
}

function proposalDetails(p: ReconciliationProposal): string {
  const payload = p.payload || {};
  const lines: string[] = [];
  if (p.entity_type === "experience") {
    const dates = [payload.start_date, payload.end_date || "Present"].filter(Boolean).join(" – ");
    if (dates) lines.push(dates);
    for (const r of (payload.responsibilities as string[]) || []) lines.push(`• ${r}`);
    for (const a of (payload.achievements as string[]) || []) lines.push(`★ ${a}`);
    const tech = (payload.technologies as string[]) || [];
    if (tech.length) lines.push(t("career.toolsLabel", { list: tech.join(", ") }));
  } else if (p.entity_type === "project") {
    if (payload.description) lines.push(String(payload.description));
    if (payload.role) lines.push(`Role: ${payload.role}`);
  } else if (payload.quantified_result) {
    lines.push(String(payload.quantified_result));
  }
  return lines.join("\n");
}

type DecisionState = {
  action: ReconciliationAction;
  target_id: string | null;
};

function ReconciliationReview({
  pendingId,
  onDone,
  onBack,
}: {
  pendingId: string;
  onDone: () => void;
  onBack: () => void;
}) {
  const pending = useApi<PendingIngestion>(() => api.get(`/api/career/pending-ingestions/${pendingId}`), [pendingId]);
  const experiences = useApi<any[]>(() => api.get("/api/career/experiences"));
  const projects = useApi<any[]>(() => api.get("/api/career/projects"));
  const achievements = useApi<any[]>(() => api.get("/api/career/achievements"));
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pending.data?.proposals) return;
    const init: Record<string, DecisionState> = {};
    for (const p of pending.data.proposals) {
      init[p.proposal_id] = {
        action: p.action || "create",
        target_id: p.target_id,
      };
    }
    setDecisions(init);
  }, [pending.data]);

  const optionsFor = (entityType: string) => {
    if (entityType === "experience") {
      return (experiences.data || []).map((e) => ({
        id: e.id,
        label: `${e.job_title} — ${e.organization}`,
      }));
    }
    if (entityType === "project") {
      return (projects.data || []).map((p) => ({ id: p.id, label: p.name }));
    }
    return (achievements.data || []).map((a) => ({
      id: a.id,
      label: (a.title || a.description || "").slice(0, 80),
    }));
  };

  const setDecision = (proposalId: string, patch: Partial<DecisionState>) => {
    setDecisions((prev) => ({
      ...prev,
      [proposalId]: { ...prev[proposalId], ...patch },
    }));
  };

  const confirmAll = async () => {
    if (!pending.data) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        decisions: pending.data.proposals.map((p) => ({
          proposal_id: p.proposal_id,
          action: decisions[p.proposal_id]?.action || "create",
          target_id:
            (decisions[p.proposal_id]?.action || "create") === "merge"
              ? decisions[p.proposal_id]?.target_id || null
              : null,
        })),
      };
      await api.post(`/api/career/pending-ingestions/${pendingId}/confirm`, payload);
      onDone();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Failed to confirm");
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!window.confirm("Discard this extraction review? Auto-applied skills/education will remain.")) return;
    setBusy(true);
    try {
      await api.delete(`/api/career/pending-ingestions/${pendingId}`);
      onDone();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Failed to discard");
    } finally {
      setBusy(false);
    }
  };

  if (pending.loading) return <p className="muted">Loading review…</p>;
  if (pending.error || !pending.data) return <ErrorBox error={pending.error || "Not found"} />;

  const mergeCount = Object.values(decisions).filter((d) => d.action === "merge").length;
  const createCount = Object.values(decisions).filter((d) => d.action === "create").length;

  return (
    <div className="panel">
      <div className="row spread mb">
        <div>
          <h3 style={{ margin: 0 }}>Review extracted knowledge</h3>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            {pending.data.document?.filename || "Pasted text"} · {pending.data.proposals.length} proposal
            {pending.data.proposals.length === 1 ? "" : "s"} · suggested {mergeCount} merge / {createCount} create
          </p>
        </div>
        <button className="ghost sm" onClick={onBack} disabled={busy}>Back</button>
      </div>

      {Object.entries(pending.data.auto_applied || {}).some(([, v]) => typeof v === "number" && v > 0) && (
        <div className="alert info">
          Already applied:{" "}
          {Object.entries(pending.data.auto_applied)
            .filter(([, v]) => typeof v === "number" && v > 0)
            .map(([k, v]) => `${k}: ${v}`)
            .join(" · ")}
        </div>
      )}

      {pending.data.proposals.map((p) => {
        const decision = decisions[p.proposal_id] || { action: p.action, target_id: p.target_id };
        const options = optionsFor(p.entity_type);
        return (
          <div key={p.proposal_id} className={`recon-card ${decision.action}`}>
            <div className="row spread">
              <div>
                <span className="badge needs_review">{p.entity_type}</span>{" "}
                <strong>{proposalSummary(p)}</strong>
              </div>
              <span className="muted small">{Math.round((p.confidence || 0) * 100)}% confidence</span>
            </div>
            {p.reasoning && <p className="muted small" style={{ margin: "6px 0" }}>{p.reasoning}</p>}
            {proposalDetails(p) && <div className="recon-payload">{proposalDetails(p)}</div>}

            {decision.action === "merge" && (p.target_snapshot || decision.target_id) && (
              <div className="alert warn" style={{ marginTop: 10, marginBottom: 0 }}>
                Will merge into: <strong>{p.target_snapshot?.label || p.target_label || decision.target_id}</strong>
                {p.target_snapshot?.responsibilities?.length ? (
                  <div className="small muted">Existing bullets: {p.target_snapshot.responsibilities.slice(0, 2).join(" · ")}</div>
                ) : null}
              </div>
            )}

            <div className="recon-actions">
              <label className="small" style={{ margin: 0 }}>
                <input
                  type="radio"
                  name={`action-${p.proposal_id}`}
                  checked={decision.action === "merge"}
                  onChange={() =>
                    setDecision(p.proposal_id, {
                      action: "merge",
                      target_id: decision.target_id || p.target_id || options[0]?.id || null,
                    })
                  }
                />{" "}
                Merge into existing
              </label>
              <label className="small" style={{ margin: 0 }}>
                <input
                  type="radio"
                  name={`action-${p.proposal_id}`}
                  checked={decision.action === "create"}
                  onChange={() => setDecision(p.proposal_id, { action: "create", target_id: null })}
                />{" "}
                Create as new
              </label>
              {decision.action === "merge" && (
                <select
                  value={decision.target_id || ""}
                  onChange={(e) => setDecision(p.proposal_id, { target_id: e.target.value || null })}
                >
                  <option value="">Select existing {p.entity_type}…</option>
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>{o.label}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
        );
      })}

      <ErrorBox error={error} />
      <div className="row mt">
        <button className="primary" onClick={confirmAll} disabled={busy || !pending.data.proposals.length}>
          Confirm &amp; save
        </button>
        <button className="danger" onClick={discard} disabled={busy}>Discard</button>
      </div>
    </div>
  );
}

function PendingIngestionsTab({
  reviewId,
  onReview,
  onCleared,
}: {
  reviewId: string | null;
  onReview: (id: string | null) => void;
  onCleared: () => void;
}) {
  const pending = useApi<PendingIngestion[]>(() => api.get("/api/career/pending-ingestions?status_filter=pending"));

  if (reviewId) {
    return (
      <ReconciliationReview
        pendingId={reviewId}
        onBack={() => onReview(null)}
        onDone={() => {
          onReview(null);
          onCleared();
          pending.reload();
        }}
      />
    );
  }

  return (
    <>
      <p className="muted">
        After extraction, experiences, projects and achievements wait here so you can confirm merges
        into existing entries or create new ones.
      </p>
      {pending.loading && <p className="muted">Loading…</p>}
      {!pending.loading && !pending.data?.length && <Empty icon={Inbox}>No pending reviews.</Empty>}
      {pending.data?.map((row) => (
        <div className="list-item" key={row.id}>
          <div className="row spread">
            <div>
              <div className="title">{row.document?.filename || "Pasted text"}</div>
              <div className="meta">
                {row.proposals?.length || 0} proposal{(row.proposals?.length || 0) === 1 ? "" : "s"}
                {" · "}
                {(row.proposals || []).filter((p) => p.action === "merge").length} suggested merge
                {" · "}
                {new Date(row.created_at).toLocaleString()}
              </div>
            </div>
            <button className="primary sm" onClick={() => onReview(row.id)}>Review</button>
          </div>
        </div>
      ))}
    </>
  );
}

function DocumentsTab({ onPendingCreated }: { onPendingCreated: (id: string) => void }) {
  const docs = useApi<CareerDocument[]>(() => api.get("/api/career/documents"));
  const [text, setText] = useState("");
  const [docType, setDocType] = useState("cv");
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    setBusy(true);
    try {
      await api.upload("/api/career/documents", fd);
      docs.reload();
    } catch (err) {
      const limited = err instanceof ApiError ? usageMessage(err.detail, t) : null;
      setError(limited || (err instanceof Error ? err.message : "Upload failed"));
    } finally {
      setBusy(false);
    }
  };

  const handleIngestResult = (resp: IngestResult) => {
    setResult(resp);
    if (resp.pending_ingestion_id) {
      onPendingCreated(resp.pending_ingestion_id);
    }
  };

  const ingestText = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const accepted = await api.post<{ document_id: string }>("/api/career/ingest-text", { text, doc_type: docType });
      const resp = await waitForCareerIngest(accepted.document_id);
      handleIngestResult(resp);
      setText("");
      docs.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Ingestion failed");
    } finally {
      setBusy(false);
    }
  };

  const ingestDoc = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/career/documents/${id}/ingest`);
      const resp = await waitForCareerIngest(id);
      handleIngestResult(resp);
      docs.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Ingestion failed");
    } finally {
      setBusy(false);
    }
  };

  const autoSummary = useMemo(() => {
    if (!result?.auto_applied && !result?.created) return null;
    const src = result.auto_applied || result.created || {};
    return Object.entries(src)
      .filter(([, v]) => typeof v === "number" && v > 0)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
  }, [result]);

  return (
    <>
      <div className="grid cols-2">
        <div className="panel">
          <h3>Upload a document</h3>
          <label>Document type</label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="cv">CV / Resume</option>
            <option value="jd">Previous Job Description</option>
            <option value="cover_letter">Previous Cover Letter</option>
            <option value="notes">Career notes</option>
            <option value="other">Other</option>
          </select>
          <div className="mt"><input type="file" accept=".pdf,.docx,.txt,.md" onChange={upload} disabled={busy} /></div>
          <p className="small muted">PDF, DOCX, TXT or MD — max size and types enforced server-side.</p>
        </div>
        <div className="panel">
          <h3>Paste career text</h3>
          <textarea rows={6} placeholder="Paste your CV, a role description, achievements…" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="primary mt" onClick={ingestText} disabled={busy || !text.trim()}><Sparkles aria-hidden /> Extract structured knowledge</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {result && (
        <div className={`alert ${result.pending_ingestion_id ? "warn" : "ok"}`}>
          {autoSummary ? <>Auto-applied: {autoSummary}. </> : null}
          {result.pending_ingestion_id ? (
            <>
              {result.proposals_count} item{result.proposals_count === 1 ? "" : "s"} need your review
              (merge into existing vs create new) — open the <strong>Pending review</strong> tab.
            </>
          ) : (
            <>Extraction complete — review entries under the relevant tabs and mark them verified.</>
          )}
        </div>
      )}
      <div className="panel">
        <h3>Stored documents</h3>
        {docs.data?.length ? (
          <table>
            <thead><tr><th>File</th><th>Type</th><th>Size</th><th>Ingested</th><th></th></tr></thead>
            <tbody>
              {docs.data.map((d) => (
                <tr key={d.id}>
                  <td>{d.filename}</td>
                  <td>{d.doc_type}</td>
                  <td className="muted">{Math.round(d.size_bytes / 1024)} KB</td>
                  <td>
                    {d.ingest_status === "running" ? (
                      <span className="badge">extracting…</span>
                    ) : d.ingest_status === "failed" ? (
                      <span className="badge unverified">failed</span>
                    ) : d.ingested ? (
                      <span className="badge verified">yes</span>
                    ) : (
                      <span className="badge unverified">no</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {(!d.ingested || d.ingest_status === "failed") && d.ingest_status !== "running" && (
                      <button className="sm" onClick={() => ingestDoc(d.id)} disabled={busy}>Run extraction</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon={FileSearch}>No documents uploaded yet.</Empty>
        )}
      </div>
    </>
  );
}

function KnowledgeTab() {
  const { t } = useT();
  const { data, reload, loading } = useApi<ProfessionalKnowledge[]>(() => api.get("/api/career/knowledge"));
  const experiences = useApi<CareerExperience[]>(() => api.get("/api/career/experiences"));
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<ProfessionalKnowledge | null>(null);
  const [form, setForm] = useState({
    name: "",
    kind: "domain",
    depth: "applied",
    summary: "",
    years_experience: "",
    experience_id: "",
    how_acquired: "",
    how_applied: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const kinds = ["industry", "domain", "business_function", "process", "methodology", "regulation", "product_service", "customer_stakeholder", "terminology"];
  const depths = ["awareness", "applied", "practiced", "expert"];

  const startEdit = (row?: ProfessionalKnowledge) => {
    const ctx = row?.contexts?.[0];
    setForm({
      name: row?.name || row?.canonical_name || "",
      kind: row?.kind || "domain",
      depth: row?.depth || "applied",
      summary: row?.summary || "",
      years_experience: row?.years_experience != null ? String(row.years_experience) : "",
      experience_id: ctx?.experience_id || "",
      how_acquired: ctx?.how_acquired || "",
      how_applied: ctx?.how_applied || "",
    });
    setEditing(row || null);
    setAdding(!row);
    setError(null);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      name: form.name,
      kind: form.kind,
      depth: form.depth,
      summary: form.summary,
      years_experience: form.years_experience === "" ? null : Number(form.years_experience),
      contexts: form.experience_id
        ? [{
            experience_id: form.experience_id,
            how_acquired: form.how_acquired,
            how_applied: form.how_applied,
            acquisition_mode: "acquired_through_role",
          }]
        : [],
    };
    try {
      if (editing?.id) await api.put(`/api/career/knowledge/${editing.id}`, payload);
      else await api.post("/api/career/knowledge", payload);
      setAdding(false);
      setEditing(null);
      reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm(t("career.confirmDelete"))) return;
    await api.delete(`/api/career/knowledge/${id}`);
    reload();
  };

  const roleLabel = (id: string | null) => {
    if (!id) return "";
    const exp = (experiences.data || []).find((row) => row.id === id);
    return exp ? `${exp.job_title} — ${exp.organization}` : "";
  };

  return (
    <>
      <div className="row spread mb">
        <p className="muted" style={{ margin: 0 }}>{t("career.knowledgeHint")}</p>
        <button className="primary sm" onClick={() => startEdit()}><Plus aria-hidden /> {t("common.add")}</button>
      </div>
      {(adding || editing) && (
        <form className="panel" onSubmit={save}>
          <h3>{editing ? t("career.editKnowledge") : t("career.addKnowledge")}</h3>
          <label>{t("career.knowledgeName")}</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <div className="form-row">
            <div>
              <label>{t("career.fields.kind")}</label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {kinds.map((kind) => (
                  <option key={kind} value={kind}>{t(`career.knowledgeKinds.${kind}`)}</option>
                ))}
              </select>
            </div>
            <div>
              <label>{t("career.fields.depth")}</label>
              <select value={form.depth} onChange={(e) => setForm({ ...form, depth: e.target.value })}>
                {depths.map((depth) => (
                  <option key={depth} value={depth}>{t(`career.knowledgeDepths.${depth}`)}</option>
                ))}
              </select>
            </div>
          </div>
          <label>{t("career.fields.summary")}</label>
          <textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} rows={3} />
          <label>{t("career.linkedRole")}</label>
          <select value={form.experience_id} onChange={(e) => setForm({ ...form, experience_id: e.target.value })}>
            <option value="">{t("career.noneOption")}</option>
            {(experiences.data || []).map((exp) => (
              <option key={exp.id} value={exp.id}>{exp.job_title} — {exp.organization}</option>
            ))}
          </select>
          <label>{t("career.fields.how_applied")}</label>
          <textarea value={form.how_applied} onChange={(e) => setForm({ ...form, how_applied: e.target.value })} rows={2} />
          <ErrorBox error={error} />
          <div className="row mt">
            <button className="primary" disabled={busy}>{t("common.save")}</button>
            <button type="button" className="ghost" onClick={() => { setAdding(false); setEditing(null); }}>{t("common.cancel")}</button>
          </div>
        </form>
      )}
      {loading && <p className="muted">{t("common.loading")}</p>}
      {!loading && !data?.length && <Empty icon={Inbox}>{t("career.knowledgeEmpty")}</Empty>}
      {data?.map((row) => (
        <div className="list-item" key={row.id}>
          <div className="row spread">
            <div>
              <div className="title">{row.canonical_name || row.name}</div>
              <div className="meta">
                {[t(`career.knowledgeKinds.${row.kind}`), t(`career.knowledgeDepths.${row.depth}`), roleLabel(row.contexts?.[0]?.experience_id || null)]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              {row.summary && <p className="small muted">{row.summary}</p>}
            </div>
            <div className="row">
              {row.verification_status && <span className={`badge ${row.verification_status}`}>{row.verification_status.replace("_", " ")}</span>}
              {row.verification_status !== "verified" && (
                <button className="sm" onClick={async () => { await api.post(`/api/career/knowledge/${row.id}/verify?status_value=verified`); reload(); }}>
                  <Check aria-hidden /> {t("career.markVerified")}
                </button>
              )}
              <button className="sm" onClick={() => startEdit(row)}><Pencil aria-hidden /> {t("common.edit")}</button>
              <button className="sm danger" onClick={() => remove(row.id)}><Trash2 aria-hidden /> {t("common.delete")}</button>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}

function PreviousApplicationsTab() {
  const apps = useApi<any[]>(() => api.get("/api/applications"));
  return (
    <div className="panel">
      <h3>Previous applications</h3>
      <p className="small muted">
        Historical applications are a searchable knowledge source — JDs, documents and outcomes inform future
        applications, but are never treated as evidence of skills (§8).
      </p>
      {apps.data?.length ? (
        <table>
          <thead><tr><th>Position</th><th>Organization</th><th>Fit</th><th>Status</th><th>Outcome</th><th>Lessons learned</th></tr></thead>
          <tbody>
            {apps.data.map((a) => (
              <tr key={a.id}>
                <td><Link to={`/applications/${a.id}`}>{a.job?.position_title}</Link></td>
                <td>{a.job?.organization_name}</td>
                <td>{a.fit_score != null ? `${Math.round(a.fit_score * 100)}%` : "—"}</td>
                <td><span className={`badge ${a.status}`}>{a.status}</span></td>
                <td>{a.outcome || "—"}</td>
                <td className="muted">{a.lessons_learned || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Empty icon={Inbox}>No applications recorded yet.</Empty>
      )}
    </div>
  );
}

export default function CareerKnowledge() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "overview";
  const setTab = (key: string) => {
    setParams(key === "overview" ? {} : { tab: key }, { replace: true });
  };
  const [reviewId, setReviewId] = useState<string | null>(null);
  const pendingCount = useApi<PendingIngestion[]>(() => api.get("/api/career/pending-ingestions?status_filter=pending"));

  const openPendingReview = (id: string) => {
    setReviewId(id);
    setTab("pending");
    pendingCount.reload();
  };

  const tabs = [
    { key: "overview", label: t("career.overview") },
    { key: "profile", label: t("career.profile") },
    ...ENTITIES.map((e) => ({ key: e.key, label: t(`career.entities.${e.key}`) })),
    { key: "knowledge", label: t("career.entities.knowledge") },
    {
      key: "pending",
      label: pendingCount.data?.length
        ? t("career.pendingCount", { n: pendingCount.data.length })
        : t("career.pending"),
    },
    { key: "documents", label: t("career.documents") },
    { key: "previous", label: t("career.previous") },
  ];

  return (
    <>
      <h1 className="page-title">{t("career.title")}</h1>
      <p className="page-sub">{t("career.sub")}{" "}
        <a href="/coach" onClick={(e) => { e.preventDefault(); openCoachWidget(); }}>{t("coach.askAboutCareer")}</a>
      </p>
      {!!pendingCount.data?.length && tab !== "pending" && (
        <div className="alert warn">
          {pendingCount.data.length === 1 ? t("career.pendingAlert", { n: pendingCount.data.length }) : t("career.pendingAlertPlural", { n: pendingCount.data.length })}{" "}
          <button className="sm" onClick={() => setTab("pending")}>{t("career.reviewNow")}</button>
        </div>
      )}
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      {tab === "overview" && <CareerOverview onOpenTab={(key: CareerTabKey) => setTab(key)} />}
      {tab === "profile" && <ProfileTab />}
      {tab === "knowledge" && <KnowledgeTab />}
      {ENTITIES.map((e) => tab === e.key && <EntityTab key={e.key} config={e} />)}
      {tab === "pending" && (
        <PendingIngestionsTab
          reviewId={reviewId}
          onReview={setReviewId}
          onCleared={() => pendingCount.reload()}
        />
      )}
      {tab === "documents" && <DocumentsTab onPendingCreated={openPendingReview} />}
      {tab === "previous" && <PreviousApplicationsTab />}
    </>
  );
}
