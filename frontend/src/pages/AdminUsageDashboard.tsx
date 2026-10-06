import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AdminUsageStats } from "../api/types";
import { ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export default function AdminUsageDashboard() {
  const { t } = useT();
  const stats = useApi<AdminUsageStats>(() => api.get("/api/admin/usage/stats"));
  if (stats.loading) return <p className="muted">{t("common.loading")}</p>;
  if (stats.error || !stats.data) return <ErrorBox error={stats.error} />;
  const data = stats.data;
  return (
    <>
      <h1 className="page-title">{t("adminPlans.usageTitle")}</h1>
      <p className="page-sub">{data.period_key}</p>
      <div className="grid cols-3">
        <div className="stat-card"><div className="stat-value">{data.active_reservations}</div><div className="stat-label">{t("usage.reserved")}</div></div>
        <div className="stat-card"><div className="stat-value">{data.stale_reservations}</div><div className="stat-label">{t("adminPlans.stale")}</div></div>
        <div className="stat-card"><div className="stat-value">{data.users_near_limit.length}</div><div className="stat-label">{t("adminPlans.nearLimit")}</div></div>
      </div>
      <div className="panel">
        <h3>{t("usage.plan")}</h3>
        {Object.entries(data.users_by_plan).map(([code, count]) => (
          <div className="row spread small" key={code}><span>{code}</span><span>{count}</span></div>
        ))}
      </div>
      <div className="panel">
        <h3>{t("adminPlans.meter")}</h3>
        {Object.entries(data.usage_by_meter).map(([meter, entry]) => (
          <div className="row spread small" key={meter}>
            <span>{t(`usage.meters.${meter}`)}</span>
            <span>{entry.consumed} + {entry.reserved}</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>{t("adminPlans.nearLimit")}</h3>
        {data.users_near_limit.map((row) => (
          <div className="row spread small" key={`${row.user_id}-${row.meter}`}>
            <Link to={`/admin/users/${row.user_id}/entitlements`}>{row.email}</Link>
            <span>{t(`usage.meters.${row.meter}`)} · {row.pct}%</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>{t("adminPlans.topConsumers")}</h3>
        {data.top_consumers.map((row) => (
          <div className="row spread small" key={row.user_id}>
            <Link to={`/admin/users/${row.user_id}/entitlements`}>{row.email}</Link>
            <span>{row.consumed}</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>{t("adminPlans.tokens")}</h3>
        {Object.entries(data.tokens_by_model).map(([model, total]) => (
          <div className="row spread small" key={model}><span className="mono">{model}</span><span>{total}</span></div>
        ))}
      </div>
    </>
  );
}
