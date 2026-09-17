import { useMemo, useState } from "react";
import { MessageSquare, Plus, Search, Trash2 } from "lucide-react";
import type { Application, CoachConversation, Job } from "../../api/types";
import { useT } from "../../lib/i18n";
import { Empty } from "../ui";
import { appLabel, filterText, formatRelativeTime, jobLabel } from "./coachContext";

type Props = {
  conversations: CoachConversation[] | null;
  activeId: string | null;
  jobs: Job[] | null;
  apps: Application[] | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
};

export default function CoachHistory({ conversations, activeId, jobs, apps, onSelect, onNew, onDelete }: Props) {
  const { t, lang } = useT();
  const [query, setQuery] = useState("");
  const untitled = t("common.untitled");
  const untitledRole = t("common.untitledRole");
  const unknownOrg = t("common.unknownOrg");

  const rows = useMemo(() => {
    const list = conversations || [];
    return list.filter((c) => {
      const app = c.application_id ? (apps || []).find((row) => row.id === c.application_id) : null;
      const job = c.job_id ? (jobs || []).find((row) => row.id === c.job_id) : null;
      const context = app
        ? appLabel(app, untitledRole, unknownOrg)
        : job
          ? jobLabel(job, untitledRole, unknownOrg)
          : t("coach.generalTitle");
      return filterText(query, c.title, context, untitled);
    });
  }, [apps, conversations, jobs, lang, query, t, untitled, untitledRole, unknownOrg]);

  const contextLabel = (c: CoachConversation) => {
    if (c.application_id) {
      const app = (apps || []).find((row) => row.id === c.application_id);
      return app ? appLabel(app, untitledRole, unknownOrg) : t("coach.appsGroup");
    }
    if (c.job_id) {
      const job = (jobs || []).find((row) => row.id === c.job_id);
      return job ? jobLabel(job, untitledRole, unknownOrg) : t("coach.jobsGroup");
    }
    return t("coach.generalTitle");
  };

  return (
    <div className="coach-history">
      <div className="coach-history-head">
        <div>
          <h3>{t("coach.history")}</h3>
          <p className="small muted">{t("coach.isolation")}</p>
        </div>
        <button type="button" className="sm primary" onClick={onNew}>
          <Plus aria-hidden /> {t("coach.newChat")}
        </button>
      </div>
      <div className="coach-history-search">
        <Search aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("coach.searchHistory")}
          aria-label={t("coach.searchHistory")}
        />
      </div>
      <div className="coach-history-list">
        {!conversations?.length && <Empty icon={MessageSquare}>{t("coach.noHistory")}</Empty>}
        {!!conversations?.length && !rows.length && <p className="coach-history-empty">{t("coach.noMatch")}</p>}
        {rows.map((c) => (
          <div key={c.id} className={`coach-history-item${activeId === c.id ? " active" : ""}`}>
            <button type="button" className="coach-history-main" onClick={() => onSelect(c.id)}>
              <span className="coach-history-title">{c.title || t("coach.untitledChat")}</span>
              <span className="coach-history-meta">
                <span>{contextLabel(c)}</span>
                <span>{formatRelativeTime(c.updated_at || c.created_at)}</span>
              </span>
            </button>
            <button
              type="button"
              className="ghost icon-only coach-history-delete"
              onClick={() => {
                if (confirm(t("common.confirmDelete"))) onDelete(c.id);
              }}
              aria-label={t("common.delete")}
            >
              <Trash2 aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
