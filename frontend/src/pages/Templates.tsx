import { api } from "../api/client";
import type { Template } from "../api/types";
import { Empty, useApi } from "../components/ui";

export default function Templates({ documentType }: { documentType: "cv" | "cover_letter" }) {
  const { data, loading } = useApi<Template[]>(() => api.get(`/api/templates?document_type=${documentType}`), [documentType]);
  return (
    <>
      <h1 className="page-title">{documentType === "cv" ? "CV Templates" : "Cover Letter Templates"}</h1>
      <p className="page-sub">Data-driven themes (§28): typography, spacing, sections, colors and rendering rules — each CV theme has a matching cover-letter theme.</p>
      {loading && <p className="muted">Loading…</p>}
      {!loading && !data?.length && <Empty>No templates found.</Empty>}
      <div className="grid cols-3">
        {data?.map((t) => {
          const colors = (t.config as any)?.colors ?? {};
          return (
            <div className="panel" key={t.id}>
              <div className="row spread">
                <h3 style={{ margin: 0 }}>{t.name}</h3>
                {t.is_builtin && <span className="badge needs_review">built-in</span>}
              </div>
              <p className="small muted">{t.description}</p>
              <div className="row" style={{ gap: 6 }}>
                {Object.entries(colors).map(([k, v]) => (
                  <span key={k} title={k} style={{ width: 18, height: 18, borderRadius: 4, background: String(v), border: "1px solid var(--border)" }} />
                ))}
              </div>
              <p className="small mono mt">key: {t.key}</p>
            </div>
          );
        })}
      </div>
    </>
  );
}
