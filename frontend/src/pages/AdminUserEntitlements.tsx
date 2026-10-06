import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { UsageSummary } from "../api/types";
import { UsageMeterCard } from "../components/Usage";
import { ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

const PLANS = ["explorer", "essential", "professional", "power"];
const METERS = ["fit_check", "application_pack", "section_regeneration"];

export default function AdminUserEntitlements() {
  const { userId } = useParams();
  const { t } = useT();
  const usage = useApi<UsageSummary>(() => api.get(`/api/admin/users/${userId}/usage`), [userId]);
  const events = useApi<Record<string, unknown>[]>(() => api.get(`/api/admin/users/${userId}/usage/events`), [userId]);
  const [planCode, setPlanCode] = useState("explorer");
  const [meter, setMeter] = useState("application_pack");
  const [quantity, setQuantity] = useState(1);
  const [feature, setFeature] = useState("custom_scoring");
  const [error, setError] = useState<string | null>(null);

  const assign = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/api/admin/users/${userId}/subscription`, { plan_code: planCode, status: "active" });
      usage.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    }
  };

  const grant = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/api/admin/users/${userId}/credits`, { meter, quantity, source: "admin_adjustment" });
      usage.reload();
      events.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    }
  };

  const override = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/api/admin/users/${userId}/overrides`, { feature_key: feature, enabled: true, reason: "Admin override" });
      usage.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    }
  };

  if (usage.loading || !usage.data) return <p className="muted">{t("common.loading")}</p>;
  return (
    <>
      <h1 className="page-title">{t("adminPlans.entitlements")}</h1>
      <p className="page-sub">{usage.data.subscription?.plan_name} · {usage.data.subscription?.status}</p>
      <ErrorBox error={error} />
      <form className="panel" onSubmit={assign}>
        <h3>{t("adminPlans.assign")}</h3>
        <select value={planCode} onChange={(e) => setPlanCode(e.target.value)}>
          {PLANS.map((code) => <option key={code} value={code}>{code}</option>)}
        </select>
        <button className="primary mt">{t("common.save")}</button>
      </form>
      <form className="panel" onSubmit={grant}>
        <h3>{t("adminPlans.grantCredits")}</h3>
        <label>{t("adminPlans.meter")}</label>
        <select value={meter} onChange={(e) => setMeter(e.target.value)}>
          {METERS.map((item) => <option key={item} value={item}>{t(`usage.meters.${item}`)}</option>)}
        </select>
        <label>{t("adminPlans.quantity")}</label>
        <input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} />
        <button className="primary mt">{t("adminPlans.grantCredits")}</button>
      </form>
      <form className="panel" onSubmit={override}>
        <h3>{t("adminPlans.override")}</h3>
        <input value={feature} onChange={(e) => setFeature(e.target.value)} />
        <button className="mt">{t("common.save")}</button>
      </form>
      <div className="grid cols-2">
        {usage.data.meters.map((item) => <UsageMeterCard key={item.meter} meter={item} />)}
      </div>
      <div className="panel">
        <h3>{t("adminPlans.events")}</h3>
        {(events.data || []).slice(0, 20).map((event) => (
          <div className="small row spread" key={String(event.id)}>
            <span>{String(event.meter)} · {String(event.state)}</span>
            <span className="muted">{String(event.quantity)}</span>
          </div>
        ))}
      </div>
    </>
  );
}
