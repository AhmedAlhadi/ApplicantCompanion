import { Files } from "lucide-react";
import { api } from "../api/client";
import type { AppDocument, Application } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";
import { useT } from "../lib/i18n";

export default function Documents() {
  const { t } = useT();
  const apps = useApi<Application[]>(() => api.get("/api/applications"));
  const docsPerApp = useApi<AppDocument[][]>(async () => {
    const list = apps.data ?? [];
    return Promise.all(list.map((a) => api.get<AppDocument[]>(`/api/applications/${a.id}/documents`)));
  }, [apps.data]);

  const docs = (docsPerApp.data ?? []).flat();

  return (
    <>
      <h1 className="page-title">{t("documents.title")}</h1>
      <p className="page-sub">{t("documents.sub")}</p>
      {(apps.loading || docsPerApp.loading) && <p className="muted">{t("common.loading")}</p>}
      {!docs.length && !docsPerApp.loading && <Empty icon={Files}>{t("documents.empty")}</Empty>}
      {docs.map((d) => (
        <div className="list-item" key={d.id}>
          <div className="row spread">
            <div>
              <div className="title"><Link to={`/documents/${d.id}`}>{d.title}</Link></div>
              <div className="meta">
                {d.document_type === "cv" ? t("documents.cv") : t("documents.coverLetter")} · {d.job?.organization_name} · {t("documents.template", { key: d.template_key })} · {t("documents.versions", { n: d.versions?.length ?? 0 })}
              </div>
            </div>
            <div className="row">
              {d.current_version && <span className="badge verified">v{d.current_version.version_number}</span>}
              <Link to={`/documents/${d.id}`}>{t("documents.editExport")}</Link>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
