import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  CareerAchievement,
  CareerCertification,
  CareerEducation,
  CareerExperience,
  CareerProfile,
  CareerProject,
  CareerSkill,
  ProfessionalKnowledge,
} from "../api/types";
import { CareerEvolution } from "./CareerEvolution";
import { Empty, useApi } from "./ui";
import { t } from "../lib/i18n";

export type CareerTabKey =
  | "profile"
  | "experience"
  | "projects"
  | "achievements"
  | "skills"
  | "education"
  | "certifications"
  | "knowledge";

type NodeType = "profile" | "experience" | "projects" | "skills" | "technology" | "knowledge";

type GraphNode = {
  id: string;
  type: NodeType;
  label: string;
  sub: string;
  status: string;
  w: number;
  h: number;
  x: number;
  y: number;
};

type GraphEdge = {
  source: string;
  target: string;
  kind: "strong" | "related";
};

type CareerBundle = {
  experiences: CareerExperience[];
  projects: CareerProject[];
  achievements: CareerAchievement[];
  skills: CareerSkill[];
  education: CareerEducation[];
  certifications: CareerCertification[];
  knowledge: ProfessionalKnowledge[];
};

const TYPE_COLOR: Record<NodeType, string> = {
  profile: "var(--chart-1)",
  experience: "var(--chart-1)",
  projects: "#37c2a0",
  skills: "#a78bfa",
  technology: "#f0a04b",
  knowledge: "#e08a6a",
};

function typeLabel(type: NodeType) {
  const keys: Record<NodeType, string> = {
    profile: "map.you",
    experience: "map.role",
    projects: "map.project",
    skills: "map.skill",
    technology: "map.technologies",
    knowledge: "map.knowledge",
  };
  return t(keys[type]);
}

function filterLabel(type: Exclude<NodeType, "profile">) {
  const keys: Record<Exclude<NodeType, "profile">, string> = {
    experience: "map.roles",
    projects: "map.projects",
    skills: "map.skills",
    technology: "map.technologies",
    knowledge: "map.knowledge",
  };
  return t(keys[type]);
}

const DEFAULT_VISIBLE: Record<Exclude<NodeType, "profile">, boolean> = {
  experience: true,
  projects: true,
  skills: true,
  technology: true,
  knowledge: true,
};

const CARD: Record<NodeType, { w: number; h: number }> = {
  profile: { w: 220, h: 64 },
  experience: { w: 168, h: 54 },
  projects: { w: 156, h: 50 },
  skills: { w: 150, h: 50 },
  technology: { w: 108, h: 34 },
  knowledge: { w: 150, h: 46 },
};

const LAYOUT = { width: 1120, height: 620 };

function norm(s: string) {
  return s.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, " ").trim();
}

function dateRange(start?: string | null, end?: string | null) {
  if (!start && !end) return "";
  return [start, end || t("common.present")].filter(Boolean).join(" – ");
}

