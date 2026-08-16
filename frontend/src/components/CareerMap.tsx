import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  CareerAchievement,
  CareerCertification,
  CareerEducation,
  CareerExperience,
  CareerProject,
  CareerSkill,
} from "../api/types";
import { Empty, useApi } from "./ui";

export type CareerTabKey =
  | "experience"
  | "projects"
  | "achievements"
  | "skills"
  | "education"
  | "certifications";

type NodeType = CareerTabKey;

type GraphNode = {
  id: string;
  type: NodeType;
  label: string;
  sub: string;
  cluster: string;
  status: string;
  r: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
};

type GraphEdge = {
  source: string;
  target: string;
  kind: "parent" | "skill";
};

type CareerBundle = {
  experiences: CareerExperience[];
  projects: CareerProject[];
  achievements: CareerAchievement[];
  skills: CareerSkill[];
  education: CareerEducation[];
  certifications: CareerCertification[];
};

const TYPE_COLOR: Record<NodeType, string> = {
  experience: "#5b8cff",
  projects: "#37c2a0",
  achievements: "#43c97e",
  skills: "#8b95b3",
  education: "#e0a84f",
  certifications: "#c084fc",
};

const TYPE_LABEL: Record<NodeType, string> = {
  experience: "Role",
  projects: "Project",
  achievements: "Achievement",
  skills: "Skill",
  education: "Education",
  certifications: "Certification",
};

const FILTER_LABEL: Record<NodeType, string> = {
  experience: "Roles",
  projects: "Projects",
  achievements: "Achievements",
  skills: "Skills",
  education: "Education",
  certifications: "Certifications",
};

const DEFAULT_VISIBLE: Record<NodeType, boolean> = {
  experience: true,
  projects: true,
  achievements: true,
  skills: true,
  education: true,
  certifications: true,
};

function norm(s: string) {
  return s.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, " ").trim();
}

function dateRange(start?: string | null, end?: string | null) {
  if (!start && !end) return "";
  return [start, end || "Present"].filter(Boolean).join(" – ");
}

function statusStroke(status: string) {
  if (status === "verified") return "#43c97e";
  if (status === "needs_review") return "#5b8cff";
  if (status === "unverified") return "#e0a84f";
  return "#2a3554";
}

function skillKeys(skill: CareerSkill) {
  return [skill.name, skill.canonical_name, ...(skill.synonyms || [])].map(norm).filter(Boolean);
}

