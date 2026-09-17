import { api } from "../../api/client";
import { t } from "../../lib/i18n";
import { useApi } from "../ui";

export default function CoachEvidencePeek({ entityType, entityId }: { entityType: string; entityId: string }) {
  const evidence = useApi<Array<{
    id: string;
    source_document?: string | null;
    source_section?: string | null;
    original_text?: string | null;
    verification_status?: string;
  }>>(() => api.get(`/api/career/evidence/${entityType}/${entityId}`), [entityType, entityId]);
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