function shorten(value: string, n: number) {
  const text = value.trim();
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function skillKeys(skill: CareerSkill) {
  return [skill.name, skill.canonical_name, ...(skill.synonyms || [])].map(norm).filter(Boolean);
}

function spread(count: number, start: number, end: number) {
  if (count <= 0) return [];
  if (count === 1) return [(start + end) / 2];
  return Array.from({ length: count }, (_, i) => start + (i * (end - start)) / (count - 1));
}

function addNode(nodes: GraphNode[], seen: Set<string>, node: Omit<GraphNode, "x" | "y">) {
  if (seen.has(node.id)) return;
  seen.add(node.id);
  nodes.push({ ...node, x: 0, y: 0 });
}

function addEdge(edges: GraphEdge[], source: string, target: string, kind: GraphEdge["kind"]) {
  if (!source || !target || source === target) return;
  if (edges.some((e) => e.source === source && e.target === target && e.kind === kind)) return;
  edges.push({ source, target, kind });
}

function buildGraph(bundle: CareerBundle, profile: CareerProfile | null): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  const expById = Object.fromEntries(bundle.experiences.map((e) => [e.id, e]));

  addNode(nodes, seen, {
    id: "profile:self",
    type: "profile",
    label: profile?.full_name || t("career.title"),
    sub: profile?.headline || t("map.careerGraph"),
    status: "",
    ...CARD.profile,
  });

  const roles = [...bundle.experiences]
    .sort((a, b) => (b.start_date || "").localeCompare(a.start_date || ""))
    .slice(0, 6);
  for (const exp of roles) {
    addNode(nodes, seen, {
      id: `experience:${exp.id}`,
      type: "experience",
      label: exp.job_title || exp.organization,
      sub: exp.organization,
      status: exp.verification_status || "",
      ...CARD.experience,
    });
    addEdge(edges, "profile:self", `experience:${exp.id}`, "strong");
  }

  const projects = bundle.projects.slice(0, 8);
  for (const proj of projects) {
    addNode(nodes, seen, {
      id: `project:${proj.id}`,
      type: "projects",
      label: proj.name,
      sub: proj.role || (proj.experience_id && expById[proj.experience_id]?.organization) || "Project",
      status: proj.verification_status || "",
      ...CARD.projects,
    });
    addEdge(edges, "profile:self", `project:${proj.id}`, "related");
    if (proj.experience_id && seen.has(`experience:${proj.experience_id}`)) {
      addEdge(edges, `project:${proj.id}`, `experience:${proj.experience_id}`, "strong");
    }
  }

  const rankedSkills = [...bundle.skills]
    .sort((a, b) => (b.evidence_count || 0) - (a.evidence_count || 0))
    .slice(0, 8);
  const skillIdByKey = new Map<string, string>();
  for (const skill of rankedSkills) {
    const id = `skill:${skill.id}`;
    addNode(nodes, seen, {
      id,
      type: "skills",
      label: skill.canonical_name || skill.name,
      sub: [skill.proficiency, skill.category].filter(Boolean).join(" · "),
      status: skill.verification_status || "",
      ...CARD.skills,
    });
    addEdge(edges, "profile:self", id, "related");
    for (const key of skillKeys(skill)) skillIdByKey.set(key, id);
  }

  for (const ach of bundle.achievements) {
    for (const term of ach.skills || []) {
      const sid = skillIdByKey.get(norm(term));
      if (!sid) continue;
      if (ach.experience_id && seen.has(`experience:${ach.experience_id}`)) {
        addEdge(edges, sid, `experience:${ach.experience_id}`, "related");
      }
      if (ach.project_id && seen.has(`project:${ach.project_id}`)) {
        addEdge(edges, sid, `project:${ach.project_id}`, "strong");
      }
    }
  }

  const techCount = new Map<string, { label: string; count: number; links: { id: string; kind: GraphEdge["kind"] }[] }>();
  const bumpTech = (term: string, linkId: string, kind: GraphEdge["kind"]) => {
    const key = norm(term);
    if (!key || skillIdByKey.has(key)) return;
    const current = techCount.get(key) || { label: term, count: 0, links: [] };
    current.count += 1;
    current.links.push({ id: linkId, kind });
    techCount.set(key, current);
  };
  for (const exp of roles) {
    for (const term of exp.technologies || []) bumpTech(term, `experience:${exp.id}`, "related");
  }
  for (const proj of projects) {
    for (const term of proj.technologies || []) bumpTech(term, `project:${proj.id}`, "strong");
  }

  const techs = [...techCount.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 8);
  for (const [key, tech] of techs) {
    const id = `tech:${key}`;
    addNode(nodes, seen, {
      id,
      type: "technology",
      label: tech.label,
      sub: tech.count > 1 ? `${tech.count} links` : "",
      status: "",
      ...CARD.technology,
    });
    for (const link of tech.links) {
      if (seen.has(link.id)) addEdge(edges, id, link.id, link.kind);
    }
  }

  const knowledge = (bundle.knowledge || []).slice(0, 8);
  for (const item of knowledge) {
    const id = `knowledge:${item.id}`;
    addNode(nodes, seen, {
      id,
      type: "knowledge",
      label: item.canonical_name || item.name,
      sub: [item.kind, item.depth].filter(Boolean).join(" · "),
      status: item.verification_status || "",
      ...CARD.knowledge,
    });
    addEdge(edges, "profile:self", id, "related");
    for (const ctx of item.contexts || []) {
      if (ctx.experience_id && seen.has(`experience:${ctx.experience_id}`)) {
        addEdge(edges, id, `experience:${ctx.experience_id}`, "strong");
      }
      if (ctx.project_id && seen.has(`project:${ctx.project_id}`)) {
        addEdge(edges, id, `project:${ctx.project_id}`, "related");
      }
    }
  }

  return { nodes, edges };
}

