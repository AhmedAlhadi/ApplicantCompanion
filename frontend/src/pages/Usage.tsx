import { UsageMeterCard } from "../components/Usage";
import { api } from "../api/client";
import type { UsageSummary } from "../api/types";
import { ErrorBox, useApi } from "../components/ui";
import { formatDate, useT } from "../lib/i18n";

export default function Usage() {
  const { t } = useT();
  const usage = useApi<UsageSummary>(() => api.get("/api/account/usage"));
  if (usage.loading) return <p className="muted">{t("common.loading")}</p>;
  if (usage.error || !usage.data) return <ErrorBox error={usage.error} />;
  const data = usage.data;
  return (
    <>
      <h1 className="page-title">{t("usage.title")}</h1>
      <p className="page-sub">{t("usage.sub")}</p>
      {!data.subscription?.usable && <div className="alert warn">{t("usage.noPlan")}</div>}
      {data.subscription && (
        <div className="panel">
          <div className="row spread">
            <div>
              <div className="small muted">{t("usage.plan")}</div>
              <strong>{data.subscription.plan_name || data.subscription.plan_code}</strong>
            </div>
            <span className="badge verified">{data.subscription.status}</span>
          </div>
          {data.period_end && <div className="small muted mt">{t("usage.periodEnds", { date: formatDate(data.period_end) })}</div>}
        </div>
      )}
      <div className="grid cols-2">
        {data.meters.map((meter) => <UsageMeterCard key={meter.meter} meter={meter} />)}
      </div>
      {!!data.credits.length && (
        <div className="panel">
          <h3>{t("usage.credits")}</h3>
          {data.credits.map((credit) => (
            <div className="row spread small" key={credit.id}>
              <span>{t(`usage.meters.${credit.meter}`)} · {credit.remaining}/{credit.original}</span>
              <span className="muted">{credit.expires_at ? t("usage.expires", { date: formatDate(credit.expires_at) }) : credit.source}</span>
            </div>
          ))}
        </div>
      )}
      <div className="panel">
        <h3>{t("usage.features")}</h3>
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          {Object.entries(data.features).map(([key, enabled]) => (
            <span className={`badge ${enabled ? "verified" : "needs_review"}`} key={key}>
              {key} · {enabled ? t("usage.enabled") : t("usage.disabled")}
            </span>
          ))}
        </div>
      </div>
      <p className="small muted">{t("usage.contactAdmin")}</p>
    </>
  );
}
