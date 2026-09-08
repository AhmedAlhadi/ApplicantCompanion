import { FileStack } from "lucide-react";
import { api } from "../api/client";
import type { Application } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

const STATUSES = ["draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn"];

export default function Applications() {
  const { t } = useT();
  const { data, loading, reload } = useApi<Application[]>(() => api.get("/api/applications"));

  const setStatus = async (id: string, status: string) => {
    await api.put(`/api/applications/${id}`, { status });
    reload();
  };

  return (
    <>
      <h1 className="page-title">{t("applications.title")}</h1>
      <p className="page-sub">{t("applications.sub")}</p>
      {loading && <p className="muted">{t("common.loading")}</p>}
      {!loading && !data?.length && <Empty icon={FileStack}>{t("applications.empty")}</Empty>}
      {!!data?.length && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>{t("applications.position")}</th>
                <th>{t("applications.organization")}</th>
                <th>{t("applications.deadline")}</th>
                <th>{t("applications.fit")}</th>
                <th>{t("applications.ats")}</th>
                <th>{t("applications.status")}</th>
                <th>{t("applications.notes")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/applications/${a.id}`}>{a.job?.position_title || t("common.untitled")}</Link></td>
                  <td>{a.job?.organization_name}</td>
                  <td className="muted">{a.job?.deadline || "—"}</td>
                  <td style={{ fontWeight: 700 }}>{a.fit_score != null ? `${Math.round(a.fit_score * 100)}%` : "—"}</td>
                  <td>{a.ats_score_snapshot != null ? `${Math.round(a.ats_score_snapshot * 100)}%` : "—"}</td>
                  <td>
                    <select value={a.status} onChange={(e) => setStatus(a.id, e.target.value)} style={{ width: "auto", padding: "4px 8px" }}>
                      {STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
                    </select>
                  </td>
                  <td className="small muted">{a.outcome || a.user_notes || "—"}</td>
                  <td><Link to={`/applications/${a.id}`}>{t("common.open")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
