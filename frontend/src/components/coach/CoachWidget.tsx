import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { History, Maximize2, MessageSquare, Plus, X } from "lucide-react";
import { motion } from "framer-motion";
import { useT } from "../../lib/i18n";
import CoachContextPicker from "./CoachContextPicker";
import CoachHistory from "./CoachHistory";
import CoachThread from "./CoachThread";
import {
  EMPTY_SELECTION,
  OPEN_COACH_EVENT,
  openCoachWidget,
  pageSelection,
  type CoachSelection,
  usePageCoachContext,
} from "./coachContext";
import { useCoachSession } from "./useCoachSession";

export { openCoachWidget };

export default function CoachWidget() {
  const { t } = useT();
  const location = useLocation();
  const navigate = useNavigate();
  const page = usePageCoachContext();
  const session = useCoachSession();
  const [open, setOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [followPage, setFollowPage] = useState(true);
  const [selection, setSelection] = useState<CoachSelection>(EMPTY_SELECTION);

  useEffect(() => {
    const onOpen = () => {
      setOpen(true);
      setHistoryOpen(false);
    };
    window.addEventListener(OPEN_COACH_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_COACH_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (historyOpen) setHistoryOpen(false);
        else setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, historyOpen]);

  useEffect(() => {
    if (!followPage) return;
    setSelection(pageSelection(page));
  }, [followPage, page.jobId, page.applicationId, page.source]);

  useEffect(() => {
    const thread = session.thread;
    if (!thread || followPage) return;
    setSelection({
      jobId: thread.job_id || "",
      applicationId: thread.application_id || "",
    });
  }, [session.thread?.id, followPage]);

  if (location.pathname === "/coach") return null;

  const applySelection = (next: CoachSelection, nextFollow: boolean) => {
    setSelection(next);
    setFollowPage(nextFollow);
  };

  const newChat = () => {
    session.selectConversation(null);
    session.setError(null);
    setFollowPage(true);
    setSelection(pageSelection(page));
    setHistoryOpen(false);
  };

  const openConversation = (id: string) => {
    const conv = session.conversations.data?.find((row) => row.id === id);
    session.selectConversation(id);
    setFollowPage(false);
    if (conv) {
      setSelection({ jobId: conv.job_id || "", applicationId: conv.application_id || "" });
    }
    setHistoryOpen(false);
  };

  const openFull = () => {
    const params = new URLSearchParams();
    if (session.activeId) params.set("c", session.activeId);
    else {
      if (selection.jobId) params.set("job", selection.jobId);
      if (selection.applicationId) params.set("application", selection.applicationId);
    }
    const query = params.toString();
    setOpen(false);
    navigate(query ? `/coach?${query}` : "/coach");
  };

  if (!open) {
    return (
      <button
        type="button"
        className="coach-fab"
        onClick={() => setOpen(true)}
        aria-label={t("coach.openWidget")}
      >
        <MessageSquare aria-hidden />
      </button>
    );
  }

  return (
    <motion.div
      className="coach-widget"
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      role="dialog"
      aria-label={t("coach.title")}
    >
      <header className="coach-widget-head">
        <div className="coach-widget-title">
          <MessageSquare aria-hidden />
          <strong>{t("coach.title")}</strong>
        </div>
        <div className="coach-widget-actions">
          <button type="button" className="ghost icon-only" onClick={() => setHistoryOpen((v) => !v)} aria-label={t("coach.showHistory")}>
            <History aria-hidden />
          </button>
          <button type="button" className="ghost icon-only" onClick={newChat} aria-label={t("coach.newChat")}>
            <Plus aria-hidden />
          </button>
          <button type="button" className="ghost icon-only" onClick={openFull} aria-label={t("coach.openFull")}>
            <Maximize2 aria-hidden />
          </button>
          <button type="button" className="ghost icon-only" onClick={() => setOpen(false)} aria-label={t("coach.closeWidget")}>
            <X aria-hidden />
          </button>
        </div>
      </header>
      {historyOpen ? (
        <CoachHistory
          conversations={session.conversations.data}
          activeId={session.activeId}
          jobs={session.jobs.data}
          apps={session.apps.data}
          onSelect={openConversation}
          onNew={newChat}
          onDelete={(id) => session.remove(id)}
        />
      ) : (
        <>
          <CoachContextPicker
            compact
            selection={selection}
            followPage={followPage}
            page={page}
            jobs={session.jobs.data}
            apps={session.apps.data}
            onSelect={applySelection}
          />
          <CoachThread
            messages={session.messages}
            draft={session.draft}
            onDraft={session.setDraft}
            busy={session.busy}
            error={session.error}
            selection={selection}
            onSend={() => session.send(selection)}
          />
        </>
      )}
    </motion.div>
  );
}
