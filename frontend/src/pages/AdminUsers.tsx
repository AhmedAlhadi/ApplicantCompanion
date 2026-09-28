import { FormEvent, useState } from "react";
import { RefreshCw, UserPlus, Users } from "lucide-react";
import { api } from "../api/client";
import type { AdminUser, User } from "../api/types";
import { Empty, ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

function authLabel(user: AdminUser, t: (key: string) => string) {
  if (user.has_password && user.google_linked) return t("admin.bothAuth");
  if (user.google_linked) return t("admin.googleAuth");
  return t("admin.passwordAuth");
}

function onboardingLabel(status: AdminUser["onboarding_status"], t: (key: string) => string) {
  if (status === "completed") return t("admin.onboardingCompleted");
  if (status === "skipped") return t("admin.onboardingSkipped");
  if (status === "in_progress") return t("admin.onboardingInProgress");
  if (status === "reset") return t("admin.onboardingReset");
  return t("admin.onboardingNotStarted");
}

export default function AdminUsers({ currentUser }: { currentUser: User }) {
  const { t } = useT();
  const users = useApi<AdminUser[]>(() => api.get("/api/admin/users"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resettingId, setResettingId] = useState<string | null>(null);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/admin/users", {
        email,
        password,
        full_name: fullName,
        is_admin: makeAdmin,
      });
      setEmail("");
      setPassword("");
      setFullName("");
      setMakeAdmin(false);
      users.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("admin.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  const patch = async (id: string, body: Record<string, unknown>) => {
    setError(null);
    try {
      await api.patch(`/api/admin/users/${id}`, body);
      users.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("admin.updateFailed"));
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm(t("admin.confirmDelete"))) return;
    setError(null);
    try {
      await api.delete(`/api/admin/users/${id}`);
      users.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("admin.updateFailed"));
    }
  };

  const resetOnboarding = async (id: string, self: boolean) => {
    if (!window.confirm(t("admin.confirmResetOnboarding"))) return;
    setError(null);
    setResettingId(id);
    try {
      await api.post(`/api/admin/users/${id}/reset-onboarding`);
      if (self) {
        window.location.assign("/onboarding");
        return;
      }
      users.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("admin.resetFailed"));
    } finally {
      setResettingId(null);
    }
  };

  return (
    <>
      <h1 className="page-title">{t("admin.usersTitle")}</h1>
      <p className="page-sub">{t("admin.usersSub")}</p>

      <form className="panel" onSubmit={create} style={{ maxWidth: 640 }}>
        <h3>{t("admin.createUser")}</h3>
        <label>{t("admin.fullName")}</label>
        <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <label>{t("admin.email")}</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>{t("admin.password")}</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        <label className="row mt" style={{ fontWeight: 500 }}>
          <input type="checkbox" checked={makeAdmin} onChange={(e) => setMakeAdmin(e.target.checked)} style={{ width: "auto" }} />
          {t("admin.makeAdmin")}
        </label>
        <ErrorBox error={error} />
        <button className="primary mt" disabled={busy}>
          <UserPlus aria-hidden /> {t("admin.createUser")}
        </button>
      </form>

      <div className="panel">
        {users.loading && <p className="muted">{t("common.loading")}</p>}
        {!users.loading && !users.data?.length && <Empty icon={Users}>{t("admin.empty")}</Empty>}
        {!!users.data?.length && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("admin.email")}</th>
                  <th>{t("admin.role")}</th>
                  <th>{t("admin.status")}</th>
                  <th>{t("admin.onboarding")}</th>
                  <th>{t("admin.signedInWith")}</th>
                  <th>{t("admin.jobs")}</th>
                  <th>{t("admin.applications")}</th>
                  <th>{t("admin.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {users.data.map((u) => {
                  const self = u.id === currentUser.id;
                  return (
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
                      <td>
                        <div className="small">{onboardingLabel(u.onboarding_status, t)}</div>
                        <button
                          type="button"
                          className="sm"
                          style={{ marginTop: 6 }}
                          onClick={() => resetOnboarding(u.id, self)}
                          disabled={resettingId === u.id}
                        >
                          <RefreshCw aria-hidden /> {t("admin.resetOnboarding")}
                        </button>
                      </td>
                      <td className="small">{authLabel(u, t)}</td>
                      <td>{u.job_count}</td>
                      <td>{u.application_count}</td>
                      <td>
                        {!self && (
                          <div className="row" style={{ gap: 6 }}>
                            <button type="button" className="sm" onClick={() => patch(u.id, { is_admin: !u.is_admin })}>
                              {u.is_admin ? t("admin.demote") : t("admin.promote")}
                            </button>
                            <button type="button" className="sm" onClick={() => patch(u.id, { is_active: !u.is_active })}>
                              {u.is_active ? t("admin.deactivate") : t("admin.activate")}
                            </button>
                            <button type="button" className="sm danger" onClick={() => remove(u.id)}>
                              {t("common.delete")}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