function layoutHubSpoke(nodes: GraphNode[]) {
  const { width, height } = LAYOUT;
  const cx = width / 2;
  const cy = height / 2 + 8;
  const hub = nodes.find((n) => n.type === "profile");
  if (hub) {
    hub.x = cx;
    hub.y = cy;
  }

  const roles = nodes.filter((n) => n.type === "experience");
  const projects = nodes.filter((n) => n.type === "projects");
  const skills = nodes.filter((n) => n.type === "skills");
  const techs = nodes.filter((n) => n.type === "technology");
  const knowledge = nodes.filter((n) => n.type === "knowledge");

  spread(roles.length, 150, height - 150).forEach((y, i) => {
    roles[i].x = 128;
    roles[i].y = y;
  });
  spread(projects.length, 250, width - 250).forEach((x, i) => {
    projects[i].x = x;
    projects[i].y = 78;
  });
  spread(skills.length, 150, height - 150).forEach((y, i) => {
    skills[i].x = width - 128;
    skills[i].y = y;
  });
  spread(techs.length, 180, width / 2 - 20).forEach((x, i) => {
    techs[i].x = x;
    techs[i].y = height - 70;
  });
  spread(knowledge.length, width / 2 + 20, width - 180).forEach((x, i) => {
    knowledge[i].x = x;
    knowledge[i].y = height - 70;
  });
}

function fitTransform(nodes: GraphNode[], width: number, height: number) {
  if (!nodes.length) return { x: 0, y: 0, k: 1 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.x - n.w / 2);
    minY = Math.min(minY, n.y - n.h / 2);
    maxX = Math.max(maxX, n.x + n.w / 2);
    maxY = Math.max(maxY, n.y + n.h / 2);
  }
  const pad = 48;
  const gw = Math.max(maxX - minX, 1);
  const gh = Math.max(maxY - minY, 1);
  const k = Math.min(width / (gw + pad * 2), height / (gh + pad * 2), 1.2);
  return {
    k,
    x: (width - gw * k) / 2 - minX * k,
    y: (height - gh * k) / 2 - minY * k,
  };
}

function tabFor(type: NodeType): CareerTabKey {
  if (type === "profile") return "profile";
  if (type === "technology") return "skills";
  if (type === "knowledge") return "knowledge";
  return type;
}

