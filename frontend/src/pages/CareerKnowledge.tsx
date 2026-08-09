import { FormEvent, useState } from "react";
import { api } from "../api/client";
import { Empty, ErrorBox, Link, useApi } from "../components/ui";

/* Field-driven CRUD tabs keep every career entity editable with provenance
   badges (§47: Verified / Unverified / Needs Review). */

type Field = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "list" | "number" | "checkbox";
  required?: boolean;
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
      { name: "technologies", label: "Technologies (one per line)", type: "list" },
      { name: "domains", label: "Domains (one per line)", type: "list" },
      { name: "leadership", label: "Leadership (one per line)", type: "list" },
      { name: "stakeholders", label: "Stakeholders (one per line)", type: "list" },
    ],
  },
  {
    key: "projects", label: "Projects", path: "/api/career/projects", verifiable: true,
    title: (r) => r.name, subtitle: (r) => r.role,
    fields: [
      { name: "name", label: "Project name", required: true },
      { name: "role", label: "Your role" },
      { name: "description", label: "Description", type: "textarea" },
      { name: "technologies", label: "Technologies (one per line)", type: "list" },
      { name: "outcomes", label: "Outcomes (one per line)", type: "list" },
      { name: "urls", label: "URLs (one per line)", type: "list" },
    ],
  },
  {
    key: "achievements", label: "Achievements", path: "/api/career/achievements", verifiable: true,
    title: (r) => r.title || r.description.slice(0, 80), subtitle: (r) => r.quantified_result,
    fields: [
      { name: "title", label: "Title" },
      { name: "description", label: "Description", type: "textarea", required: true },
      { name: "quantified_result", label: "Quantified result" },
      { name: "skills", label: "Related skills (one per line)", type: "list" },
    ],
  },
  {
    key: "skills", label: "Skills", path: "/api/career/skills", verifiable: true,
    title: (r) => r.canonical_name || r.name,
    subtitle: (r) => [r.category, r.proficiency, r.synonyms?.length ? `aka: ${r.synonyms.join(", ")}` : ""].filter(Boolean).join(" · "),
    fields: [
      { name: "name", label: "Skill", required: true },
      { name: "category", label: "Category (technical/functional/domain/behavioral/tools/methodologies)" },
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
      { name: "credential_id", label: "Credential ID" },
      { name: "url", label: "URL" },
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
      base[f.name] = f.type === "list" ? (v ?? []).join("\n") : v ?? (f.type === "checkbox" ? false : "");
    }
    return base;
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      else payload[f.name] = v === "" ? (f.required ? v : null) : v;
    }
    try {
      if (initial?.id) await api.put(`${config.path}/${initial.id}`, payload);
      else await api.post(config.path, payload);
      onSaved();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Save failed");
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
  const { data, reload, loading } = useApi<any[]>(() => api.get(config.path));
  const [editing, setEditing] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);

  const remove = async (id: string) => {
    if (!confirm("Delete this entry?")) return;
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
        <button className="primary sm" onClick={() => { setAdding(true); setEditing(null); }}>+ Add</button>
      </div>
      {(adding || editing) && (
        <EntityForm config={config} initial={editing} onSaved={() => { setAdding(false); setEditing(null); reload(); }} onCancel={() => { setAdding(false); setEditing(null); }} />
      )}
      {loading && <p className="muted">Loading…</p>}
      {!loading && !data?.length && <Empty>Nothing here yet — add entries manually or ingest a document.</Empty>}
      {data?.map((row) => (
        <div className="list-item" key={row.id}>
          <div className="row spread">
            <div>
              <div className="title">{config.title(row)}</div>
              {config.subtitle && <div className="meta">{config.subtitle(row)}</div>}
            </div>
            <div className="row">
              {row.verification_status && <span className={`badge ${row.verification_status}`}>{row.verification_status.replace("_", " ")}</span>}
              <button className="sm ghost" onClick={() => setEvidenceFor(evidenceFor === row.id ? null : row.id)}>View Evidence</button>
              {config.verifiable && row.verification_status !== "verified" && (
                <button className="sm" onClick={() => verify(row.id, "verified")}>Mark verified</button>
              )}
              <button className="sm" onClick={() => { setEditing(row); setAdding(false); }}>Edit</button>
              <button className="sm danger" onClick={() => remove(row.id)}>Delete</button>
            </div>
          </div>
          {evidenceFor === row.id && <EvidencePanel entityType={config.key === "education" ? "education" : config.key.replace(/s$/, "")} entityId={row.id} />}
        </div>
      ))}
    </>
  );
}

