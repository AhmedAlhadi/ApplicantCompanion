import { useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  CareerAchievement,
  CareerExperience,
  CareerProject,
  CareerSkill,
  JobAnalysisResponse,
  Requirement,
} from "../api/types";
import { Empty, useApi } from "./ui";
import { t } from "../lib/i18n";

type Column = "requirement" | "competency" | "evidence" | "technology";
type Strength = "strong" | "partial" | "related";

type EvNode = {
  id: string;
  column: Column;
  label: string;
  sub: string;
  pct?: number;
  status?: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

type EvEdge = { source: string; target: string; strength: Strength };

const COL_X: Record<Column, number> = {
  requirement: 118,
  competency: 368,
  evidence: 638,
  technology: 900,
};

const COL_COLOR: Record<Column, string> = {
  requirement: "#a78bfa",
  competency: "#5b8cff",
  evidence: "#37c2a0",
  technology: "#7dd3fc",
};

function colLabel(column: Column) {
  return t(`evidence.${column}`);
}

function competencyFor(req: Requirement, competencies: string[]) {
  const hay = norm(`${req.text} ${(req.keywords || []).join(" ")}`);
  const hit = competencies.find((c) => {
    const key = norm(c);
    return key && (hay.includes(key) || key.split(" ").some((w) => w.length > 3 && hay.includes(w)));
  });
  const category = t(`category.${req.category}`);
  return hit || (category !== `category.${req.category}` ? category : req.category) || t("evidence.general");
}

function norm(s: string) {
  return s.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, " ").trim();
}

