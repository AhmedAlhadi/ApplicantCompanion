import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, downloadFile } from "../api/client";
import type { AppDocument, CVContent, CoverLetterContent, Template } from "../api/types";
import { Empty, ErrorBox, Link, Spinner, useApi } from "../components/ui";

/* Document editor: full human control (§30) — edit any text, reorder/remove
   sections, regenerate single sections, restore versions, switch templates,
   export PDF/DOCX — with per-bullet "View Evidence" traceability (§32). */

export default function DocumentEditor() {
  const { id } = useParams<{ id: string }>();
  const doc = useApi<AppDocument>(() => api.get(`/api/documents/${id}`), [id]);
  const templates = useApi<Template[]>(() => api.get("/api/templates"));
  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);

  const d = doc.data;
  const current = d?.current_version;
  const isCV = d?.document_type === "cv";

  if (doc.loading) return <p className="muted">Loading…</p>;
  if (!d || !current) return <Empty>Document not found or not generated yet.</Empty>;

  const content = current.content as CVContent & CoverLetterContent;

  const saveEdit = async () => {
    setBusy("save");
    setError(null);
    try {
      const parsed = JSON.parse(draft);
      await api.put(`/api/documents/${d.id}`, { content: parsed });
      setEditMode(false);
      doc.reload();
    } catch (err: any) {
      setError(err instanceof SyntaxError ? `Invalid JSON: ${err.message}` : "Save failed");
    } finally {
      setBusy(null);
    }
  };

  const regenerateSection = async (section: string) => {
    setBusy(section);
    try {
      await api.post(`/api/documents/${d.id}/regenerate-section`, { section });
      doc.reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Regeneration failed");
    } finally {
      setBusy(null);
    }
  };

  const restore = async (version: number) => {
    setBusy("restore");
    await api.post(`/api/documents/${d.id}/restore/${version}`);
    doc.reload();
    setBusy(null);
  };

  const changeTemplate = async (key: string) => {
    await api.put(`/api/documents/${d.id}`, { content, template_key: key });
    doc.reload();
  };

  const vr = current.validation_results;
  const ats = current.ats_analysis;
  const docTemplates = (templates.data ?? []).filter((t) => t.document_type === d.document_type);

  return (
    <>
      <div className="row spread">
        <div>
          <h1 className="page-title">{d.title}</h1>
          <p className="page-sub">
            {d.job ? <Link to={`/applications/${d.application_id}`}>{d.job.position_title} — {d.job.organization_name}</Link> : null}
            {" "}· v{current.version_number} {current.user_edited ? "(edited)" : ""} · model <span className="mono">{current.model || "—"}</span> · prompt {current.prompt_version}
          </p>
        </div>
        <div className="row">
          <select value={d.template_key} onChange={(e) => changeTemplate(e.target.value)} style={{ width: "auto" }}>
            {docTemplates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
          <button onClick={() => downloadFile(`/api/documents/${d.id}/export?fmt=pdf`, "document.pdf")}>Export PDF</button>
          <button onClick={() => downloadFile(`/api/documents/${d.id}/export?fmt=docx`, "document.docx")}>Export DOCX</button>
          <button className={editMode ? "primary" : ""} onClick={() => { setDraft(JSON.stringify(content, null, 2)); setEditMode(!editMode); }}>
            {editMode ? "Close editor" : "Edit content"}
          </button>
        </div>
      </div>

      <ErrorBox error={error} />

      <div className="grid cols-3" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <div>
          {editMode ? (
            <div className="panel">
              <h3>Edit structured content (JSON)</h3>
              <textarea rows={28} className="mono" value={draft} onChange={(e) => setDraft(e.target.value)} />
              <div className="row mt">
                <button className="primary" onClick={saveEdit} disabled={busy === "save"}>Save as new version</button>
                <span className="small muted">Edits create a new version — nothing is lost (§29).</span>
              </div>
            </div>
          ) : (
            <div className="cv-preview">
              {isCV ? <CVPreview content={content as CVContent} evidenceFor={evidenceFor} onEvidence={setEvidenceFor} docId={d.id} /> : <LetterPreview content={content as unknown as CoverLetterContent} evidenceFor={evidenceFor} onEvidence={setEvidenceFor} docId={d.id} />}
            </div>
          )}
        </div>

        <div>
          <div className="panel">
            <h3>Regenerate a section (§31)</h3>
            <div className="row">
              {(isCV ? ["summary", "experience", "skills"] : ["paragraphs"]).map((section) => (
                <button key={section} className="sm" onClick={() => regenerateSection(section)} disabled={!!busy}>
                  {busy === section ? <Spinner /> : null} {section}
                </button>
              ))}
            </div>
            <p className="small muted mt">Only the chosen section is regenerated; the rest of the document is preserved.</p>
          </div>

          {vr && (
            <div className="panel">
              <h3>Validation (§41)</h3>
              {([
                ["Schema", vr.schema_valid],
                ["Evidence support", vr.evidence_valid],
                ["Requirement coverage", vr.requirement_coverage_ok],
                ["Hallucination-free", vr.hallucination_free],
                ["Language quality", vr.quality_ok],
              ] as [string, boolean][]).map(([label, ok]) => (
                <div className="row spread small" key={label} style={{ padding: "3px 0" }}>
                  <span>{label}</span>
                  <span className={`badge ${ok ? "verified" : "NOT_MATCHED"}`}>{ok ? "pass" : "fail"}</span>
                </div>
              ))}
              {!!vr.issues?.length && <ul className="small mt">{vr.issues.map((i, n) => <li key={n}>{i}</li>)}</ul>}
            </div>
          )}

          {ats?.ats_score !== undefined && (
            <div className="panel">
              <h3>ATS Analysis (§25)</h3>
              <div className="score-row"><span className="name">ATS Compatibility</span><div className="score-bar"><div style={{ width: `${(ats.ats_score ?? 0) * 100}%` }} /></div><span className="pct">{Math.round((ats.ats_score ?? 0) * 100)}%</span></div>
              <div className="score-row"><span className="name">Keyword Coverage</span><div className="score-bar"><div style={{ width: `${(ats.keyword_coverage ?? 0) * 100}%` }} /></div><span className="pct">{Math.round((ats.keyword_coverage ?? 0) * 100)}%</span></div>
              <div className="score-row"><span className="name">Requirement Coverage</span><div className="score-bar"><div style={{ width: `${(ats.requirement_coverage ?? 0) * 100}%` }} /></div><span className="pct">{Math.round((ats.requirement_coverage ?? 0) * 100)}%</span></div>
              {!!ats.missing_keywords?.length && <p className="small muted mt">Missing keywords: {ats.missing_keywords.slice(0, 8).join(", ")}</p>}
              {!!ats.keyword_overuse_warnings?.length && <p className="small" style={{ color: "var(--warn)" }}>{ats.keyword_overuse_warnings.join("; ")}</p>}
            </div>
          )}

          <div className="panel">
            <h3>Version history (§29)</h3>
            {d.versions.map((v) => (
              <div className="row spread small" key={v.version_number} style={{ padding: "4px 0" }}>
                <span>
                  v{v.version_number} {v.user_edited ? "(edited)" : ""} {v.is_current ? "— current" : ""}
                </span>
                {!v.is_current && <button className="sm ghost" onClick={() => restore(v.version_number)} disabled={!!busy}>Restore</button>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function EvidencePopover({ docId, ids, onClose }: { docId: string; ids: string[]; onClose: () => void }) {
  const data = useApi<any>(() => api.get(`/api/documents/${docId}/evidence`), [docId]);
  const panels = (data.data?.traceability ?? []).filter((p: any) => ids.includes(p.entity_id));
  return (
    <div className="evidence-pop">
      <div className="row spread">
        <strong>Evidence & provenance</strong>
        <button className="sm ghost" onClick={onClose}>close</button>
      </div>
      {panels.length === 0 && <div className="muted small">Resolving evidence…</div>}
      {panels.map((p: any) =>
        p.evidence.map((ev: any) => (
          <div key={ev.id} className="mt small">
            <div><strong>Source:</strong> {ev.source_document ?? "manual entry"} · {ev.source_section}</div>
            <div className="muted">“{ev.original_text}”</div>
            <span className={`badge ${ev.verification_status}`}>{ev.verification_status}</span>
          </div>
        ))
      )}
    </div>
  );
}

function CVPreview({ content, evidenceFor, onEvidence, docId }: { content: CVContent; evidenceFor: string | null; onEvidence: (k: string | null) => void; docId: string }) {
  return (
    <>
      <h2 style={{ border: "none", margin: "0 0 4px" }}>{content.headline}</h2>
      {content.summary && (
        <>
          <h2>Professional Summary</h2>
          <p>{content.summary}</p>
        </>
      )}
      <h2>Professional Experience</h2>
      {content.experience.map((e, i) => (
        <div key={i}>
          <div className="cv-entry-title">{e.job_title}, {e.organization}</div>
          <div className="cv-dates">{[e.start_date, e.end_date].filter(Boolean).join(" – ")}{e.location ? ` · ${e.location}` : ""}</div>
          <ul>
            {e.bullets.map((b, j) => {
              const key = `${i}-${j}`;
              return (
                <li key={j}>
                  {b.text}{" "}
                  {!!b.evidence_ids?.length && (
                    <button className="sm ghost" style={{ padding: "0 6px", fontSize: 11 }} onClick={() => onEvidence(evidenceFor === key ? null : key)}>
                      [View Evidence]
                    </button>
                  )}
                  {evidenceFor === key && <EvidencePopover docId={docId} ids={b.evidence_ids} onClose={() => onEvidence(null)} />}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {!!content.skills?.length && (<><h2>Skills</h2><p>{content.skills.join(", ")}</p></>)}
      {!!content.education?.length && (
        <><h2>Education</h2>
          {content.education.map((ed, i) => (
            <p key={i}><strong>{[ed.degree, ed.field_of_study].filter(Boolean).join(", ")}</strong>{ed.institution ? `, ${ed.institution}` : ""}</p>
          ))}
        </>
      )}
      {!!content.certifications?.length && (<><h2>Certifications</h2><ul>{content.certifications.map((c, i) => <li key={i}>{c}</li>)}</ul></>)}
      {!!content.languages?.length && (<><h2>Languages</h2><p>{content.languages.map((l) => `${l.language} (${l.proficiency})`).join(", ")}</p></>)}
    </>
  );
}

function LetterPreview({ content, evidenceFor, onEvidence, docId }: { content: CoverLetterContent; evidenceFor: string | null; onEvidence: (k: string | null) => void; docId: string }) {
  return (
    <>
      {content.subject && <p><strong>{content.subject}</strong></p>}
      <p>{content.salutation}</p>
      {content.paragraphs.map((p, i) => {
        const key = `p-${i}`;
        return (
          <div key={i}>
            <p>
              {p.text}{" "}
              {!!p.evidence_ids?.filter(Boolean).length && (
                <button className="sm ghost" style={{ padding: "0 6px", fontSize: 11 }} onClick={() => onEvidence(evidenceFor === key ? null : key)}>
                  [View Evidence]
                </button>
              )}
            </p>
            {evidenceFor === key && <EvidencePopover docId={docId} ids={p.evidence_ids} onClose={() => onEvidence(null)} />}
          </div>
        );
      })}
      <p style={{ whiteSpace: "pre-line" }}>{content.closing}</p>
    </>
  );
}