function buildGraph(bundle: CareerBundle): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  const addNode = (node: Omit<GraphNode, "x" | "y" | "vx" | "vy">) => {
    if (seen.has(node.id)) return;
    seen.add(node.id);
    nodes.push({ ...node, x: 0, y: 0, vx: 0, vy: 0 });
  };
  const addEdge = (source: string, target: string, kind: GraphEdge["kind"]) => {
    if (!source || !target || source === target) return;
    edges.push({ source, target, kind });
  };

  const expCluster = (exp: CareerExperience) => (exp.domains || []).map((d) => d.trim()).find(Boolean) || "General";
  const expById = Object.fromEntries(bundle.experiences.map((e) => [e.id, e]));
  const projById = Object.fromEntries(bundle.projects.map((p) => [p.id, p]));

  for (const exp of bundle.experiences) {
    addNode({
      id: `experience:${exp.id}`,
      type: "experience",
      label: exp.job_title || exp.organization,
      sub: [exp.organization, dateRange(exp.start_date, exp.end_date)].filter(Boolean).join(" · "),
      cluster: expCluster(exp),
      status: exp.verification_status || "",
      r: 16,
    });
  }

  for (const proj of bundle.projects) {
    const parent = proj.experience_id ? expById[proj.experience_id] : null;
    addNode({
      id: `project:${proj.id}`,
      type: "projects",
      label: proj.name,
      sub: proj.role || (parent ? parent.job_title : "Independent"),
      cluster: parent ? expCluster(parent) : "Independent",
      status: proj.verification_status || "",
      r: 12,
    });
    if (proj.experience_id) addEdge(`project:${proj.id}`, `experience:${proj.experience_id}`, "parent");
  }

  for (const ach of bundle.achievements) {
    const parentExp = ach.experience_id ? expById[ach.experience_id] : null;
    const parentProj = ach.project_id ? projById[ach.project_id] : null;
    const cluster = parentExp
      ? expCluster(parentExp)
      : parentProj?.experience_id && expById[parentProj.experience_id]
        ? expCluster(expById[parentProj.experience_id])
        : ach.education_id
          ? "Education"
          : "Unlinked";
    addNode({
      id: `achievement:${ach.id}`,
      type: "achievements",
      label: ach.title || ach.description.slice(0, 48) || "Achievement",
      sub: ach.quantified_result || "",
      cluster,
      status: ach.verification_status || "",
      r: 10,
    });
    if (ach.experience_id) addEdge(`achievement:${ach.id}`, `experience:${ach.experience_id}`, "parent");
    if (ach.project_id) addEdge(`achievement:${ach.id}`, `project:${ach.project_id}`, "parent");
    if (ach.education_id) addEdge(`achievement:${ach.id}`, `education:${ach.education_id}`, "parent");
  }

  for (const edu of bundle.education) {
    addNode({
      id: `education:${edu.id}`,
      type: "education",
      label: [edu.degree, edu.field_of_study].filter(Boolean).join(" ") || edu.institution,
      sub: edu.institution,
      cluster: "Education",
      status: edu.verification_status || "",
      r: 11,
    });
  }

  for (const cert of bundle.certifications) {
    addNode({
      id: `certification:${cert.id}`,
      type: "certifications",
      label: cert.name,
      sub: cert.issuer,
      cluster: "Credentials",
      status: cert.verification_status || "",
      r: 11,
    });
  }

  const skillIdByKey = new Map<string, string>();
  for (const skill of bundle.skills) {
    const id = `skill:${skill.id}`;
    addNode({
      id,
      type: "skills",
      label: skill.canonical_name || skill.name,
      sub: [skill.category, skill.proficiency].filter(Boolean).join(" · "),
      cluster: skill.category || "Skills",
      status: skill.verification_status || "",
      r: 8 + Math.min(skill.evidence_count || 0, 4),
    });
    for (const key of skillKeys(skill)) skillIdByKey.set(key, id);
  }

  const topicId = (term: string) => `topic:${norm(term)}`;
  const ensureTopic = (term: string, cluster: string) => {
    const key = norm(term);
    if (!key) return null;
    const existing = skillIdByKey.get(key);
    if (existing) return existing;
    const id = topicId(term);
    addNode({
      id,
      type: "skills",
      label: term,
      sub: "from a role or achievement",
      cluster,
      status: "",
      r: 7,
    });
    skillIdByKey.set(key, id);
    return id;
  };

  for (const exp of bundle.experiences) {
    const cluster = expCluster(exp);
    for (const term of [...(exp.technologies || []), ...(exp.domains || [])]) {
      const sid = ensureTopic(term, cluster);
      if (sid) addEdge(sid, `experience:${exp.id}`, "skill");
    }
  }
  for (const proj of bundle.projects) {
    const parent = proj.experience_id ? expById[proj.experience_id] : null;
    const cluster = parent ? expCluster(parent) : "Independent";
    for (const term of proj.technologies || []) {
      const sid = ensureTopic(term, cluster);
      if (sid) addEdge(sid, `project:${proj.id}`, "skill");
    }
  }
  for (const ach of bundle.achievements) {
    for (const term of ach.skills || []) {
      const sid = ensureTopic(term, ach.experience_id && expById[ach.experience_id] ? expCluster(expById[ach.experience_id]) : "Skills");
      if (sid) addEdge(sid, `achievement:${ach.id}`, "skill");
    }
  }

  const connected = new Set<string>();
  for (const e of edges) {
    connected.add(e.source);
    connected.add(e.target);
  }
  const keptNodes = nodes.filter((n) => n.type !== "skills" || connected.has(n.id) || (bundle.skills.length > 0 && n.id.startsWith("skill:")));
  const keptIds = new Set(keptNodes.map((n) => n.id));
  return {
    nodes: keptNodes,
    edges: edges.filter((e) => keptIds.has(e.source) && keptIds.has(e.target)),
  };
}