function shorten(value: string, n: number) {
  const text = value.trim();
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function importanceRank(importance: string) {
  return { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }[importance] ?? 4;
}

function matchStrength(status?: string): Strength {
  if (status === "MATCHED") return "strong";
  if (status === "PARTIALLY_MATCHED" || status === "TRANSFERABLE") return "partial";
  return "related";
}

function spread(count: number, start: number, end: number) {
  if (count <= 0) return [];
  if (count === 1) return [(start + end) / 2];
  return Array.from({ length: count }, (_, i) => start + (i * (end - start)) / (count - 1));
}

function entityLabel(
  type: string,
  id: string,
  lookup: {
    experiences: Record<string, CareerExperience>;
    projects: Record<string, CareerProject>;
    achievements: Record<string, CareerAchievement>;
    skills: Record<string, CareerSkill>;
  },
) {
  if (type === "experience" && lookup.experiences[id]) {
    const row = lookup.experiences[id];
    return { label: row.job_title || row.organization, sub: row.organization, techs: row.technologies || [] };
  }
  if ((type === "project" || type === "projects") && lookup.projects[id]) {
    const row = lookup.projects[id];
    return { label: row.name, sub: row.role || "Project", techs: row.technologies || [] };
  }
  if (type === "achievement" && lookup.achievements[id]) {
    const row = lookup.achievements[id];
    return { label: row.title || "Achievement", sub: row.quantified_result || "", techs: [] };
  }
  if (type === "skill" && lookup.skills[id]) {
    const row = lookup.skills[id];
    return { label: row.canonical_name || row.name, sub: row.category || "Skill", techs: [] };
  }
  return { label: type, sub: "", techs: [] as string[] };
}

function buildEvidenceGraph(
  requirements: Requirement[],
  competencies: string[],
  lookup: {
    experiences: Record<string, CareerExperience>;
    projects: Record<string, CareerProject>;
    achievements: Record<string, CareerAchievement>;
    skills: Record<string, CareerSkill>;
  },
) {
  const nodes: EvNode[] = [];
  const edges: EvEdge[] = [];
  const seen = new Set<string>();
  const size: Record<Column, { w: number; h: number }> = {
    requirement: { w: 188, h: 56 },
    competency: { w: 176, h: 50 },
    evidence: { w: 188, h: 52 },
    technology: { w: 120, h: 34 },
  };

  const add = (node: Omit<EvNode, "x" | "y" | "w" | "h">) => {
    if (seen.has(node.id)) return;
    seen.add(node.id);
    nodes.push({ ...node, x: COL_X[node.column], y: 0, ...size[node.column] });
  };
  const link = (source: string, target: string, strength: Strength) => {
    if (!seen.has(source) || !seen.has(target)) return;
    edges.push({ source, target, strength });
  };

  const selectedReqs = [...requirements]
    .sort((a, b) => importanceRank(a.importance) - importanceRank(b.importance))
    .slice(0, 6);

  for (const req of selectedReqs) {
    const reqId = `req:${req.id}`;
    add({
      id: reqId,
      column: "requirement",
      label: req.text,
      sub: req.importance,
      pct: req.match ? Math.round((req.match.confidence || 0) * 100) : undefined,
      status: req.match?.status,
    });
    const competency = competencyFor(req, competencies);
    const compId = `comp:${norm(competency)}`;
    add({ id: compId, column: "competency", label: competency, sub: "Mapped competency" });
    link(reqId, compId, matchStrength(req.match?.status));

    const evidenceItems = (req.match?.evidence || []).slice(0, 3);
    if (!evidenceItems.length) {
      const gapId = `gap:${req.id}`;
      add({ id: gapId, column: "evidence", label: "No linked evidence yet", sub: "Gap", status: "NOT_MATCHED" });
      link(compId, gapId, "related");
      continue;
    }
    for (const item of evidenceItems) {
      const evId = `ev:${item.entity_type}:${item.entity_id}`;
      const resolved = entityLabel(item.entity_type, item.entity_id, lookup);
      add({
        id: evId,
        column: "evidence",
        label: resolved.label,
        sub: resolved.sub || item.source || item.entity_type,
        status: req.match?.status,
      });
      link(compId, evId, matchStrength(req.match?.status));
      for (const tech of resolved.techs.slice(0, 3)) {
        const techId = `tech:${norm(tech)}`;
        add({ id: techId, column: "technology", label: tech, sub: "" });
        link(evId, techId, "related");
      }
    }
  }

  const byCol = (column: Column) => nodes.filter((n) => n.column === column);
  (Object.keys(COL_X) as Column[]).forEach((column) => {
    const colNodes = byCol(column);
    spread(colNodes.length, 70, 470).forEach((y, i) => {
      colNodes[i].y = y;
    });
  });

  return { nodes, edges };
}

export function EvidenceGraph({ analysis }: { analysis: JobAnalysisResponse }) {
  const career = useApi(async () => {
    const [experiences, projects, achievements, skills] = await Promise.all([
      api.get<CareerExperience[]>("/api/career/experiences"),
      api.get<CareerProject[]>("/api/career/projects"),
      api.get<CareerAchievement[]>("/api/career/achievements"),
      api.get<CareerSkill[]>("/api/career/skills"),
    ]);
    return { experiences, projects, achievements, skills };
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const graph = useMemo(() => {
    if (!career.data) return { nodes: [] as EvNode[], edges: [] as EvEdge[] };
    const lookup = {
      experiences: Object.fromEntries(career.data.experiences.map((e) => [e.id, e])),
      projects: Object.fromEntries(career.data.projects.map((p) => [p.id, p])),
      achievements: Object.fromEntries(career.data.achievements.map((a) => [a.id, a])),
      skills: Object.fromEntries(career.data.skills.map((s) => [s.id, s])),
    };
    return buildEvidenceGraph(
      analysis.requirements || [],
      analysis.parsed?.competencies || [],
      lookup,
    );
  }, [analysis, career.data]);

  const nodeById = useMemo(() => Object.fromEntries(graph.nodes.map((n) => [n.id, n])), [graph.nodes]);
  const selected = selectedId ? nodeById[selectedId] : null;
  const activeIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const next = new Set<string>([selectedId]);
    for (const e of graph.edges) {
      if (e.source === selectedId) next.add(e.target);
      if (e.target === selectedId) next.add(e.source);
    }
    return next;
  }, [selectedId, graph.edges]);

  const job = analysis.job;
  if (!analysis.requirements?.length) {
    return <Empty>{t("evidence.empty")}</Empty>;
  }
  if (career.loading) return <p className="muted">{t("evidence.building")}</p>;

  return (
    <div className="eg-panel">
      <div className="row spread mb">
        <div>
          <h3 className="ck-graph-title">{t("evidence.title")}</h3>
          <p className="small muted" style={{ margin: 0 }}>
            {job.position_title || t("common.untitledRole")} · {job.organization_name || t("common.unknownOrg")}
          </p>
        </div>
        <div className="eg-legend">
          <span><span className="ck-edge-swatch strong" /> {t("evidence.strong")}</span>
          <span><span className="ck-edge-swatch partial" /> {t("evidence.partial")}</span>
          <span><span className="ck-edge-swatch related" /> {t("evidence.related")}</span>
        </div>
      </div>

      <div className="eg-map">
        <svg className="eg-svg" viewBox="0 0 1040 540" role="img" aria-label="Career to job evidence graph">
          {(Object.keys(COL_X) as Column[]).map((column) => (
            <text key={column} className="ck-cluster-label" x={COL_X[column]} y={24} textAnchor="middle">
              {colLabel(column)}
            </text>
          ))}
          {graph.edges.map((e, i) => {
            const a = nodeById[e.source];
            const b = nodeById[e.target];
            if (!a || !b) return null;
            const active = !selectedId || (activeIds.has(e.source) && activeIds.has(e.target) && (e.source === selectedId || e.target === selectedId));
            return (
              <line
                key={`${e.source}-${e.target}-${i}`}
                x1={a.x + a.w / 2 - 8}
                y1={a.y}
                x2={b.x - b.w / 2 + 8}
                y2={b.y}
                className={`ck-edge ${e.strength} ${active && selectedId ? "active" : ""}`}
                opacity={selectedId && !active ? 0.12 : 0.9}
              />
            );
          })}
          {graph.nodes.map((n) => {
            const color = COL_COLOR[n.column];
            const dimmed = selectedId ? !activeIds.has(n.id) : false;
            const hovered = selectedId === n.id;
            return (
              <g
                key={n.id}
                className="ck-node"
                transform={`translate(${n.x} ${n.y})`}
                opacity={dimmed ? 0.3 : 1}
                onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}
              >
                <title>{n.label}{n.sub ? ` — ${n.sub}` : ""}</title>
                <rect
                  x={-n.w / 2}
                  y={-n.h / 2}
                  width={n.w}
                  height={n.h}
                  rx={10}
                  fill={`${color}22`}
                  stroke={hovered ? "#e8ecf6" : color}
                  strokeWidth={hovered ? 2 : 1.4}
                />
                <text className="ck-node-label" y={n.pct != null || n.sub ? -5 : 4} textAnchor="middle">
                  {shorten(n.label, 24)}
                </text>
                <text className="ck-node-sub" y={13} textAnchor="middle">
                  {n.pct != null ? `${n.pct}% match` : shorten(n.sub, 22)}
                </text>
              </g>
            );
          })}
        </svg>
        {selected && (
          <div className="ck-map-detail">
            <span className="badge" style={{ color: COL_COLOR[selected.column], background: "transparent", border: `1px solid ${COL_COLOR[selected.column]}` }}>
              {colLabel(selected.column)}
            </span>
            <div className="title mt">{selected.label}</div>
            {selected.sub && <div className="meta">{selected.sub}</div>}
            {selected.status && <div className="mt"><span className={`badge ${selected.status}`}>{selected.status.replace("_", " ")}</span></div>}
            {selected.pct != null && <div className="meta">{selected.pct}% confidence</div>}
          </div>
        )}
      </div>
      <p className="eg-tip">Click a requirement to highlight the competency, evidence, and tools that support it.</p>
    </div>
  );
}
