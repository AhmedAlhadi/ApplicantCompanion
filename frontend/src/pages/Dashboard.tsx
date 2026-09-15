import { Briefcase, CalendarDays, FileStack, Gauge, ShieldCheck } from "lucide-react";
import { api } from "../api/client";
import type { Application, DashboardStats, UserSettings } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";
import { showAts } from "../lib/ats";
import { useT } from "../lib/i18n";

const STATUS_ORDER = ["draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn"];

export default function Dashboard() {
  const { t } = useT();
  const stats = useApi<DashboardStats>(() => api.get("/api/dashboard/stats"));
  const apps = useApi<Application[]>(() => api.get("/api/applications"));
  const settings = useApi<UserSettings>(() => api.get("/api/settings"));
  const atsVisible = showAts(settings.data);

  if (stats.loading) {
    return (
      <>
        <div className="skeleton skeleton-text" style={{ width: 220 }} />
        <div className="grid cols-4 mt">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton skeleton-card" />
          ))}
        </div>
        <div className="grid cols-2 mt">
          <div className="skeleton" style={{ height: 220 }} />
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      </>
    );
  }
  const s = stats.data;

  return (
    <>
      <h1 className="page-title">{t("dashboard.title")}</h1>
      <p className="page-sub">{t("dashboard.sub")}</p>

      <div className="grid cols-4">
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.total_applications ?? 0}</div>
            <FileStack className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("dashboard.totalApps")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{Math.round((s?.average_fit ?? 0) * 100)}%</div>
            <Gauge className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("dashboard.avgFit")}</div>
        </div>
        {atsVisible && (
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{Math.round((s?.average_ats ?? 0) * 100)}%</div>
            <ShieldCheck className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("dashboard.avgAts")}</div>
        </div>
        )}
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.applications_this_month ?? 0}</div>
            <CalendarDays className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("dashboard.thisMonth")}</div>
        </div>
      </div>

      <div className="grid cols-2 mt">
        <div className="panel">
          <h3>{t("dashboard.pipeline")}</h3>
          <div className="row" style={{ gap: 8 }}>
            {STATUS_ORDER.map((status) => (
              <div key={status} className="stat-card" style={{ flex: 1, textAlign: "center", padding: "10px 6px" }}>
                <div className="stat-value" style={{ fontSize: 20 }}>{s?.by_status?.[status] ?? 0}</div>
                <div className="stat-label">{t(`status.${status}`)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h3>{t("dashboard.topFit")}</h3>
          {s?.top_opportunities?.length ? (
            <table>
              <tbody>
                {s.top_opportunities.map((o) => (
                  <tr key={o.job_id}>
                    <td>
                      <Link to={`/jobs/${o.job_id}`}>{o.position_title || t("common.untitledRole")}</Link>
                      <div className="small muted">{o.organization_name}</div>
                    </td>
                    <td style={{ textAlign: "end", fontWeight: 700 }}>{Math.round(o.overall_score * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon={Briefcase}>{t("dashboard.noScored")}</Empty>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>{t("dashboard.recent")}</h3>
        {apps.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>{t("dashboard.position")}</th>
                <th>{t("dashboard.organization")}</th>
                <th>{t("dashboard.fit")}</th>
                {atsVisible && <th>{t("dashboard.ats")}</th>}
                <th>{t("dashboard.status")}</th>
              </tr>
            </thead>
            <tbody>
              {apps.data.slice(0, 8).map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/applications/${a.id}`}>{a.job?.position_title || t("common.untitled")}</Link></td>
                  <td>{a.job?.organization_name}</td>
                  <td>{a.fit_score != null ? `${Math.round(a.fit_score * 100)}%` : "—"}</td>
                  {atsVisible && <td>{a.ats_score_snapshot != null ? `${Math.round(a.ats_score_snapshot * 100)}%` : "—"}</td>}
                  <td><span className={`badge ${a.status}`}>{t(`status.${a.status}`)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon={FileStack}>{t("dashboard.noApps")}</Empty>
        )}
      </div>
    </>
  );
}
