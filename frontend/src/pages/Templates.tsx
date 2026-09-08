import { LayoutTemplate } from "lucide-react";
import { api } from "../api/client";
import type { Template } from "../api/types";
import { Empty, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export default function Templates({ documentType }: { documentType: "cv" | "cover_letter" }) {
  const { t } = useT();
  const { data, loading } = useApi<Template[]>(() => api.get(`/api/templates?document_type=${documentType}`), [documentType]);
  return (
    <>
      <h1 className="page-title">{documentType === "cv" ? t("templates.cvTitle") : t("templates.clTitle")}</h1>
      <p className="page-sub">{t("templates.sub")}</p>
      {loading && <p className="muted">{t("common.loading")}</p>}
      {!loading && !data?.length && <Empty icon={LayoutTemplate}>{t("templates.empty")}</Empty>}
      <div className="grid cols-3">
        {data?.map((tpl) => {
          const colors = (tpl.config as any)?.colors ?? {};
          return (
            <div className="panel" key={tpl.id}>
              <div className="row spread">
                <h3 style={{ margin: 0 }}>{tpl.name}</h3>
                {tpl.is_builtin && <span className="badge needs_review">{t("templates.builtin")}</span>}
              </div>
              <p className="small muted">{tpl.description}</p>
              <div className="row" style={{ gap: 6 }}>
                {Object.entries(colors).map(([k, v]) => (
                  <span key={k} title={k} style={{ width: 18, height: 18, borderRadius: 4, background: String(v), border: "1px solid var(--border)" }} />
                ))}
              </div>
              <p className="small mono mt">key: {tpl.key}</p>
            </div>
          );
        })}
      </div>
    </>
  );
}
