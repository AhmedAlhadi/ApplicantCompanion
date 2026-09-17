import { useEffect, useState } from "react";
import { MessageSquare, PanelLeft } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useT } from "../lib/i18n";
import CoachContextPicker from "../components/coach/CoachContextPicker";
import CoachHistory from "../components/coach/CoachHistory";
import CoachThread from "../components/coach/CoachThread";
import { type CoachSelection, usePageCoachContext } from "../components/coach/coachContext";
import { useCoachSession } from "../components/coach/useCoachSession";

export default function CareerCoach() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const session = useCoachSession(params.get("c"));
  const page = usePageCoachContext();
  const [selection, setSelection] = useState<CoachSelection>({
    jobId: params.get("job") || "",
    applicationId: params.get("application") || "",
  });
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (params.get("c")) return;
    const jobId = params.get("job") || "";
    const applicationId = params.get("application") || "";
    if (jobId || applicationId) setSelection({ jobId, applicationId });
  }, [params]);

  useEffect(() => {
    const thread = session.thread;
    if (!thread) return;
    setSelection({
      jobId: thread.job_id || "",
      applicationId: thread.application_id || "",
    });
  }, [session.thread?.id]);

  const newChat = () => {
    session.selectConversation(null);
    const next = new URLSearchParams();
    if (selection.jobId) next.set("job", selection.jobId);
    if (selection.applicationId) next.set("application", selection.applicationId);
    setParams(next);
    setHistoryOpen(false);
  };

  const openConversation = (id: string) => {
    session.selectConversation(id);
    setParams({ c: id });
    setHistoryOpen(false);
  };

  const remove = async (id: string) => {
    const wasActive = session.activeId === id || params.get("c") === id;
    await session.remove(id);
    if (wasActive) setParams({});
  };

  const send = async () => {
    const id = await session.send(selection);
    if (id && params.get("c") !== id) setParams({ c: id });
  };

  return (
    <div className="coach-page">
      <div className="coach-page-head">
        <div>
          <h1 className="page-title"><MessageSquare className="page-title-icon" aria-hidden /> {t("coach.title")}</h1>
          <p className="page-sub">{t("coach.sub")}</p>
        </div>
        <button type="button" className="ghost coach-history-toggle" onClick={() => setHistoryOpen((v) => !v)}>
          <PanelLeft aria-hidden /> {t("coach.history")}
        </button>
      </div>
      <div className={`coach-workspace${historyOpen ? " history-open" : ""}`}>
        {historyOpen && (
          <button type="button" className="coach-history-backdrop" aria-label={t("common.close")} onClick={() => setHistoryOpen(false)} />
        )}
        <CoachHistory
          conversations={session.conversations.data}
          activeId={session.activeId}
          jobs={session.jobs.data}
          apps={session.apps.data}
          onSelect={openConversation}
          onNew={newChat}
          onDelete={remove}
        />
        <section className="coach-main">
          <CoachContextPicker
            selection={selection}
            followPage={false}
            page={page}
            jobs={session.jobs.data}
            apps={session.apps.data}
            onSelect={(next) => setSelection(next)}
          />
          <CoachThread
            messages={session.messages}
            draft={session.draft}
            onDraft={session.setDraft}
            busy={session.busy}
            error={session.error}
            selection={selection}
            onSend={send}
          />
        </section>
      </div>
    </div>
  );
}