export function CareerOverview({ onOpenTab }: { onOpenTab: (tab: CareerTabKey) => void }) {
  const bundle = useApi<CareerBundle>(async () => {
    const [experiences, projects, achievements, skills, education, certifications, knowledge] = await Promise.all([
      api.get<CareerExperience[]>("/api/career/experiences"),
      api.get<CareerProject[]>("/api/career/projects"),
      api.get<CareerAchievement[]>("/api/career/achievements"),
      api.get<CareerSkill[]>("/api/career/skills"),
      api.get<CareerEducation[]>("/api/career/education"),
      api.get<CareerCertification[]>("/api/career/certifications"),
      api.get<ProfessionalKnowledge[]>("/api/career/knowledge"),
    ]);
    return { experiences, projects, achievements, skills, education, certifications, knowledge };
  });
  const profile = useApi<CareerProfile>(() => api.get("/api/career/profile"));

  const [visible, setVisible] = useState(DEFAULT_VISIBLE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ mode: "pan" | "node"; id?: string; x: number; y: number } | null>(null);

  const stats = useMemo(() => {
    const b = bundle.data;
    if (!b) return null;
    return {
      experiences: b.experiences.length,
      projects: b.projects.length,
      skills: b.skills.length,
      techs: new Set([
        ...b.experiences.flatMap((e) => e.technologies || []),
        ...b.projects.flatMap((p) => p.technologies || []),
      ]).size,
      knowledge: b.knowledge.length,
      total: b.experiences.length + b.projects.length + b.skills.length + b.knowledge.length,
    };
  }, [bundle.data]);

  useEffect(() => {
    if (!bundle.data) return;
    const graph = buildGraph(bundle.data, profile.data);
    layoutHubSpoke(graph.nodes);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    const svg = svgRef.current;
    setTransform(fitTransform(graph.nodes, svg?.clientWidth || 960, svg?.clientHeight || 560));
    setSelectedId(null);
  }, [bundle.data, profile.data]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setTransform((prev) => {
        const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
        const nextK = Math.min(3, Math.max(0.35, prev.k * factor));
        return {
          k: nextK,
          x: mx - ((mx - prev.x) * nextK) / prev.k,
          y: my - ((my - prev.y) * nextK) / prev.k,
        };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [nodes.length]);

  const shownNodes = useMemo(() => {
    const q = norm(query);
    return nodes.filter((n) => {
      if (n.type !== "profile" && !visible[n.type]) return false;
      if (!q) return true;
      return norm(`${n.label} ${n.sub}`).includes(q);
    });
  }, [nodes, visible, query]);
  const shownIds = useMemo(() => new Set(shownNodes.map((n) => n.id)), [shownNodes]);
  const shownEdges = useMemo(
    () => edges.filter((e) => shownIds.has(e.source) && shownIds.has(e.target)),
    [edges, shownIds],
  );
  const nodeById = useMemo(() => Object.fromEntries(shownNodes.map((n) => [n.id, n])), [shownNodes]);
  const selected = selectedId ? nodeById[selectedId] || nodes.find((n) => n.id === selectedId) : null;
  const activeIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const next = new Set<string>([selectedId]);
    for (const e of shownEdges) {
      if (e.source === selectedId) next.add(e.target);
      if (e.target === selectedId) next.add(e.source);
    }
    return next;
  }, [selectedId, shownEdges]);

  const pointer = (e: React.PointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = pointer(e);
    const dx = p.x - d.x;
    const dy = p.y - d.y;
    d.x = p.x;
    d.y = p.y;
    if (d.mode === "pan") {
      setTransform((t) => ({ ...t, x: t.x + dx, y: t.y + dy }));
      return;
    }
    if (d.id) {
      setNodes((prev) =>
        prev.map((n) => (n.id === d.id ? { ...n, x: n.x + dx / transform.k, y: n.y + dy / transform.k } : n)),
      );
    }
  };

  const zoomBy = (factor: number) => {
    const svg = svgRef.current;
    const mx = (svg?.clientWidth || 960) / 2;
    const my = (svg?.clientHeight || 560) / 2;
    setTransform((prev) => {
      const nextK = Math.min(3, Math.max(0.35, prev.k * factor));
      return {
        k: nextK,
        x: mx - ((mx - prev.x) * nextK) / prev.k,
        y: my - ((my - prev.y) * nextK) / prev.k,
      };
    });
  };

  if (bundle.loading) return <p className="muted">{t("career.loadingMap")}</p>;
  if (bundle.error) return <p className="alert error">{bundle.error}</p>;
  if (!bundle.data || !stats?.total) {
    return <Empty>{t("career.mapEmpty")}</Empty>;
  }

  return (
    <>
      <div className="ck-stats">
        <div className="stat-card"><div className="stat-value">{stats.experiences}</div><div className="stat-label">{t("map.roles")}</div></div>
        <div className="stat-card"><div className="stat-value">{stats.projects}</div><div className="stat-label">{t("map.projects")}</div></div>
        <div className="stat-card"><div className="stat-value">{stats.skills}</div><div className="stat-label">{t("map.skills")}</div></div>
        <div className="stat-card"><div className="stat-value">{stats.knowledge}</div><div className="stat-label">{t("map.knowledge")}</div></div>
        <div className="stat-card"><div className="stat-value">{stats.techs}</div><div className="stat-label">{t("map.technologies")}</div></div>
      </div>

      <div className="ck-graph-panel">
        <div className="row spread mb">
          <div>
            <h3 className="ck-graph-title">Career Knowledge Graph</h3>
            <p className="small muted" style={{ margin: 0 }}>Roles, projects, skills, and tools around your profile.</p>
          </div>
          <div className="row">
            <input
              className="ck-search"
              placeholder={t("map.search")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="button" className="sm" onClick={() => zoomBy(1.15)}>+</button>
            <button type="button" className="sm" onClick={() => zoomBy(1 / 1.15)}>−</button>
          </div>
        </div>

        <div className="row spread mb">
          <div className="ck-map-filters">
            {(Object.keys(DEFAULT_VISIBLE) as (keyof typeof DEFAULT_VISIBLE)[]).map((type) => (
              <button
                key={type}
                type="button"
                className={`ck-filter ${visible[type] ? "on" : ""}`}
                style={{ ["--ck-color" as string]: TYPE_COLOR[type] }}
                onClick={() => setVisible((v) => ({ ...v, [type]: !v[type] }))}
              >
                {filterLabel(type)}
              </button>
            ))}
          </div>
          <span className="small muted">Solid = strong link · dashed = related</span>
        </div>

        <div className="ck-map">
          <svg
            ref={svgRef}
            className="ck-map-svg"
            onPointerMove={onPointerMove}
            onPointerUp={() => { drag.current = null; }}
            onPointerLeave={() => { drag.current = null; }}
            onPointerDown={(e) => {
              if (e.target !== svgRef.current && (e.target as Element).tagName !== "svg") return;
              const p = pointer(e);
              drag.current = { mode: "pan", x: p.x, y: p.y };
              (e.target as Element).setPointerCapture?.(e.pointerId);
            }}
          >
            <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
              <text className="ck-cluster-label" x={128} y={118} textAnchor="middle">{t("map.roles")}</text>
              <text className="ck-cluster-label" x={LAYOUT.width / 2} y={36} textAnchor="middle">{t("map.projects")}</text>
              <text className="ck-cluster-label" x={LAYOUT.width - 128} y={118} textAnchor="middle">{t("map.skills")}</text>
              <text className="ck-cluster-label" x={LAYOUT.width / 2} y={LAYOUT.height - 28} textAnchor="middle">{t("map.technologies")}</text>
              {shownEdges.map((e, i) => {
                const a = nodeById[e.source];
                const b = nodeById[e.target];
                if (!a || !b) return null;
                const active = !selectedId || activeIds.has(e.source) && activeIds.has(e.target) && (e.source === selectedId || e.target === selectedId);
                return (
                  <line
                    key={`${e.source}-${e.target}-${i}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    className={`ck-edge ${e.kind} ${active && selectedId ? "active" : ""}`}
                    opacity={selectedId && !active ? 0.12 : 0.9}
                  />
                );
              })}
              {shownNodes.map((n) => {
                const hovered = hoverId === n.id || selectedId === n.id;
                const dimmed = selectedId ? !activeIds.has(n.id) : false;
                const color = TYPE_COLOR[n.type];
                return (
                  <g
                    key={n.id}
                    className={`ck-node${n.type === "profile" ? " profile" : ""}`}
                    transform={`translate(${n.x} ${n.y})`}
                    opacity={dimmed ? 0.28 : 1}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      const p = pointer(e);
                      drag.current = { mode: "node", id: n.id, x: p.x, y: p.y };
                      setSelectedId(n.id);
                      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
                    }}
                    onPointerEnter={() => setHoverId(n.id)}
                    onPointerLeave={() => setHoverId((h) => (h === n.id ? null : h))}
                  >
                    <title>{n.label}{n.sub ? ` — ${n.sub}` : ""}</title>
                    <rect
                      x={-n.w / 2}
                      y={-n.h / 2}
                      width={n.w}
                      height={n.h}
                      rx={n.type === "profile" ? 12 : 10}
                      fill={n.type === "profile" ? "var(--chart-profile-fill)" : `color-mix(in srgb, ${color} 13%, transparent)`}
                      stroke={hovered ? "var(--chart-hover-stroke)" : color}
                      strokeWidth={hovered ? 2 : 1.4}
                    />
                    <text className="ck-node-label" y={n.sub ? -4 : 4} textAnchor="middle">
                      {shorten(n.label, n.type === "technology" ? 14 : 22)}
                    </text>
                    {n.sub ? (
                      <text className="ck-node-sub" y={14} textAnchor="middle">
                        {shorten(n.sub, 24)}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </g>
          </svg>
          {selected && (
            <div className="ck-map-detail">
              <div className="row spread">
                <span className="badge" style={{ color: TYPE_COLOR[selected.type], background: "transparent", border: `1px solid ${TYPE_COLOR[selected.type]}` }}>
                  {typeLabel(selected.type)}
                </span>
                {selected.status && <span className={`badge ${selected.status}`}>{selected.status.replace("_", " ")}</span>}
              </div>
              <div className="title mt">{selected.label}</div>
              {selected.sub && <div className="meta">{selected.sub}</div>}
              <div className="small muted mt">
                {shownEdges.filter((e) => e.source === selected.id || e.target === selected.id).length} connection
                {shownEdges.filter((e) => e.source === selected.id || e.target === selected.id).length === 1 ? "" : "s"}
              </div>
              <button className="primary sm mt" onClick={() => onOpenTab(tabFor(selected.type))}>
                {selected.type === "profile" ? t("career.profile") : filterLabel(selected.type as Exclude<NodeType, "profile">)}
              </button>
            </div>
          )}
        </div>
        <div className="ck-legend">
          {(Object.keys(DEFAULT_VISIBLE) as (keyof typeof DEFAULT_VISIBLE)[]).map((type) => (
            <span key={type} className="ck-legend-item">
              <span className="evo-dot" style={{ background: TYPE_COLOR[type] }} />
              {filterLabel(type)}
            </span>
          ))}
        </div>
      </div>

      <CareerEvolution experiences={bundle.data.experiences} narratives={profile.data?.career_narratives} />
    </>
  );
}
