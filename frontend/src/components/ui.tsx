import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, getToken, setToken, workflowEventsUrl } from "../api/client";
import type { User, WorkflowRun } from "../api/types";

type NavChild = { to: string; label: string; end?: boolean };
type NavGroup = { to: string; label: string; end?: boolean; children?: NavChild[] };

const NAV: NavGroup[] = [
  { to: "/", label: "Dashboard", end: true },
  {
    to: "/career",
    label: "My Career",
    children: [
      { to: "/career", label: "Knowledge Graph" },
      { to: "/career?tab=experience", label: "Roles & Projects" },
      { to: "/career?tab=skills", label: "Skills" },
      { to: "/career?tab=achievements", label: "Achievements" },
    ],
  },
  {
    to: "/jobs",
    label: "Jobs",
    children: [
      { to: "/jobs", label: "Job Match", end: true },
    ],
  },
  { to: "/applications", label: "Applications" },
  { to: "/documents", label: "Documents" },
  { to: "/templates", label: "CV Templates" },
  { to: "/cover-letter-templates", label: "Cover Letters" },
  { to: "/settings", label: "Settings" },
  { to: "/ai-config", label: "AI / Model Config" },
];

function careerTab(search: string) {
  return new URLSearchParams(search).get("tab") || "overview";
}

function isParentActive(item: NavGroup, pathname: string) {
  const url = new URL(item.to, "http://local");
  if (item.end) return pathname === url.pathname;
  return pathname === url.pathname || (url.pathname !== "/" && pathname.startsWith(`${url.pathname}/`));
}

function isChildActive(to: string, pathname: string, search: string, end?: boolean) {
  const url = new URL(to, "http://local");
  if (url.pathname !== pathname) {
    if (!end && url.pathname !== "/" && pathname.startsWith(`${url.pathname}/`)) return true;
    return false;
  }
  if (url.pathname === "/career") {
    return careerTab(search) === (url.searchParams.get("tab") || "overview");
  }
  return true;
}

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = () => {
    setLoading(true);
    fn()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, deps);
  return { data, error, loading, reload };
}

export function Layout({ user }: { user: User }) {
  const navigate = useNavigate();
  const location = useLocation();
  const logout = () => {
    setToken(null);
    navigate("/login");
  };
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Applicant<span>Companion</span>
        </div>
        <nav>
          {NAV.map((item) => {
            const parentActive = isParentActive(item, location.pathname);
            return (
              <div key={item.to} className="nav-group">
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={() => (parentActive ? "active" : "")}
                >
                  {item.label}
                </NavLink>
                {item.children && (
                  <div className="nav-children">
                    {item.children.map((child) => (
                      <NavLink
                        key={child.to}
                        to={child.to}
                        end={child.end}
                        className={() =>
                          isChildActive(child.to, location.pathname, location.search, child.end) ? "active" : ""
                        }
                      >
                        {child.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-user-name">{user.full_name || user.email}</div>
            <div className="sidebar-user-meta">{user.email}</div>
            {user.is_admin && <span className="badge needs_review">Admin</span>}
          </div>
          <button className="ghost sm" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

export function ScoreRing({ score, threshold }: { score: number; threshold?: number }) {
  const pct = Math.round(score * 100);
  const strong = threshold === undefined ? pct >= 80 : score >= threshold;
  return (
    <div className="score-ring">
      <div className="score-big" style={{ color: strong ? "var(--ok)" : "var(--warn)" }}>
        {pct}%
      </div>
      <div>
        <span className={`badge ${strong ? "strong" : "moderate"}`}>
          {strong ? "Strong Fit — Recommended to Apply" : "Moderate/Weak Fit"}
        </span>
        {threshold !== undefined && (
          <div className="small muted mt">threshold: {Math.round(threshold * 100)}%</div>
        )}
      </div>
    </div>
  );
}

export function ProgressStages({ workflow }: { workflow: WorkflowRun | null }) {
  const stages = workflow?.stages ?? [];
  if (!stages.length) return null;
  return (
    <ul className="stage-list">
      {stages.map((s) => (
        <li key={s.name}>
          <span className={`stage-dot ${s.status}`} />
          <span>{s.name.replace(/([A-Z])/g, " $1").trim()}</span>
          <span className={`badge ${s.status}`}>{s.status}</span>
          {s.error && <span className="small muted">{s.error}</span>}
        </li>
      ))}
    </ul>
  );
}

export function ProgressBar({ label }: { label?: string }) {
  return (
    <div className="progress-bar-wrap">
      {label ? <div className="small muted mb">{label}</div> : null}
      <div className="progress-bar" role="progressbar" aria-busy="true" aria-label={label || "Working"}>
        <div className="progress-bar-indeterminate" />
      </div>
    </div>
  );
}

/** Subscribe to live workflow progress over SSE, falling back to polling. */
export function useWorkflow(runId: string | null, pollUrl: string | null, onDone?: () => void) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    if (!pollUrl) return;
    let stopped = false;
    let es: EventSource | null = null;
    const pollingDeadline = Date.now() + 21 * 60 * 1000;
    const poll = async () => {
      try {
        const data = await api.get<WorkflowRun>(pollUrl);
        if (stopped) return;
        setRun(data);
        if (data.status === "COMPLETED" || data.status === "FAILED") {
          doneRef.current?.();
          return;
        }
      } catch {
        /* keep polling */
      }
      if (Date.now() >= pollingDeadline) {
        setRun((current) => ({
          id: current?.id ?? runId ?? "",
          status: "FAILED",
          current_stage: current?.current_stage ?? "",
          stages: current?.stages ?? [],
          workflow_type: current?.workflow_type ?? "job_analysis",
          error: "Progress polling exceeded the workflow lease. Retry the analysis.",
        }));
        doneRef.current?.();
        return;
      }
      if (!stopped) timer = window.setTimeout(poll, 1200);
    };
    let timer = window.setTimeout(poll, 400);
    if (runId) {
      // SSE for live updates; polling continues as fallback
      es = new EventSource(workflowEventsUrl(runId));
      es.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data);
          if (parsed?.data?.stages) setRun(parsed.data);
        } catch {
          /* ignore */
        }
      };
    }
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      es?.close();
    };
  }, [runId, pollUrl]);
  return run;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="alert error">{error}</div>;
}

export function Spinner() {
  return <span className="spinner" />;
}

export { Link };
