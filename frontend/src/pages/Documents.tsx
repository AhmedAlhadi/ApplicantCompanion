import { api } from "../api/client";
import type { AppDocument, Application } from "../api/types";
import { Empty, Link, useApi } from "../components/ui";

export default function Documents() {
  const apps = useApi<Application[]>(() => api.get("/api/applications"));
  const docsPerApp = useApi<AppDocument[][]>(async () => {
    const list = apps.data ?? [];
    return Promise.all(list.map((a) => api.get<AppDocument[]>(`/api/applications/${a.id}/documents`)));
  }, [apps.data]);

  const docs = (docsPerApp.data ?? []).flat();

  return (
    <>
      <h1 className="page-title">Documents</h1>
      <p className="page-sub">Every generated CV and cover letter, versioned and exportable (§29, §50).</p>
      {(apps.loading || docsPerApp.loading) && <p className="muted">Loading…</p>}
      {!docs.length && !docsPerApp.loading && <Empty>No documents yet — generate one from an application.</Empty>}
      {docs.map((d) => (
        <div className="list-item" key={d.id}>
          <div className="row spread">
            <div>
              <div className="title"><Link to={`/documents/${d.id}`}>{d.title}</Link></div>
              <div className="meta">
                {d.document_type === "cv" ? "CV" : "Cover Letter"} · {d.job?.organization_name} · template {d.template_key} · {d.versions?.length ?? 0} version(s)
              </div>
            </div>
            <div className="row">
              {d.current_version && <span className="badge verified">v{d.current_version.version_number}</span>}
              <Link to={`/documents/${d.id}`}>Edit / Export</Link>
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