function simulate(nodes: GraphNode[], edges: GraphEdge[], ticks = 240) {
  const n = nodes.length;
  if (!n) return;
  const clusters = [...new Set(nodes.map((d) => d.cluster))];
  clusters.forEach((cluster, i) => {
    const members = nodes.filter((d) => d.cluster === cluster);
    const angle = (i / Math.max(clusters.length, 1)) * Math.PI * 2;
    const cx = 420 + Math.cos(angle) * 210;
    const cy = 300 + Math.sin(angle) * 160;
    members.forEach((d, j) => {
      const a = (j / Math.max(members.length, 1)) * Math.PI * 2;
      d.x = cx + Math.cos(a) * (28 + members.length);
      d.y = cy + Math.sin(a) * (28 + members.length);
      d.vx = 0;
      d.vy = 0;
    });
  });

  const index = Object.fromEntries(nodes.map((d, i) => [d.id, i]));
  for (let t = 0; t < ticks; t++) {
    const alpha = 1 - t / ticks;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        const dist2 = dx * dx + dy * dy || 0.01;
        const dist = Math.sqrt(dist2);
        const force = (1100 * alpha) / dist2;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        nodes[i].vx -= fx;
        nodes[i].vy -= fy;
        nodes[j].vx += fx;
        nodes[j].vy += fy;
      }
    }
    for (const e of edges) {
      const a = nodes[index[e.source]];
      const b = nodes[index[e.target]];
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const rest = e.kind === "skill" ? 96 : 72;
      const f = (dist - rest) * 0.085 * alpha;
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }
    const centroids = new Map<string, { x: number; y: number; n: number }>();
    for (const d of nodes) {
      const c = centroids.get(d.cluster) || { x: 0, y: 0, n: 0 };
      c.x += d.x;
      c.y += d.y;
      c.n += 1;
      centroids.set(d.cluster, c);
    }
    for (const d of nodes) {
      const c = centroids.get(d.cluster)!;
      d.vx += ((c.x / c.n) - d.x) * 0.012;
      d.vy += ((c.y / c.n) - d.y) * 0.012;
      d.vx += (420 - d.x) * 0.004;
      d.vy += (300 - d.y) * 0.004;
      d.vx *= 0.72;
      d.vy *= 0.72;
      d.x += d.vx;
      d.y += d.vy;
    }
  }
}

function fitTransform(nodes: GraphNode[], width: number, height: number) {
  if (!nodes.length) return { x: 0, y: 0, k: 1 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.x - n.r);
    minY = Math.min(minY, n.y - n.r);
    maxX = Math.max(maxX, n.x + n.r);
    maxY = Math.max(maxY, n.y + n.r);
  }
  const pad = 56;
  const gw = Math.max(maxX - minX, 1);
  const gh = Math.max(maxY - minY, 1);
  const k = Math.min(width / (gw + pad * 2), height / (gh + pad * 2), 1.35);
  return {
    k,
    x: (width - gw * k) / 2 - minX * k,
    y: (height - gh * k) / 2 - minY * k,
  };
}

