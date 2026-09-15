import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { Application, CoachConversation, CoachMessage, Job } from "../api/types";
import { Empty, ErrorBox, useApi } from "../components/ui";
import { t, useT } from "../lib/i18n";

function EvidencePeek({ entityType, entityId }: { entityType: string; entityId: string }) {
  const evidence = useApi<any[]>(() => api.get(`/api/career/evidence/${entityType}/${entityId}`), [entityType, entityId]);
  if (evidence.loading) return <p className="small muted">{t("editor.resolving")}</p>;
  if (!evidence.data?.length) return <p className="small muted">{t("editor.noProvenance")}</p>;
  return (
    <div className="evidence-pop">
      {evidence.data.map((ev) => (
        <div key={ev.id} className="mb">
          <div><strong>{t("editor.source")}</strong> {ev.source_document ?? t("editor.manualEntry")}{ev.source_section ? ` · ${ev.source_section}` : ""}</div>
          {ev.original_text && <div className="muted">“{ev.original_text}”</div>}
          <div className="small"><span className={`badge ${ev.verification_status}`}>{ev.verification_status}</span></div>
        </div>
      ))}
    </div>
  );
}

export default function CareerCoach() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const conversations = useApi<CoachConversation[]>(() => api.get("/api/coach/conversations"));
  const jobs = useApi<Job[]>(() => api.get("/api/jobs"));
  const apps = useApi<Application[]>(() => api.get("/api/applications"));
  const [activeId, setActiveId] = useState<string | null>(params.get("c"));
  const [thread, setThread] = useState<CoachConversation | null>(null);
  const [draft, setDraft] = useState("");
  const [jobId, setJobId] = useState(params.get("job") || "");
  const [appId, setAppId] = useState(params.get("application") || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openCite, setOpenCite] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId) {
      setThread(null);
      return;
    }
    let cancelled = false;
    api.get<CoachConversation>(`/api/coach/conversations/${activeId}`).then((row) => {
      if (!cancelled) {
        setThread(row);
        setJobId(row.job_id || jobId);
        setAppId(row.application_id || appId);
      }
    }).catch(() => {
      if (!cancelled) setThread(null);
    });
    return () => { cancelled = true; };
  }, [activeId]);

  const messages = thread?.messages || [];

  const startConversation = async () => {
    setError(null);
    const created = await api.post<CoachConversation>("/api/coach/conversations", {
      job_id: jobId || null,
      application_id: appId || null,
    });
    setActiveId(created.id);
    setParams({ c: created.id });
    conversations.reload();
    setThread({ ...created, messages: [] });
    return created.id;
  };

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      let conversationId = activeId;
      if (!conversationId) conversationId = await startConversation();
      const reply = await api.post<CoachMessage>(`/api/coach/conversations/${conversationId}/messages`, {
        content: text,
        job_id: jobId || null,
        application_id: appId || null,
      });
      setDraft("");
      setThread((prev) => ({
        ...(prev || { id: conversationId!, title: text.slice(0, 80), job_id: jobId || null, application_id: appId || null, created_at: null, updated_at: null, messages: [] }),
        messages: [
          ...(prev?.messages || []),
          { id: `u-${Date.now()}`, role: "user", content: text, citations: [], created_at: new Date().toISOString() },
          reply,
        ],
      }));
      conversations.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("coach.error"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await api.delete(`/api/coach/conversations/${id}`);
    if (activeId === id) {
      setActiveId(null);
      setThread(null);
      setParams({});
    }
    conversations.reload();
  };

  const jobOptions = useMemo(() => jobs.data || [], [jobs.data]);
  const appOptions = useMemo(() => apps.data || [], [apps.data]);

  return (
    <>
      <h1 className="page-title"><MessageSquare className="page-title-icon" aria-hidden /> {t("coach.title")}</h1>
      <p className="page-sub">{t("coach.sub")}</p>
      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <div className="panel">
          <div className="row spread mb">
            <h3>{t("coach.history")}</h3>
            <button className="sm" onClick={() => { setActiveId(null); setThread(null); setParams({}); }}><Plus aria-hidden /> {t("coach.newChat")}</button>
          </div>
          {!conversations.data?.length && <Empty>{t("coach.empty")}</Empty>}
          {conversations.data?.map((c) => (
            <div key={c.id} className="row spread" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <button className={activeId === c.id ? "primary sm" : "sm ghost"} onClick={() => { setActiveId(c.id); setParams({ c: c.id }); }}>
                {c.title || t("common.untitled")}
              </button>
              <button className="sm ghost" onClick={() => remove(c.id)} aria-label={t("common.delete")}><Trash2 aria-hidden /></button>
            </div>
          ))}
        </div>
        <div className="panel">
          <label>{t("coach.context")}</label>
          <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">{t("coach.noContext")}</option>
            {jobOptions.map((job) => (
              <option key={job.id} value={job.id}>{t("coach.jobContext", { title: job.position_title || job.organization_name || job.id })}</option>
            ))}
          </select>
          <select className="mt" value={appId} onChange={(e) => setAppId(e.target.value)}>
            <option value="">{t("coach.noContext")}</option>
            {appOptions.map((app) => (
              <option key={app.id} value={app.id}>{t("coach.appContext", { title: app.job?.position_title || app.id })}</option>
            ))}
          </select>
          <div className="mt" style={{ minHeight: 240 }}>
            {!messages.length && <Empty icon={MessageSquare}>{t("coach.empty")}</Empty>}
            {messages.map((m) => (
              <div key={m.id} className="mb">
                <div className="small muted">{m.role === "user" ? t("map.you") : t("coach.title")}</div>
                <p style={{ whiteSpace: "pre-wrap" }}>{m.content}</p>
                {!!m.citations?.length && (
                  <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                    <span className="small muted">{t("coach.citations")}:</span>
                    {m.citations.map((cite) => {
                      const key = `${cite.entity_type}:${cite.entity_id}`;
                      return (
                        <button
                          key={key}
                          type="button"
                          className="sm"
                          onClick={() => setOpenCite(openCite === key ? null : key)}
                        >
                          {cite.label} {cite.verification_status ? `(${cite.verification_status})` : ""}
                        </button>
                      );
                    })}
                  </div>
                )}
                {m.citations?.map((cite) => {
                  const key = `${cite.entity_type}:${cite.entity_id}`;
                  return openCite === key ? <EvidencePeek key={key} entityType={cite.entity_type} entityId={cite.entity_id} /> : null;
                })}
              </div>
            ))}
          </div>
          <ErrorBox error={error} />
          <form className="mt" onSubmit={send}>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t("coach.placeholder")} rows={3} />
            <button className="primary mt" disabled={busy || !draft.trim()}>{busy ? t("coach.sending") : t("coach.send")}</button>
          </form>
        </div>
      </div>
    </>
  );
}
