import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Briefcase,
  Cpu,
  FileStack,
  Files,
  LayoutDashboard,
  LayoutTemplate,
  LogOut,
  Mail,
  Moon,
  Network,
  Settings as SettingsIcon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { api, getToken, setToken, workflowEventsUrl } from "../api/client";
import type { User, WorkflowRun } from "../api/types";
import { useT } from "../lib/i18n";
import { useTheme } from "../lib/theme";

type NavChild = { to: string; end?: boolean };
type NavGroup = { to: string; end?: boolean; icon: LucideIcon; children?: NavChild[] };

const NAV: Omit<NavGroup, "label">[] = [
  { to: "/", end: true, icon: LayoutDashboard },
  {
    to: "/career",
    icon: Network,
    children: [
      { to: "/career" },
      { to: "/career?tab=experience" },
      { to: "/career?tab=skills" },
      { to: "/career?tab=achievements" },
    ],
  },
  {
    to: "/jobs",
    icon: Briefcase,
    children: [
      { to: "/jobs", end: true },
    ],
  },
  { to: "/applications", icon: FileStack },
  { to: "/documents", icon: Files },
  { to: "/templates", icon: LayoutTemplate },
  { to: "/cover-letter-templates", icon: Mail },
  { to: "/settings", icon: SettingsIcon },
  { to: "/ai-config", icon: Cpu },
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
  const { theme, setPref } = useTheme();
  const { t } = useT();
  const logout = () => {
    setToken(null);
    navigate("/login");
  };
  const navLabels: Record<string, string> = {
    "/": t("nav.dashboard"),
    "/career": t("nav.career"),
    "/jobs": t("nav.jobs"),
    "/applications": t("nav.applications"),
    "/documents": t("nav.documents"),
    "/templates": t("nav.cvTemplates"),
    "/cover-letter-templates": t("nav.coverLetters"),
    "/settings": t("nav.settings"),
    "/ai-config": t("nav.aiConfig"),
  };
  const childLabels: Record<string, string> = {
    "/career": t("nav.knowledgeGraph"),
    "/career?tab=experience": t("nav.rolesProjects"),
    "/career?tab=skills": t("nav.skills"),
    "/career?tab=achievements": t("nav.achievements"),
    "/jobs": t("nav.jobMatch"),
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
            const Icon = item.icon;
            return (
              <div key={item.to} className="nav-group">
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={() => (parentActive ? "active" : "")}
                >
                  <Icon className="nav-icon" aria-hidden />
                  {navLabels[item.to] ?? item.to}
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
                        {childLabels[child.to] ?? child.to}
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
            {user.is_admin && <span className="badge needs_review">{t("common.admin")}</span>}
          </div>
          <div className="sidebar-footer-row">
            <button className="ghost sm" onClick={logout}>
              <LogOut aria-hidden /> {t("common.signOut")}
            </button>
            <button
              className="ghost sm icon-only"
              onClick={() => setPref(theme === "dark" ? "light" : "dark")}
              title={theme === "dark" ? t("common.lightMode") : t("common.darkMode")}
              aria-label={theme === "dark" ? t("common.lightMode") : t("common.darkMode")}
            >
              {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
            </button>
          </div>
        </div>
      </aside>
      <motion.main
        className="main"
        key={location.pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
      >
        <Outlet />
      </motion.main>
    </div>
  );
}

export function ScoreRing({ score, threshold, low, high }: { score: number; threshold?: number; low?: number | null; high?: number | null }) {
  const { t } = useT();
  const pct = Math.round(score * 100);
  const strong = threshold === undefined ? pct >= 80 : score >= threshold;
  const hasRange =
    low != null && high != null && (Math.round(low * 100) !== pct || Math.round(high * 100) !== pct);
  return (
    <div className="score-ring">
      <div className="score-big" style={{ color: strong ? "var(--ok)" : "var(--warn)" }}>
        {pct}%
      </div>
      <div>
        <span className={`badge ${strong ? "strong" : "moderate"}`}>
          {strong ? t("score.strong") : t("score.moderate")}
        </span>
        {hasRange && (
          <div className="small muted mt">
            {t("score.possibleRange", { low: Math.round(low * 100), high: Math.round(high * 100) })}
          </div>
        )}
        {threshold !== undefined && (
          <div className="small muted mt">{t("score.threshold", { pct: Math.round(threshold * 100) })}</div>
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
  const { t } = useT();
  return (
    <div className="progress-bar-wrap">
      {label ? <div className="small muted mb">{label}</div> : null}
      <div className="progress-bar" role="progressbar" aria-busy="true" aria-label={label || t("common.working")}>
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

export function Empty({ children, icon: Icon }: { children: React.ReactNode; icon?: LucideIcon }) {
  return (
    <div className="empty">
      {Icon ? <Icon aria-hidden /> : null}
      <div>{children}</div>
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="alert error">{error}</div>;
}

export function Spinner() {
  return <span className="spinner" />;
}

export { Link };
