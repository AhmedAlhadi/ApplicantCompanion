import { api } from "../api/client";
import type { Application, DashboardStats } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";

const STATUS_ORDER = ["draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn"];

export default function Dashboard() {
  const stats = useApi<DashboardStats>(() => api.get("/api/dashboard/stats"));
  const apps = useApi<Application[]>(() => api.get("/api/applications"));

  if (stats.loading) return <p className="muted">Loading…</p>;
  const s = stats.data;

  return (
    <>
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">Your application pipeline at a glance.</p>

      <div className="grid cols-4">
        <div className="stat-card">
          <div className="stat-value">{s?.total_applications ?? 0}</div>
          <div className="stat-label">Total Applications</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{Math.round((s?.average_fit ?? 0) * 100)}%</div>
          <div className="stat-label">Average Job Fit</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{Math.round((s?.average_ats ?? 0) * 100)}%</div>
          <div className="stat-label">Average ATS Score</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{s?.applications_this_month ?? 0}</div>
          <div className="stat-label">Applications This Month</div>
        </div>
      </div>

      <div className="grid cols-2 mt">
        <div className="panel">
          <h3>Pipeline by Status</h3>
          <div className="row" style={{ gap: 8 }}>
            {STATUS_ORDER.map((status) => (
              <div key={status} className="stat-card" style={{ flex: 1, textAlign: "center", padding: "10px 6px" }}>
                <div className="stat-value" style={{ fontSize: 20 }}>{s?.by_status?.[status] ?? 0}</div>
                <div className="stat-label" style={{ textTransform: "capitalize" }}>{status}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h3>Highest-Fit Opportunities</h3>
          {s?.top_opportunities?.length ? (
            <table>
              <tbody>
                {s.top_opportunities.map((o) => (
                  <tr key={o.job_id}>
                    <td>
                      <Link to={`/jobs/${o.job_id}`}>{o.position_title || "Untitled role"}</Link>
                      <div className="small muted">{o.organization_name}</div>
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 700 }}>{Math.round(o.overall_score * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>No scored jobs yet — add a job to get started.</Empty>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>Recent Applications</h3>
        {apps.data?.length ? (
          <table>
            <thead>
              <tr><th>Position</th><th>Organization</th><th>Fit</th><th>ATS</th><th>Status</th></tr>
            </thead>
            <tbody>
              {apps.data.slice(0, 8).map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/applications/${a.id}`}>{a.job?.position_title || "Untitled"}</Link></td>
                  <td>{a.job?.organization_name}</td>
                  <td>{a.fit_score != null ? `${Math.round(a.fit_score * 100)}%` : "—"}</td>
                  <td>{a.ats_score_snapshot != null ? `${Math.round(a.ats_score_snapshot * 100)}%` : "—"}</td>
                  <td><span className={`badge ${a.status}`}>{a.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No applications yet.</Empty>
        )}
      </div>
    </>
  );
}
