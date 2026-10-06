import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { PlanRecord } from "../api/types";
import { ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

const METERS = ["fit_check", "application_pack", "section_regeneration", "career_documents", "storage_bytes", "concurrent_workflows", "active_applications"];
const FEATURES = ["organization_research", "hiring_context_research", "docx_export", "custom_scoring", "advanced_analytics", "api_access", "bulk_fit_check", "priority_processing"];
const TEMPLATES = ["traditional-executive", "modern-professional", "international-un", "consulting", "technology-ai", "minimal-ats", "academic-research"];

export default function AdminPlanEditor() {
  const { planId } = useParams();
  const { t } = useT();
  const plan = useApi<PlanRecord>(() => api.get(`/api/admin/plans/${planId}`), [planId]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = plan.data?.versions.find((version) => version.id === plan.data?.current_version_id) || plan.data?.versions[0];
  const [limits, setLimits] = useState<Record<string, number>>({});
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [templates, setTemplates] = useState<string[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!current || ready) return;
    setLimits(current.limits);
    setFeatures(current.features);
    setTemplates(current.template_keys);
    setReady(true);
  }, [current, ready]);

  const publishNew = async (e: FormEvent) => {
    e.preventDefault();
    if (!plan.data) return;
    setBusy(true);
    setError(null);
    try {
      const version = await api.post<{ id: string }>(`/api/admin/plans/${plan.data.id}/versions`, {
        limits,
        features,
        template_keys: templates,
        priority: current?.priority || 0,
        rollover_caps: current?.rollover_caps || {},
        notes: "Edited from admin",
      });
      await api.post(`/api/admin/plans/${plan.data.id}/versions/${version.id}/publish`);
      setReady(false);
      plan.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    if (!plan.data) return;
    await api.post(`/api/admin/plans/${plan.data.id}/archive`);
    plan.reload();
  };

  if (plan.loading || !plan.data || !current) return <p className="muted">{t("common.loading")}</p>;
  const published = Boolean(current.published_at);
  return (
    <>
      <h1 className="page-title">{plan.data.display_name}</h1>
      <p className="page-sub">{plan.data.code} · v{current.version_number} · {plan.data.status}</p>
      <form className="panel" onSubmit={publishNew}>
        <h3>{t("adminPlans.limits")}</h3>
        <div className="grid cols-2">
          {METERS.map((meter) => (
            <div key={meter}>
              <label>{t(`usage.meters.${meter}`)}</label>
              <input
                type="number"
                value={limits[meter] ?? 0}
                onChange={(e) => setLimits({ ...limits, [meter]: Number(e.target.value) })}
              />
            </div>
          ))}
        </div>
        <h3>{t("adminPlans.features")}</h3>
        {FEATURES.map((feature) => (
          <label className="row" key={feature} style={{ fontWeight: 500 }}>
            <input
              type="checkbox"
              checked={Boolean(features[feature])}
              onChange={(e) => setFeatures({ ...features, [feature]: e.target.checked })}
              style={{ width: "auto" }}
            />
            {feature}
          </label>
        ))}
        <h3>{t("adminPlans.templates")}</h3>
        {TEMPLATES.map((key) => (
          <label className="row" key={key} style={{ fontWeight: 500 }}>
            <input
              type="checkbox"
              checked={templates.includes(key)}
              onChange={(e) => setTemplates(e.target.checked ? [...templates, key] : templates.filter((item) => item !== key))}
              style={{ width: "auto" }}
            />
            {key}
          </label>
        ))}
        <ErrorBox error={error} />
        <div className="row mt">
          <button className="primary" disabled={busy}>{t("adminPlans.createVersion")}</button>
          <button type="button" onClick={archive}>{t("adminPlans.archive")}</button>
        </div>
        {published && <p className="small muted">{t("adminPlans.sub")}</p>}
      </form>
      <div className="panel">
        <h3>{t("adminPlans.createVersion")}</h3>
        {plan.data.versions.map((version) => (
          <div className="row spread small" key={version.id}>
            <span>v{version.version_number}</span>
            <span className="muted">{version.published_at ? t("adminPlans.publish") : plan.data?.status}</span>
          </div>
        ))}
      </div>
    </>
  );
}
