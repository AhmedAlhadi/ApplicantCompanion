import { LayoutTemplate } from "lucide-react";
import { api } from "../api/client";
import type { Template } from "../api/types";
import { Empty, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export function ThemePicker({
  documentType,
  selected,
  onSelect,
}: {
  documentType: "cv" | "cover_letter";
  selected?: string;
  onSelect?: (key: string) => void;
}) {
  const { t } = useT();
  const { data, loading } = useApi<Template[]>(() => api.get(`/api/templates?document_type=${documentType}`), [documentType]);
  if (loading) return <p className="muted">{t("common.loading")}</p>;
  if (!data?.length) return <Empty icon={LayoutTemplate}>{t("templates.empty")}</Empty>;
  return (
    <div className="grid cols-3">
      {data.map((tpl) => {
        const colors = (tpl.config as { colors?: Record<string, string> })?.colors ?? {};
        const isSelected = selected === tpl.key;
        return (
          <button
            type="button"
            className={`panel theme-card${isSelected ? " selected" : ""}`}
            key={tpl.id}
            onClick={() => onSelect?.(tpl.key)}
            aria-pressed={isSelected}
          >
            <div className="row spread">
              <h3 style={{ margin: 0 }}>{tpl.name}</h3>
              <div className="row" style={{ gap: 6 }}>
                {isSelected && <span className="badge verified">{t("settings.selected")}</span>}
                {tpl.is_builtin && <span className="badge needs_review">{t("templates.builtin")}</span>}
              </div>
            </div>
            <p className="small muted">{tpl.description}</p>
            <div className="row" style={{ gap: 6 }}>
              {Object.entries(colors).map(([k, v]) => (
                <span key={k} title={k} style={{ width: 18, height: 18, borderRadius: 4, background: String(v), border: "1px solid var(--border)" }} />
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default function Templates({ documentType }: { documentType: "cv" | "cover_letter" }) {
  const { t } = useT();
  return (
    <>
      <h1 className="page-title">{documentType === "cv" ? t("templates.cvTitle") : t("templates.clTitle")}</h1>
      <p className="page-sub">{t("templates.sub")}</p>
      <ThemePicker documentType={documentType} />
    </>
  );
}
