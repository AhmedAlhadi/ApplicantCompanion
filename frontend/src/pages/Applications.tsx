import { api } from "../api/client";
import type { Application } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";

const STATUSES = ["draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn"];

export default function Applications() {
  const { data, loading, reload } = useApi<Application[]>(() => api.get("/api/applications"));

  const setStatus = async (id: string, status: string) => {
    await api.put(`/api/applications/${id}`, { status });
    reload();
  };

  return (
    <>
      <h1 className="page-title">Applications</h1>
      <p className="page-sub">Track every application from draft to outcome, with lessons learned feeding future applications (§8).</p>
      {loading && <p className="muted">Loading…</p>}
      {!loading && !data?.length && <Empty>No applications yet — analyze a job first, then open its application workspace.</Empty>}
      {!!data?.length && (
        <div className="panel">
          <table>
            <thead>
              <tr><th>Position</th><th>Organization</th><th>Deadline</th><th>Fit</th><th>ATS</th><th>Status</th><th>Outcome / notes</th><th></th></tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/applications/${a.id}`}>{a.job?.position_title || "Untitled"}</Link></td>
                  <td>{a.job?.organization_name}</td>
                  <td className="muted">{a.job?.deadline || "—"}</td>
                  <td style={{ fontWeight: 700 }}>{a.fit_score != null ? `${Math.round(a.fit_score * 100)}%` : "—"}</td>
                  <td>{a.ats_score_snapshot != null ? `${Math.round(a.ats_score_snapshot * 100)}%` : "—"}</td>
                  <td>
                    <select value={a.status} onChange={(e) => setStatus(a.id, e.target.value)} style={{ width: "auto", padding: "4px 8px" }}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="small muted">{a.outcome || a.user_notes || "—"}</td>
                  <td><Link to={`/applications/${a.id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
