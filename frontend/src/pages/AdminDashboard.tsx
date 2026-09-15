import { Shield, UserCheck, UserPlus, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AdminStats, AdminUser } from "../api/types";
import { LanguagePickers } from "../components/LanguageSettings";
import { Empty, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export default function AdminDashboard() {
  const { t } = useT();
  const stats = useApi<AdminStats>(() => api.get("/api/admin/stats"));
  const users = useApi<AdminUser[]>(() => api.get("/api/admin/users"));

  if (stats.loading) return <p className="muted">{t("common.loading")}</p>;
  const s = stats.data;

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">{t("admin.title")}</h1>
          <p className="page-sub">{t("admin.sub")}</p>
        </div>
        <Link to="/admin/users" className="btn primary">
          <Users aria-hidden /> {t("admin.manageUsers")}
        </Link>
      </div>

      <div className="grid cols-4">
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.total_users ?? 0}</div>
            <Users className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("admin.totalUsers")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.active_users ?? 0}</div>
            <UserCheck className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("admin.activeUsers")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.admin_users ?? 0}</div>
            <Shield className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("admin.adminUsers")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head">
            <div className="stat-value">{s?.created_this_month ?? 0}</div>
            <UserPlus className="stat-icon" aria-hidden />
          </div>
          <div className="stat-label">{t("admin.createdThisMonth")}</div>
        </div>
      </div>

      <div className="panel mt" style={{ maxWidth: 640 }}>
        <h3>{t("admin.language")}</h3>
        <p className="small muted">{t("admin.languageHint")}</p>
        <div className="mt">
          <LanguagePickers persist />
        </div>
      </div>

      <div className="panel mt">
        <h3>{t("admin.usersTitle")}</h3>
        {users.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>{t("admin.email")}</th>
                <th>{t("admin.role")}</th>
                <th>{t("admin.status")}</th>
                <th>{t("admin.jobs")}</th>
                <th>{t("admin.applications")}</th>
              </tr>
            </thead>
            <tbody>
              {users.data.slice(0, 8).map((u) => (
                <tr key={u.id}>
                  <td>
                    <div>{u.full_name || u.email}</div>
                    {u.full_name ? <div className="small muted">{u.email}</div> : null}
                  </td>
                  <td>{u.is_admin ? t("common.admin") : t("admin.member")}</td>
                  <td>
                    <span className={`badge ${u.is_active ? "verified" : "needs_review"}`}>
                      {u.is_active ? t("admin.active") : t("admin.inactive")}
                    </span>
                  </td>
                  <td>{u.job_count}</td>
                  <td>{u.application_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon={Users}>{t("admin.empty")}</Empty>
        )}
      </div>
    </>
  );
}
