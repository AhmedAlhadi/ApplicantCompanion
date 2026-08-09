import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, getToken, setToken, workflowEventsUrl } from "../api/client";
import type { User, WorkflowRun } from "../api/types";

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
  const logout = () => {
    setToken(null);
    navigate("/login");
  };
  const links: [string, string][] = [
    ["/", "Dashboard"],
    ["/career", "Career Knowledge"],
    ["/jobs", "Jobs"],
    ["/applications", "Applications"],
    ["/templates", "CV Templates"],
    ["/cover-letter-templates", "Cover Letter Templates"],
    ["/documents", "Documents"],
    ["/settings", "Settings"],
    ["/ai-config", "AI / Model Config"],
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Applicant<span>Companion</span>
        </div>
        <nav>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div>{user.full_name || user.email}</div>
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

/** Subscribe to live workflow progress over SSE, falling back to polling. */
export function useWorkflow(runId: string | null, pollUrl: string | null, onDone?: () => void) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    if (!pollUrl) return;
    let stopped = false;
    let es: EventSource | null = null;
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