function ProfileTab() {
  const { data, reload, loading } = useApi<any>(() => api.get("/api/career/profile"));
  const [form, setForm] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const f = form ?? data ?? {};
  if (loading) return <p className="muted">Loading…</p>;
  const set = (k: string, v: string) => setForm({ ...f, [k]: v });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    await api.put("/api/career/profile", {
      full_name: f.full_name ?? "", headline: f.headline ?? "", summary: f.summary ?? "",
      email: f.email ?? "", phone: f.phone ?? "", location: f.location ?? "",
      links: f.links ?? {}, preferred_positioning: f.preferred_positioning ?? "",
      career_narratives: f.career_narratives ?? [],
    });
    setSaved(true);
    setForm(null);
    reload();
    setTimeout(() => setSaved(false), 2000);
  };
  return (
    <form className="panel" onSubmit={save}>
      <div className="form-row">
        <div><label>Full name</label><input value={f.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} /></div>
        <div><label>Headline</label><input value={f.headline ?? ""} onChange={(e) => set("headline", e.target.value)} /></div>
      </div>
      <label>Professional summary</label>
      <textarea value={f.summary ?? ""} onChange={(e) => set("summary", e.target.value)} />
      <div className="form-row">
        <div><label>Email</label><input value={f.email ?? ""} onChange={(e) => set("email", e.target.value)} /></div>
        <div><label>Phone</label><input value={f.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></div>
      </div>
      <div className="form-row">
        <div><label>Location</label><input value={f.location ?? ""} onChange={(e) => set("location", e.target.value)} /></div>
        <div><label>LinkedIn URL</label><input value={f.links?.linkedin ?? ""} onChange={(e) => set("links", { ...(f.links ?? {}), linkedin: e.target.value })} /></div>
      </div>
      <label>Preferred career positioning</label>
      <textarea value={f.preferred_positioning ?? ""} onChange={(e) => set("preferred_positioning", e.target.value)} />
      <div className="row mt">
        <button className="primary">Save profile</button>
        {saved && <span className="badge verified">Saved</span>}
      </div>
    </form>
  );
}

function DocumentsTab() {
  const docs = useApi<any[]>(() => api.get("/api/career/documents"));
  const [text, setText] = useState("");
  const [docType, setDocType] = useState("cv");
  const [result, setResult] = useState<any | null>(null);
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
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const ingestText = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await api.post<any>("/api/career/ingest-text", { text, doc_type: docType });
      setResult(resp.created);
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
    try {
      const resp = await api.post<any>(`/api/career/documents/${id}/ingest`);
      setResult(resp);
      docs.reload();
    } finally {
      setBusy(false);
    }
  };

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
          <button className="primary mt" onClick={ingestText} disabled={busy || !text.trim()}>Extract structured knowledge</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {result && (
        <div className="alert info">
          Extracted: {Object.entries(result).filter(([, v]) => typeof v === "number").map(([k, v]) => `${k}: ${v}`).join(" · ")} — review them under the
          relevant tabs and mark them verified.
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
                  <td>{d.ingested ? <span className="badge verified">yes</span> : <span className="badge unverified">no</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    {!d.ingested && <button className="sm" onClick={() => ingestDoc(d.id)} disabled={busy}>Run extraction</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No documents uploaded yet.</Empty>
        )}
      </div>
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
        <Empty>No applications recorded yet.</Empty>
      )}
    </div>
  );
}

export default function CareerKnowledge() {
  const [tab, setTab] = useState("profile");
  const tabs = [{ key: "profile", label: "Profile" }, ...ENTITIES.map((e) => ({ key: e.key, label: e.label })), { key: "documents", label: "Documents" }, { key: "previous", label: "Previous Applications" }];
  return (
    <>
      <h1 className="page-title">Career Knowledge</h1>
      <p className="page-sub">The authoritative, evidence-tracked source for every claim about your career.</p>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      {tab === "profile" && <ProfileTab />}
      {ENTITIES.map((e) => tab === e.key && <EntityTab key={e.key} config={e} />)}
      {tab === "documents" && <DocumentsTab />}
      {tab === "previous" && <PreviousApplicationsTab />}
    </>
  );
}
