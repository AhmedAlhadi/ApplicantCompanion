import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { ErrorBox, useApi } from "../components/ui";

const WEIGHT_LABELS: Record<string, string> = {
  mandatory_qualifications: "Mandatory qualifications",
  relevant_experience: "Relevant experience",
  technical_skills: "Technical/functional skills",
  responsibilities: "Responsibilities match",
  domain_knowledge: "Domain knowledge",
  leadership_management: "Leadership/management",
  education_certifications: "Education/certifications",
  language_other: "Language/other",
};

export default function Settings() {
  const { data, reload, loading } = useApi<any>(() => api.get("/api/settings"));
  const [threshold, setThreshold] = useState(0.8);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setThreshold(data.score_threshold ?? 0.8);
      setWeights(data.scoring_weights ?? {});
    }
  }, [data]);

  const total = Object.values(weights).reduce((a, b) => a + (Number(b) || 0), 0);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.put("/api/settings", { score_threshold: Number(threshold), scoring_weights: weights });
      setSaved(true);
      reload();
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : "Save failed");
    }
  };

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1 className="page-title">Settings</h1>
      <p className="page-sub">Advisory decision-support configuration — the score never blocks you (§20-21).</p>
      <form className="panel" onSubmit={save} style={{ maxWidth: 640 }}>
        <h3>Job-fit threshold</h3>
        <label>Threshold ({Math.round(threshold * 100)}%)</label>
        <input type="range" min={0.5} max={0.95} step={0.01} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
        <p className="small muted">Scores at or above the threshold show “Strong Fit — Recommended to Apply”. Below it you will be asked whether to continue.</p>

        <h3 className="mt">Scoring weights (§18)</h3>
        {Object.entries(weights).map(([key, value]) => (
          <div className="score-row" key={key}>
            <span className="name">{WEIGHT_LABELS[key] ?? key}</span>
            <input type="range" min={0} max={0.5} step={0.01} value={value} onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })} />
            <span className="pct">{Math.round(value * 100)}%</span>
          </div>
        ))}
        <p className={`small ${Math.abs(total - 1) > 0.01 ? "" : "muted"}`} style={Math.abs(total - 1) > 0.01 ? { color: "var(--danger)" } : {}}>
          Total: {Math.round(total * 100)}% (must equal 100%)
        </p>
        <ErrorBox error={error} />
        <div className="row mt">
          <button className="primary" disabled={Math.abs(total - 1) > 0.01}>Save settings</button>
          {saved && <span className="badge verified">Saved</span>}
        </div>
      </form>
    </>
  );
}
