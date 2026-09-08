import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, Plus, Sparkles, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { Empty, ErrorBox, Link, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

function NewJobForm({ onCreated }: { onCreated: (id: string) => void }) {
  const { t } = useT();
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
      setError(typeof err.detail === "string" ? err.detail : t("jobs.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h3>{t("jobs.newJob")}</h3>
      <label>{t("jobs.jdRequired")}</label>
      <textarea rows={10} placeholder={t("jobs.jdPh")} value={form.raw_jd_text}
        onChange={(e) => setForm({ ...form, raw_jd_text: e.target.value })} required />
      <div className="form-row">
        <div><label>{t("onboarding.organization")}</label><input value={form.organization_name} onChange={(e) => setForm({ ...form, organization_name: e.target.value })} placeholder={t("jobs.orgPh")} /></div>
        <div><label>{t("onboarding.position")}</label><input value={form.position_title} onChange={(e) => setForm({ ...form, position_title: e.target.value })} placeholder={t("jobs.posPh")} /></div>
      </div>
      <div className="form-row">
        <div><label>{t("jobs.location")}</label><input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
        <div><label>{t("applications.deadline")}</label><input value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} placeholder={t("jobs.deadlinePh")} /></div>
      </div>
      <div className="form-row">
        <div><label>{t("jobs.sourceUrl")}</label><input value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} /></div>
        <div><label>{t("jobs.notes")}</label><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
      </div>
      <ErrorBox error={error} />
      <button className="primary mt" disabled={busy || !form.raw_jd_text.trim()}>
        {busy ? t("jobs.creating") : <><Sparkles aria-hidden /> {t("jobs.createAnalyze")}</>}
      </button>
    </form>
  );
}

export default function Jobs() {
  const { t } = useT();
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
          <h1 className="page-title">{t("jobs.title")}</h1>
          <p className="page-sub">{t("jobs.sub")}</p>
        </div>
        <button className="primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? <><X aria-hidden /> {t("jobs.close")}</> : <><Plus aria-hidden /> {t("jobs.newJob")}</>}
        </button>
      </div>
      {showForm && <NewJobForm onCreated={onCreated} />}
      {loading && <p className="muted">{t("common.loading")}</p>}
      {!loading && !data?.length && !showForm && <Empty icon={Briefcase}>{t("jobs.empty")}</Empty>}
      {data?.map((job) => (
        <div className="list-item" key={job.id}>
          <div className="row spread">
            <div>
              <div className="title"><Link to={`/jobs/${job.id}`}>{job.position_title || t("common.untitledRole")}</Link></div>
              <div className="meta">
                {job.organization_name || t("common.unknownOrg")}
                {job.location ? ` · ${job.location}` : ""}
                {job.contract_type ? ` · ${job.contract_type}` : ""}
                {job.deadline ? ` · ${t("jobs.deadline", { date: job.deadline })}` : ""}
              </div>
            </div>
            <div className="row">
              {job.fit_score != null && (
                <span className={`badge ${job.fit_score >= 0.8 ? "strong" : "moderate"}`}>{t("score.jobFit", { pct: Math.round(job.fit_score * 100) })}</span>
              )}
              <span className={`badge ${job.status}`}>{t(`status.${job.status}`)}</span>
              <button className="sm danger" onClick={async () => { if (confirm(t("common.confirmDeleteJob"))) { await api.delete(`/api/jobs/${job.id}`); reload(); } }}><Trash2 aria-hidden /> {t("common.delete")}</button>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
