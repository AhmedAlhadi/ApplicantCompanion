import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Briefcase,
  Cpu,
  FileStack,
  Files,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  Settings as SettingsIcon,
  Shield,
  Sun,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { api, getToken, setToken, workflowEventsUrl } from "../api/client";
import type { User, WorkflowRun } from "../api/types";
import { useT } from "../lib/i18n";
import { useTheme } from "../lib/theme";

export function Brand() {
  const { t } = useT();
  return (
    <div className="brand">
      <span>{t("common.appName")}</span>
    </div>
  );
}

type NavItem = { to: string; end?: boolean; icon: LucideIcon };

const NAV: NavItem[] = [
  { to: "/", end: true, icon: LayoutDashboard },
  { to: "/career", icon: Network },
  { to: "/jobs", icon: Briefcase },
  { to: "/applications", icon: FileStack },
  { to: "/documents", icon: Files },
];

function isNavActive(item: NavItem, pathname: string) {
  const url = new URL(item.to, "http://local");
  if (item.end) return pathname === url.pathname;
  return pathname === url.pathname || (url.pathname !== "/" && pathname.startsWith(`${url.pathname}/`));
}

function userInitials(user: User) {
  const name = user.full_name.trim();
  if (name) {
    const parts = name.split(/\s+/);
    return `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}`.toUpperCase() || "?";
  }
  return (user.email[0] || "?").toUpperCase();
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
  const [navOpen, setNavOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

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
  };

  useEffect(() => {
    setNavOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setNavOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className={`app-shell${navOpen ? " nav-open" : ""}`}>
      {navOpen && <button type="button" className="sidebar-backdrop" aria-label={t("nav.closeNav")} onClick={() => setNavOpen(false)} />}
      <aside className="sidebar">
        <Brand />
        <nav>
          {NAV.map((item) => {
            const parentActive = isNavActive(item, location.pathname);
            const Icon = item.icon;
            return (
              <div key={item.to} className="nav-group">
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={() => (parentActive ? "active" : "")}
                  onClick={() => setNavOpen(false)}
                >
                  <Icon className="nav-icon" aria-hidden />
                  {navLabels[item.to] ?? item.to}
                </NavLink>
              </div>
            );
          })}
        </nav>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button
            type="button"
            className="ghost icon-only hamburger"
            onClick={() => setNavOpen((open) => !open)}
            aria-label={navOpen ? t("nav.closeNav") : t("nav.openNav")}
          >
            {navOpen ? <X aria-hidden /> : <Menu aria-hidden />}
          </button>
          <div className="topbar-spacer" />
          <div className="avatar-wrap" ref={menuRef}>
            <button
              type="button"
              className="avatar-btn"
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={t("nav.accountMenu")}
            >
              {user.avatar_url ? (
                <img src={user.avatar_url} alt="" className="avatar-img" referrerPolicy="no-referrer" />
              ) : (
                <span className="avatar-initials">{userInitials(user)}</span>
              )}
            </button>
            {menuOpen && (
              <div className="avatar-menu" role="menu">
                <div className="avatar-menu-user">
                  <div className="sidebar-user-name">{user.full_name || user.email}</div>
                  <div className="sidebar-user-meta">{user.email}</div>
                  {user.is_admin && <span className="badge needs_review">{t("common.admin")}</span>}
                </div>
                <Link to="/settings" role="menuitem" onClick={() => setMenuOpen(false)}>
                  <SettingsIcon aria-hidden /> {t("nav.settings")}
                </Link>
                <Link to="/ai-config" role="menuitem" onClick={() => setMenuOpen(false)}>
                  <Cpu aria-hidden /> {t("nav.aiConfig")}
                </Link>
                {user.is_admin && (
                  <>
                    <Link to="/admin" role="menuitem" onClick={() => setMenuOpen(false)}>
                      <Shield aria-hidden /> {t("nav.admin")}
                    </Link>
                    <Link to="/admin/users" role="menuitem" onClick={() => setMenuOpen(false)}>
                      <Users aria-hidden /> {t("nav.users")}
                    </Link>
                  </>
                )}
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => setPref(theme === "dark" ? "light" : "dark")}
                >
                  {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
                  {theme === "dark" ? t("common.lightMode") : t("common.darkMode")}
                </button>
                <button type="button" role="menuitem" onClick={logout}>
                  <LogOut aria-hidden /> {t("common.signOut")}
                </button>
              </div>
            )}
          </div>
        </header>
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
