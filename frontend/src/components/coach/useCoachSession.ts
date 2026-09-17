import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Application, CoachConversation, CoachMessage, Job } from "../../api/types";
import { t } from "../../lib/i18n";
import { useApi } from "../ui";
import type { CoachSelection } from "./coachContext";

export function useCoachSession(externalId?: string | null) {
  const conversations = useApi<CoachConversation[]>(() => api.get("/api/coach/conversations"));
  const jobs = useApi<Job[]>(() => api.get("/api/jobs"));
  const apps = useApi<Application[]>(() => api.get("/api/applications"));
  const [activeId, setActiveId] = useState<string | null>(externalId ?? null);
  const [thread, setThread] = useState<CoachConversation | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (externalId === undefined) return;
    setActiveId(externalId);
  }, [externalId]);

  useEffect(() => {
    if (!activeId) {
      setThread(null);
      return;
    }
    let cancelled = false;
    api.get<CoachConversation>(`/api/coach/conversations/${activeId}`).then((row) => {
      if (!cancelled) setThread(row);
    }).catch(() => {
      if (!cancelled) setThread(null);
    });
    return () => { cancelled = true; };
  }, [activeId]);

  const selectConversation = (id: string | null) => {
    setActiveId(id);
    setError(null);
    if (!id) setThread(null);
  };

  const startConversation = async (selection: CoachSelection) => {
    const created = await api.post<CoachConversation>("/api/coach/conversations", {
      job_id: selection.jobId || null,
      application_id: selection.applicationId || null,
    });
    setActiveId(created.id);
    setThread({ ...created, messages: [] });
    conversations.reload();
    return created.id;
  };

  const send = async (selection: CoachSelection) => {
    const text = draft.trim();
    if (!text || busy) return activeId;
    setBusy(true);
    setError(null);
    try {
      let conversationId = activeId;
      if (!conversationId) conversationId = await startConversation(selection);
      const reply = await api.post<CoachMessage>(`/api/coach/conversations/${conversationId}/messages`, {
        content: text,
        job_id: selection.jobId || null,
        application_id: selection.applicationId || null,
      });
      setDraft("");
      setThread((prev) => ({
        ...(prev || {
          id: conversationId!,
          title: text.slice(0, 80),
          job_id: selection.jobId || null,
          application_id: selection.applicationId || null,
          created_at: null,
          updated_at: null,
          messages: [],
        }),
        title: prev?.title || text.slice(0, 80),
        messages: [
          ...(prev?.messages || []),
          { id: `u-${Date.now()}`, role: "user", content: text, citations: [], created_at: new Date().toISOString() },
          reply,
        ],
      }));
      conversations.reload();
      return conversationId;
    } catch (err: unknown) {
      const detail = err && typeof err === "object" && "detail" in err ? (err as { detail: unknown }).detail : null;
      setError(typeof detail === "string" ? detail : t("coach.error"));
      return activeId;
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await api.delete(`/api/coach/conversations/${id}`);
    if (activeId === id) {
      setActiveId(null);
      setThread(null);
    }
    conversations.reload();
  };

  return {
    conversations,
    jobs,
    apps,
    activeId,
    thread,
    messages: thread?.messages || [],
    draft,
    setDraft,
    busy,
    error,
    setError,
    selectConversation,
    startConversation,
    send,
    remove,
  };
}
