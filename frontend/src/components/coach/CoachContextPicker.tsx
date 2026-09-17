import { useEffect, useMemo, useRef, useState } from "react";
import { Briefcase, Check, FileStack, Globe, Search, Sparkles } from "lucide-react";
import type { Application, Job } from "../../api/types";
import { useT } from "../../lib/i18n";
import {
  type CoachSelection,
  type PageCoachContext,
  appLabel,
  filterText,
  isGeneralSelection,
  jobLabel,
  pageSelection,
  selectionKey,
  useResolvedSelection,
} from "./coachContext";

type Props = {
  compact?: boolean;
  selection: CoachSelection;
  followPage: boolean;
  page: PageCoachContext;
  jobs: Job[] | null;
  apps: Application[] | null;
  onSelect: (selection: CoachSelection, followPage: boolean) => void;
};

export default function CoachContextPicker({ compact, selection, followPage, page, jobs, apps, onSelect }: Props) {
  const { t, lang } = useT();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const resolved = useResolvedSelection(selection, jobs, apps, page);
  const pageSel = pageSelection(page);
  const pageHasEntity = !!(page.jobId || page.applicationId);
  const pageDiffers = pageHasEntity && selectionKey(pageSel) !== selectionKey(selection);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      window.setTimeout(() => searchRef.current?.focus(), 20);
    }
  }, [open]);

  const untitled = t("common.untitledRole");
  const unknownOrg = t("common.unknownOrg");

  const options = useMemo(() => {
    const rows: Array<{
      key: string;
      kind: "page" | "general" | "application" | "job";
      selection: CoachSelection;
      followPage: boolean;
      title: string;
      subtitle: string;
      search: string;
    }> = [];

    if (pageHasEntity) {
      rows.push({
        key: `page:${selectionKey(pageSel)}`,
        kind: "page",
        selection: pageSel,
        followPage: true,
        title: page.title || untitled,
        subtitle: [page.organization, t("coach.followingPage")].filter(Boolean).join(" · "),
        search: `${page.title} ${page.organization} ${page.status}`,
      });
    }

    rows.push({
      key: "general",
      kind: "general",
      selection: { jobId: "", applicationId: "" },
      followPage: false,
      title: t("coach.generalTitle"),
      subtitle: t("coach.generalHint"),
      search: `${t("coach.generalTitle")} ${t("coach.noContext")}`,
    });

    for (const app of apps || []) {
      const label = appLabel(app, untitled, unknownOrg);
      rows.push({
        key: `app:${app.id}`,
        kind: "application",
        selection: { jobId: app.job_id || "", applicationId: app.id },
        followPage: false,
        title: label,
        subtitle: [t("coach.appsGroup"), app.status ? t(`status.${app.status}`) : ""].filter(Boolean).join(" · "),
        search: `${label} ${app.status} ${app.job?.location || ""}`,
      });
    }

    for (const job of jobs || []) {
      const label = jobLabel(job, untitled, unknownOrg);
      rows.push({
        key: `job:${job.id}`,
        kind: "job",
        selection: { jobId: job.id, applicationId: "" },
        followPage: false,
        title: label,
        subtitle: [t("coach.jobsGroup"), job.location, job.status ? t(`status.${job.status}`) : ""].filter(Boolean).join(" · "),
        search: `${label} ${job.location} ${job.status} ${job.department}`,
      });
    }

    return rows.filter((row) => filterText(query, row.search, row.title, row.subtitle));
  }, [apps, jobs, lang, page, pageHasEntity, pageSel, query, t, untitled, unknownOrg]);

  const title = resolved.kind === "general"
    ? t("coach.generalTitle")
    : jobLabel({ position_title: resolved.title, organization_name: resolved.organization }, untitled, unknownOrg);

  const hint = resolved.kind === "application"
    ? t("coach.appHint")
    : resolved.kind === "job"
      ? t("coach.jobHint")
      : page.source === "career"
        ? t("coach.careerPageHint")
        : t("coach.generalHint");

  const Icon = resolved.kind === "application" ? FileStack : resolved.kind === "job" ? Briefcase : Globe;

  const pick = (sel: CoachSelection, nextFollow: boolean) => {
    onSelect(sel, nextFollow);
    setOpen(false);
  };

  return (
    <div className={`coach-context${compact ? " compact" : ""}`} ref={wrapRef}>
      <div className="coach-context-card">
        <div className="coach-context-icon" aria-hidden>
          <Icon />
        </div>
        <div className="coach-context-copy">
          <div className="coach-context-kicker">
            {followPage && pageHasEntity ? t("coach.followingPage") : t("coach.context")}
          </div>
          <div className="coach-context-title">{title}</div>
          {!compact && <p className="coach-context-hint">{followPage && pageHasEntity ? t("coach.pageHint") : hint}</p>}
        </div>
        <div className="coach-context-actions">
          {!isGeneralSelection(selection) && (
            <button type="button" className="sm ghost" onClick={() => pick({ jobId: "", applicationId: "" }, false)}>
              {t("coach.chatGenerally")}
            </button>
          )}
          <button
            type="button"
            className="sm"
            aria-expanded={open}
            aria-haspopup="listbox"
            onClick={() => setOpen((v) => !v)}
          >
            <Search aria-hidden /> {t("coach.changeContext")}
          </button>
        </div>
      </div>

      {pageDiffers && !open && (
        <div className="coach-context-banner">
          <Sparkles aria-hidden />
          <span>{t("coach.pageContextBanner", { title: page.title || untitled })}</span>
          <button type="button" className="sm primary" onClick={() => pick(pageSel, true)}>
            {t("coach.useThisPage")}
          </button>
        </div>
      )}

      {open && (
        <div className="coach-context-pop" role="listbox" aria-label={t("coach.contextAria")}>
          <div className="coach-context-search">
            <Search aria-hidden />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("coach.searchContext")}
              aria-label={t("coach.searchContext")}
            />
          </div>
          <div className="coach-context-list">
            {!options.length && <div className="coach-context-empty">{t("coach.noMatch")}</div>}
            {options.map((row) => {
              const sameSel = selectionKey(row.selection) === selectionKey(selection);
              const active = row.kind === "page"
                ? followPage && pageHasEntity
                : row.kind === "general"
                  ? isGeneralSelection(selection) && !(followPage && pageHasEntity)
                  : !followPage && sameSel;
              const RowIcon = row.kind === "page" ? Sparkles : row.kind === "application" ? FileStack : row.kind === "job" ? Briefcase : Globe;
              return (
                <button
                  key={row.key}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`coach-context-option${active ? " active" : ""}`}
                  onClick={() => pick(row.selection, row.followPage)}
                >
                  <RowIcon aria-hidden />
                  <span>
                    <span className="coach-context-option-title">{row.title}</span>
                    <span className="coach-context-option-sub">{row.subtitle}</span>
                  </span>
                  {active ? <Check aria-hidden /> : null}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
