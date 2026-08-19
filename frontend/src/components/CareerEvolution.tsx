import type { CareerExperience, CareerNarrative } from "../api/types";

const PHASE_COLORS = ["#3b6fd4", "#2f9e8a", "#7c6af0", "#c9842a", "#4a8fd8", "#43c97e"];

function parseMonth(value?: string | null): number | null {
  if (!value) return null;
  const match = value.match(/^(\d{4})(?:-(\d{2}))?/);
  if (!match) return null;
  return Number(match[1]) * 12 + Number(match[2] || "1") - 1;
}

function yearLabel(value?: string | null, fallback = "") {
  if (!value) return fallback;
  return value.slice(0, 4);
}

function phaseLabel(exp: CareerExperience, narratives: CareerNarrative[]) {
  const domain = (exp.domains || []).map((d) => d.trim()).find(Boolean);
  const range = [yearLabel(exp.start_date), yearLabel(exp.end_date, "Present")].filter(Boolean).join("–");
  const narrative = narratives.find((n) => {
    const period = (n.period || "").toLowerCase();
    return period && (period.includes(yearLabel(exp.start_date)) || period.includes((exp.job_title || "").toLowerCase()));
  });
  const focus = narrative?.title || domain || exp.job_title || exp.organization;
  return { range, focus, copy: narrative?.text || narrative?.narrative || "" };
}

export function buildCareerPhases(experiences: CareerExperience[], narratives: CareerNarrative[] = []) {
  const sorted = [...experiences].sort((a, b) => (a.start_date || "9999").localeCompare(b.start_date || "9999"));
  return sorted.map((exp, index) => {
    const start = parseMonth(exp.start_date);
    const end = parseMonth(exp.end_date) ?? (start != null ? start + 12 : null);
    const { range, focus, copy } = phaseLabel(exp, narratives);
    return {
      id: exp.id,
      range,
      focus,
      copy,
      organization: exp.organization,
      weight: Math.max(1, (end ?? 0) - (start ?? 0) || 12),
      color: PHASE_COLORS[index % PHASE_COLORS.length],
    };
  });
}

export function CareerEvolution({
  experiences,
  narratives = [],
}: {
  experiences: CareerExperience[];
  narratives?: CareerNarrative[];
}) {
  const phases = buildCareerPhases(experiences, narratives);
  if (!phases.length) return null;

  const total = phases.reduce((sum, phase) => sum + phase.weight, 0);
  let cursor = 0;
  const width = 1000;
  const height = 168;

  return (
    <div className="evo-panel">
      <div className="row spread mb">
        <div>
          <h3 className="evo-title">Career Evolution</h3>
          <p className="small muted" style={{ margin: 0 }}>Derived from role dates and focus areas.</p>
        </div>
        <span className="small muted">View by: Focus Area</span>
      </div>
      <svg className="evo-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Career evolution timeline">
        {phases.map((phase, index) => {
          const x0 = (cursor / total) * width;
          cursor += phase.weight;
          const x1 = (cursor / total) * width;
          const mid = (x0 + x1) / 2;
          const rise = 28 + (index % 3) * 14;
          const yTop = 36 - rise * 0.15;
          const path = [
            `M ${x0} ${height - 18}`,
            `C ${x0 + 18} ${yTop + 8}, ${mid - 24} ${yTop}, ${mid} ${yTop}`,
            `C ${mid + 24} ${yTop}, ${x1 - 18} ${yTop + 8}, ${x1} ${height - 18}`,
            "Z",
          ].join(" ");
          return (
            <g key={phase.id}>
              <path d={path} fill={phase.color} opacity={0.82} />
              <text x={mid} y={yTop + 22} textAnchor="middle" className="evo-label">
                {phase.range}
              </text>
              <text x={mid} y={yTop + 40} textAnchor="middle" className="evo-focus">
                {phase.focus.length > 28 ? `${phase.focus.slice(0, 26)}…` : phase.focus}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="evo-legend">
        {phases.map((phase) => (
          <div key={phase.id} className="evo-legend-item">
            <span className="evo-dot" style={{ background: phase.color }} />
            <span>
              <strong>{phase.organization}</strong>
              {phase.copy ? <span className="muted"> — {phase.copy}</span> : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
