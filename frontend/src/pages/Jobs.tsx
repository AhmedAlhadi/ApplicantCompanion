import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { Empty, ErrorBox, Link, useApi } from "../components/ui";

function NewJobForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [form, setForm] = useState({
    raw_jd_text: "", organization_name: "", position_title: "", location: "",
    deadline: "", source_url: "", notes: "", source_type: "paste",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await api.post<Job>("/api/jobs", {
        ...form,
        deadline: form.deadline || null,
      });
      onCreated(job.id);
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Could not create job");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h3>New job</h3>
      <label>Job description *</label>
      <textarea rows={10} placeholder="Paste the full job description here…" value={form.raw_jd_text}
        onChange={(e) => setForm({ ...form, raw_jd_text: e.target.value })} required />
      <div className="form-row">
        <div><label>Organization</label><input value={form.organization_name} onChange={(e) => setForm({ ...form, organization_name: e.target.value })} placeholder="Detected from the JD if empty" /></div>
        <div><label>Position</label><input value={form.position_title} onChange={(e) => setForm({ ...form, position_title: e.target.value })} placeholder="Detected from the JD if empty" /></div>
      </div>
      <div className="form-row">
        <div><label>Location</label><input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
        <div><label>Deadline</label><input value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} placeholder="e.g. 2026-09-01" /></div>
      </div>
      <div className="form-row">
        <div><label>Source URL</label><input value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} /></div>
        <div><label>Notes</label><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
      </div>
      <ErrorBox error={error} />
      <button className="primary mt" disabled={busy || !form.raw_jd_text.trim()}>
        {busy ? "Creating…" : "Create & Analyze"}
      </button>
    </form>
  );
}

export default function Jobs() {
  const { data, loading, reload } = useApi<Job[]>(() => api.get("/api/jobs"));
  const [showForm, setShowForm] = useState(false);
  const navigate = useNavigate();

  const onCreated = async (id: string) => {
    await api.post(`/api/jobs/${id}/analyze`, { include_research: true });
    navigate(`/jobs/${id}`);
  };

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-sub">Paste a job description — the platform parses it, researches the organization, matches your evidence and scores the fit.</p>
        </div>
        <button className="primary" onClick={() => setShowForm(!showForm)}>{showForm ? "Close" : "+ New Job"}</button>
      </div>
      {showForm && <NewJobForm onCreated={onCreated} />}
      {loading && <p className="muted">Loading…</p>}
      {!loading && !data?.length && !showForm && <Empty>No jobs yet. Click “New Job” to analyze your first vacancy.</Empty>}
      {data?.map((job) => (
        <div className="list-item" key={job.id}>
          <div className="row spread">
            <div>
              <div className="title"><Link to={`/jobs/${job.id}`}>{job.position_title || "Untitled role"}</Link></div>
              <div className="meta">
                {job.organization_name || "Unknown organization"}
                {job.location ? ` · ${job.location}` : ""}
                {job.contract_type ? ` · ${job.contract_type}` : ""}
                {job.deadline ? ` · deadline ${job.deadline}` : ""}
              </div>
            </div>
            <div className="row">
              {job.fit_score != null && (
                <span className={`badge ${job.fit_score >= 0.8 ? "strong" : "moderate"}`}>{Math.round(job.fit_score * 100)}% fit</span>
              )}
              <span className={`badge ${job.status}`}>{job.status}</span>
              <button className="sm danger" onClick={async () => { if (confirm("Delete this job?")) { await api.delete(`/api/jobs/${job.id}`); reload(); } }}>Delete</button>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