export function CareerOverview({ onOpenTab }: { onOpenTab: (tab: CareerTabKey) => void }) {
  const bundle = useApi<CareerBundle>(async () => {
    const [experiences, projects, achievements, skills, education, certifications] = await Promise.all([
      api.get<CareerExperience[]>("/api/career/experiences"),
      api.get<CareerProject[]>("/api/career/projects"),
      api.get<CareerAchievement[]>("/api/career/achievements"),
      api.get<CareerSkill[]>("/api/career/skills"),
      api.get<CareerEducation[]>("/api/career/education"),
      api.get<CareerCertification[]>("/api/career/certifications"),
    ]);
    return { experiences, projects, achievements, skills, education, certifications };
  });

  const [visible, setVisible] = useState(DEFAULT_VISIBLE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ mode: "pan" | "node"; id?: string; x: number; y: number } | null>(null);

  const stats = useMemo(() => {
    const b = bundle.data;
    if (!b) return null;
    const allStatus = [
      ...b.experiences,
      ...b.projects,
      ...b.achievements,
      ...b.skills,
      ...b.education,
      ...b.certifications,
    ];
    const verified = allStatus.filter((x) => x.verification_status === "verified").length;
    return {
      experiences: b.experiences.length,
      projects: b.projects.length,
      achievements: b.achievements.length,
      skills: b.skills.length,
      verified,
      total: allStatus.length,
      orphans: b.achievements.filter((a) => !a.experience_id && !a.project_id && !a.education_id).length,
    };
  }, [bundle.data]);

  useEffect(() => {
    if (!bundle.data) return;
    const graph = buildGraph(bundle.data);
    simulate(graph.nodes, graph.edges);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    const svg = svgRef.current;
    const width = svg?.clientWidth || 960;
    const height = svg?.clientHeight || 520;
    setTransform(fitTransform(graph.nodes, width, height));
    setSelectedId(null);
  }, [bundle.data]);

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

  const shownNodes = useMemo(() => nodes.filter((n) => visible[n.type]), [nodes, visible]);
  const shownIds = useMemo(() => new Set(shownNodes.map((n) => n.id)), [shownNodes]);
  const shownEdges = useMemo(
    () => edges.filter((e) => shownIds.has(e.source) && shownIds.has(e.target)),
    [edges, shownIds],
  );
  const nodeById = useMemo(() => Object.fromEntries(shownNodes.map((n) => [n.id, n])), [shownNodes]);
  const selected = selectedId ? nodeById[selectedId] || nodes.find((n) => n.id === selectedId) : null;

  const clusterLabels = useMemo(() => {
    const groups = new Map<string, { x: number; y: number; n: number }>();
    for (const n of shownNodes) {
      const g = groups.get(n.cluster) || { x: 0, y: 0, n: 0 };
      g.x += n.x;
      g.y += n.y;
      g.n += 1;
      groups.set(n.cluster, g);
    }
    return [...groups.entries()].map(([label, g]) => ({ label, x: g.x / g.n, y: g.y / g.n - 28 }));
  }, [shownNodes]);

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

  const toggleType = (type: NodeType) => {
    setVisible((v) => ({ ...v, [type]: !v[type] }));
  };

  if (bundle.loading) return <p className="muted">Loading career map…</p>;
  if (bundle.error) return <p className="alert error">{bundle.error}</p>;
  if (!bundle.data || !stats?.total) {
    return <Empty>Nothing in the knowledge base yet — ingest a CV or add a role to see the map.</Empty>;
  }

  return (
    <>
      <div className="ck-stats">
        <div className="stat-card"><div className="stat-value">{stats.experiences}</div><div className="stat-label">Roles</div></div>
        <div className="stat-card"><div className="stat-value">{stats.projects}</div><div className="stat-label">Projects</div></div>
        <div className="stat-card"><div className="stat-value">{stats.achievements}</div><div className="stat-label">Achievements</div></div>
        <div className="stat-card"><div className="stat-value">{stats.skills}</div><div className="stat-label">Skills</div></div>
        <div className="stat-card">
          <div className="stat-value">{stats.total ? Math.round((stats.verified / stats.total) * 100) : 0}%</div>
          <div className="stat-label">Verified</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.orphans}</div>
          <div className="stat-label">Unlinked achievements</div>
        </div>
      </div>

      <div className="row spread mb">
        <div className="ck-map-filters">
          {(["experience", "projects", "achievements", "skills", "education", "certifications"] as NodeType[]).map((type) => (
            <button
              key={type}
              type="button"
              className={`ck-filter ${visible[type] ? "on" : ""}`}
              style={{ ["--ck-color" as string]: TYPE_COLOR[type] }}
              onClick={() => toggleType(type)}
            >
              {FILTER_LABEL[type]}
            </button>
          ))}
        </div>
        <span className="small muted">Drag the canvas to pan · scroll to zoom · drag a node to pin it</span>
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
            {clusterLabels.map((c) => (
              <text key={c.label} className="ck-cluster-label" x={c.x} y={c.y} textAnchor="middle">
                {c.label}
              </text>
            ))}
            {shownEdges.map((e, i) => {
              const a = nodeById[e.source];
              const b = nodeById[e.target];
              if (!a || !b) return null;
              const active = selectedId && (e.source === selectedId || e.target === selectedId);
              return (
                <line
                  key={`${e.source}-${e.target}-${i}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  className={`ck-edge ${e.kind} ${active ? "active" : ""}`}
                />
              );
            })}
            {shownNodes.map((n) => {
              const hovered = hoverId === n.id || selectedId === n.id;
              return (
                <g
                  key={n.id}
                  className="ck-node"
                  transform={`translate(${n.x} ${n.y})`}
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
                  <circle
                    r={n.r + (hovered ? 2 : 0)}
                    fill={TYPE_COLOR[n.type]}
                    stroke={statusStroke(n.status)}
                    strokeWidth={n.status ? 2.4 : 1.2}
                    opacity={selectedId && selectedId !== n.id ? 0.45 : 0.95}
                  />
                  <text className="ck-node-label" y={n.r + 12} textAnchor="middle">
                    {n.label.length > 22 ? `${n.label.slice(0, 20)}…` : n.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        {selected && (
          <div className="ck-map-detail">
            <div className="row spread">
              <span className="badge" style={{ color: TYPE_COLOR[selected.type], background: "transparent", border: `1px solid ${TYPE_COLOR[selected.type]}` }}>
                {TYPE_LABEL[selected.type]}
              </span>
              {selected.status && <span className={`badge ${selected.status}`}>{selected.status.replace("_", " ")}</span>}
            </div>
            <div className="title mt">{selected.label}</div>
            {selected.sub && <div className="meta">{selected.sub}</div>}
            <div className="meta">Field: {selected.cluster}</div>
            <div className="small muted mt">
              {shownEdges.filter((e) => e.source === selected.id || e.target === selected.id).length} connection
              {shownEdges.filter((e) => e.source === selected.id || e.target === selected.id).length === 1 ? "" : "s"}
            </div>
            <button className="primary sm mt" onClick={() => onOpenTab(selected.type)}>
              Open {FILTER_LABEL[selected.type].toLowerCase()}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
