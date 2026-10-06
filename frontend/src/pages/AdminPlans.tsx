import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { PlanRecord } from "../api/types";
import { ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export default function AdminPlans() {
  const { t } = useT();
  const plans = useApi<PlanRecord[]>(() => api.get("/api/admin/plans"));
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/admin/plans", { code, display_name: name });
      setCode("");
      setName("");
      plans.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("common.saveFailed"));
    }
  };

  return (
    <>
      <h1 className="page-title">{t("adminPlans.title")}</h1>
      <p className="page-sub">{t("adminPlans.sub")}</p>
      <form className="panel" onSubmit={create}>
        <div className="grid cols-2">
          <div>
            <label>{t("adminPlans.code")}</label>
            <input value={code} onChange={(e) => setCode(e.target.value)} required />
          </div>
          <div>
            <label>{t("adminPlans.name")}</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
        </div>
        <ErrorBox error={error} />
        <button className="primary mt">{t("adminPlans.newPlan")}</button>
      </form>
      {plans.loading && <p className="muted">{t("common.loading")}</p>}
      {plans.data?.map((plan) => (
        <div className="list-item" key={plan.id}>
          <div className="row spread">
            <div>
              <Link to={`/admin/plans/${plan.id}`}><strong>{plan.display_name}</strong></Link>
              <div className="small muted">{plan.code} · {t("adminPlans.subscribers")} {plan.subscriber_count}</div>
            </div>
            <span className="badge verified">{plan.status}</span>
          </div>
        </div>
      ))}
    </>
  );
}
