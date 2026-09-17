import { useEffect, useMemo, useState } from "react";
import { matchPath, useLocation } from "react-router-dom";
import { api } from "../../api/client";
import type { AppDocument, Application, Job } from "../../api/types";
import { dateLocale, formatDate } from "../../lib/i18n";

export type PageCoachSource = "job" | "application" | "document" | "career" | "none";

export type PageCoachContext = {
  source: PageCoachSource;
  jobId: string;
  applicationId: string;
  title: string;
  organization: string;
  status: string;
  loading: boolean;
};

export type CoachSelection = {
  jobId: string;
  applicationId: string;
};

export const EMPTY_SELECTION: CoachSelection = { jobId: "", applicationId: "" };

export const OPEN_COACH_EVENT = "ac-open-coach";

export function openCoachWidget() {
  window.dispatchEvent(new Event(OPEN_COACH_EVENT));
}

export function selectionKey(sel: CoachSelection) {
  return `${sel.applicationId || ""}:${sel.jobId || ""}`;
}

export function isGeneralSelection(sel: CoachSelection) {
  return !sel.jobId && !sel.applicationId;
}

export function pageSelection(ctx: PageCoachContext): CoachSelection {
  return { jobId: ctx.jobId, applicationId: ctx.applicationId };
}

const EMPTY_PAGE: PageCoachContext = {
  source: "none",
  jobId: "",
  applicationId: "",
  title: "",
  organization: "",
  status: "",
  loading: false,
};

export function usePageCoachContext(): PageCoachContext {
  const { pathname } = useLocation();
  const [ctx, setCtx] = useState<PageCoachContext>({ ...EMPTY_PAGE, loading: true });

  useEffect(() => {
    const jobMatch = matchPath("/jobs/:id", pathname);
    const appMatch = matchPath("/applications/:id", pathname);
    const docMatch = matchPath("/documents/:id", pathname);
    let cancelled = false;

    const fail = () => {
      if (!cancelled) setCtx(EMPTY_PAGE);
    };

    if (jobMatch?.params.id) {
      setCtx((prev) => ({ ...prev, loading: true, source: "job" }));
      api.get<Job>(`/api/jobs/${jobMatch.params.id}`).then((job) => {
        if (cancelled) return;
        setCtx({
          source: "job",
          jobId: job.id,
          applicationId: "",
          title: job.position_title || "",
          organization: job.organization_name || "",
          status: job.status || "",
          loading: false,
        });
      }).catch(fail);
      return () => { cancelled = true; };
    }

    if (appMatch?.params.id) {
      setCtx((prev) => ({ ...prev, loading: true, source: "application" }));
      api.get<Application>(`/api/applications/${appMatch.params.id}`).then((app) => {
        if (cancelled) return;
        setCtx({
          source: "application",
          jobId: app.job_id || "",
          applicationId: app.id,
          title: app.job?.position_title || "",
          organization: app.job?.organization_name || "",
          status: app.status || "",
          loading: false,
        });
      }).catch(fail);
      return () => { cancelled = true; };
    }

    if (docMatch?.params.id) {
      setCtx((prev) => ({ ...prev, loading: true, source: "document" }));
      api.get<AppDocument>(`/api/documents/${docMatch.params.id}`).then((doc) => {
        if (cancelled) return;
        setCtx({
          source: "document",
          jobId: doc.job?.id || "",
          applicationId: doc.application_id || "",
          title: doc.job?.position_title || doc.title || "",
          organization: doc.job?.organization_name || "",
          status: doc.document_type || "",
          loading: false,
        });
      }).catch(fail);
      return () => { cancelled = true; };
    }

    if (pathname === "/career" || pathname.startsWith("/career/")) {
      setCtx({ ...EMPTY_PAGE, source: "career", loading: false });
      return;
    }

    setCtx(EMPTY_PAGE);
    return () => { cancelled = true; };
  }, [pathname]);

  return ctx;
}

export function jobLabel(job: Pick<Job, "position_title" | "organization_name"> | null | undefined, untitled: string, unknownOrg: string) {
  const title = job?.position_title?.trim() || untitled;
  const org = job?.organization_name?.trim();
  return org ? `${title} · ${org}` : title === untitled && !org ? unknownOrg : title;
}

export function appLabel(app: Application, untitled: string, unknownOrg: string) {
  return jobLabel(app.job, untitled, unknownOrg);
}

export function formatRelativeTime(iso: string | null | undefined) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffSec = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(dateLocale(), { numeric: "auto" });
  if (abs < 60) return rtf.format(diffSec, "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(diffSec / 86400), "day");
  return formatDate(date, { month: "short", day: "numeric" });
}

export function filterText(query: string, ...parts: Array<string | null | undefined>) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return parts.some((part) => (part || "").toLowerCase().includes(q));
}

export function useResolvedSelection(
  selection: CoachSelection,
  jobs: Job[] | null,
  apps: Application[] | null,
  page: PageCoachContext,
) {
  return useMemo(() => {
    if (selection.applicationId) {
      const app = (apps || []).find((row) => row.id === selection.applicationId);
      if (app) {
        return {
          kind: "application" as const,
          title: app.job?.position_title || "",
          organization: app.job?.organization_name || "",
          status: app.status,
        };
      }
      if (page.applicationId === selection.applicationId) {
        return {
          kind: "application" as const,
          title: page.title,
          organization: page.organization,
          status: page.status,
        };
      }
      return { kind: "application" as const, title: "", organization: "", status: "" };
    }
    if (selection.jobId) {
      const job = (jobs || []).find((row) => row.id === selection.jobId);
      if (job) {
        return {
          kind: "job" as const,
          title: job.position_title || "",
          organization: job.organization_name || "",
          status: job.status,
        };
      }
      if (page.jobId === selection.jobId) {
        return {
          kind: "job" as const,
          title: page.title,
          organization: page.organization,
          status: page.status,
        };
      }
      return { kind: "job" as const, title: "", organization: "", status: "" };
    }
    return { kind: "general" as const, title: "", organization: "", status: "" };
  }, [selection, jobs, apps, page]);
}
