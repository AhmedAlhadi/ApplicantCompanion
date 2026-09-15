import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, FileSearch, FileText, PartyPopper, RefreshCw, Sparkles, Upload, User as UserIcon } from "lucide-react";
import { api } from "../api/client";
import ThinkingProgress, { THINKING_PHRASES } from "../components/ThinkingProgress";
import type {
  AppDocument,
  CareerProfile,
  IngestResult,
  Job,
  JobScore,
  OnboardingStatus,
  PendingIngestion,
  User,
  WorkflowRun,
} from "../api/types";
import { Brand, ErrorBox, ScoreRing, Spinner, useWorkflow } from "../components/ui";
import { useT } from "../lib/i18n";

type Step = "welcome" | "career" | "profile" | "job" | "working" | "done";

const STEP_KEYS: Step[] = ["welcome", "career", "profile", "job", "working", "done"];

function enterWorkspace() {
  window.location.assign("/");
}

async function acceptPending(pendingId: string) {
  await api.post(`/api/career/pending-ingestions/${pendingId}/accept-suggested`);
}

async function acceptAllPending() {
  const pending = await api.get<PendingIngestion[]>("/api/career/pending-ingestions?status_filter=pending");
  for (const row of pending) {
    await acceptPending(row.id);
  }
  return pending.length;
}

export default function Onboarding({ user }: { user: User }) {
  const { t } = useT();
  const [step, setStep] = useState<Step>("welcome");
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [skipping, setSkipping] = useState(false);

  const [jobId, setJobId] = useState<string | null>(null);
  const [appId, setAppId] = useState<string | null>(null);
  const [analyzeRunId, setAnalyzeRunId] = useState<string | null>(null);
  const [generateRunId, setGenerateRunId] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineHint, setPipelineHint] = useState("");
  const [summary, setSummary] = useState<{
    score: JobScore | null;
    experienceCount: number;
    hasStrategy: boolean;
    hasCv: boolean;
    hasCoverLetter: boolean;
    organization: string;
    title: string;
  } | null>(null);

  const analysisHandled = useRef(false);
  const generationHandled = useRef(false);

  const analyzeWorkflow = useWorkflow(
    analyzeRunId,
    jobId && (analyzeRunId || step === "working") && !generateRunId ? `/api/jobs/${jobId}/workflow` : null,
  );
  const generateWorkflow = useWorkflow(
    generateRunId,
    appId && generateRunId ? `/api/applications/${appId}/workflow` : null,
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const initial = await api.get<OnboardingStatus>("/api/onboarding");
        if (cancelled) return;
        let current = initial;
        if (current.pending_count > 0) {
          await acceptAllPending();
          current = await api.get<OnboardingStatus>("/api/onboarding");
        }
        if (cancelled) return;
        setStatus(current);
        await resumeFromStatus(current);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load onboarding");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resumeFromStatus = async (current: OnboardingStatus) => {
    if (current.latest_job?.status === "analyzing") {
      setJobId(current.latest_job.id);
      setPipelineHint("Analyzing the job ad…");
      setStep("working");
      return;
    }

    if (current.latest_application && current.latest_job?.status === "analyzed") {
      const docs = await api.get<AppDocument[]>(`/api/applications/${current.latest_application.id}/documents`);
      const types = new Set(docs.filter((d) => d.current_version).map((d) => d.document_type));
      setJobId(current.latest_job.id);
      setAppId(current.latest_application.id);
      if (types.has("cv") && types.has("cover_letter")) {
        await loadSummary(current.latest_job.id, current.latest_application.id);
        setStep("done");
        return;
      }
      setPipelineHint("Generating your strategy, resume, and cover letter…");
      setStep("working");
      await startGeneration(current.latest_application.id);
      return;
    }

    if (current.latest_job?.status === "analyzed" && !current.latest_application) {
      setJobId(current.latest_job.id);
      setPipelineHint("Creating your application…");
      setStep("working");
      await afterAnalysis(current.latest_job.id);
      return;
    }

    if (!current.has_profile && current.experience_count > 0) {
      setStep("profile");
      return;
    }
    if (current.experience_count === 0) {
      setStep(current.has_profile ? "career" : "welcome");
      return;
    }
    if (current.job_count === 0) {
      setStep(current.has_profile ? "job" : "profile");
      return;
    }
    setStep("welcome");
  };

  const afterAnalysis = async (resolvedJobId: string) => {
    if (analysisHandled.current) return;
    analysisHandled.current = true;
    try {
      setPipelineHint("Creating your application and generating documents…");
      const app = await api.post<{ id: string }>("/api/applications", { job_id: resolvedJobId });
      setAppId(app.id);
      await api.post(`/api/applications/${app.id}/decide`, { decision: "continue" });
      await startGeneration(app.id);
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "Could not start document generation");
    }
  };

  const startGeneration = async (resolvedAppId: string) => {
    const docs = await api.get<AppDocument[]>(`/api/applications/${resolvedAppId}/documents`);
    const types = new Set(docs.filter((d) => d.current_version).map((d) => d.document_type));
    if (types.has("cv") && types.has("cover_letter")) {
      if (jobId) await loadSummary(jobId, resolvedAppId);
      setStep("done");
      return;
    }
    generationHandled.current = false;
    const accepted = await api.post<{ workflow_run_id: string }>(`/api/applications/${resolvedAppId}/generate-all`, {});
    setGenerateRunId(accepted.workflow_run_id);
    setPipelineHint("Generating your strategy, resume, and cover letter…");
  };

  const loadSummary = async (resolvedJobId: string, resolvedAppId: string) => {
    const [score, docs, experiences, job] = await Promise.all([
      api.get<JobScore>(`/api/jobs/${resolvedJobId}/score`).catch(() => null),
      api.get<AppDocument[]>(`/api/applications/${resolvedAppId}/documents`).catch(() => []),
      api.get<{ id: string }[]>("/api/career/experiences").catch(() => []),
      api.get<Job>(`/api/jobs/${resolvedJobId}`).catch(() => null),
    ]);
    const types = new Set((docs || []).filter((d) => d.current_version).map((d) => d.document_type));
    setSummary({
      score,
      experienceCount: experiences?.length ?? 0,
      hasStrategy: true,
      hasCv: types.has("cv"),
      hasCoverLetter: types.has("cover_letter"),
      organization: job?.organization_name || "",
      title: job?.position_title || "",
    });
  };

  useEffect(() => {
    if (step !== "working" || generateRunId) return;
    if (analyzeWorkflow?.status === "COMPLETED" && jobId) {
      void afterAnalysis(jobId);
    } else if (analyzeWorkflow?.status === "FAILED") {
      setPipelineError(analyzeWorkflow.error || "Job analysis failed");
    }
  }, [analyzeWorkflow?.status, generateRunId, jobId, step]);

  useEffect(() => {
    if (step !== "working" || !appId || !jobId) return;
    if (generateWorkflow?.status === "COMPLETED") {
      if (generationHandled.current) return;
      generationHandled.current = true;
      void (async () => {
        await loadSummary(jobId, appId);
        setStep("done");
      })();
    } else if (generateWorkflow?.status === "FAILED") {
      setPipelineError(generateWorkflow.error || "Document generation failed");
    }
  }, [generateWorkflow?.status, appId, jobId, step]);

  const skip = async () => {
    setSkipping(true);
    setError(null);
    try {
      await api.post("/api/onboarding/skip");
      enterWorkspace();
    } catch (err) {
      setSkipping(false);
      setError(err instanceof Error ? err.message : "Could not skip onboarding");
    }
  };

  const finish = async () => {
    setError(null);
    try {
      await api.post("/api/onboarding/complete");
      enterWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish onboarding");
    }
  };

  const retryPipeline = async () => {
    if (!jobId) return;
    setPipelineError(null);
    analysisHandled.current = false;
    generationHandled.current = false;
    setGenerateRunId(null);
    try {
      const job = await api.get<Job>(`/api/jobs/${jobId}`);
      if (job.status !== "analyzed") {
        const accepted = await api.post<{ workflow_run_id: string }>(`/api/jobs/${jobId}/analyze`, {
          include_research: true,
        });
        setAnalyzeRunId(accepted.workflow_run_id);
        setPipelineHint("Analyzing the job ad…");
        return;
      }
      if (appId) {
        await startGeneration(appId);
        return;
      }
      await afterAnalysis(jobId);
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "Retry failed");
    }
  };

  if (!ready) {
    return (
      <div className="onboard-wrap">
        <p className="muted">{t("common.loading")}</p>
      </div>
    );
  }

  const stepIndex = STEP_KEYS.indexOf(step);
  const canSkip = step !== "working" && step !== "done";

  return (
    <div className="onboard-wrap">
      <Brand />
      <div className="onboard-steps" aria-label="Onboarding progress">
        {STEP_KEYS.map((key, i) => (
          <div
            key={key}
            className={`onboard-step ${i === stepIndex ? "active" : ""} ${i < stepIndex ? "done" : ""}`}
          >
            <span className="onboard-step-dot">{i < stepIndex ? <Check aria-hidden /> : i + 1}</span>
            <span>{t(`onboarding.steps.${key}`)}</span>
          </div>
        ))}
      </div>
      <ErrorBox error={error} />

      {step === "welcome" && <WelcomeStep onContinue={() => setStep("career")} />}
      {step === "career" && (
        <CareerStep
          onDone={async () => {
            const next = await api.get<OnboardingStatus>("/api/onboarding");
            setStatus(next);
            setStep("profile");
          }}
        />
      )}
      {step === "profile" && (
        <ProfileStep
          user={user}
          initial={status?.profile}
          onDone={async () => {
            const next = await api.get<OnboardingStatus>("/api/onboarding");
            setStatus(next);
            setStep("job");
          }}
        />
      )}
      {step === "job" && (
        <JobStep
          onCreated={async (id, runId) => {
            analysisHandled.current = false;
            generationHandled.current = false;
            setJobId(id);
            setAnalyzeRunId(runId);
            setGenerateRunId(null);
            setPipelineError(null);
            setPipelineHint(t("onboarding.analyzingHint"));
            setStep("working");
          }}
        />
      )}
      {step === "working" && (
        <WorkingStep
          hint={pipelineHint}
          analyzeWorkflow={analyzeWorkflow}
          generateWorkflow={generateWorkflow}
          error={pipelineError}
          onRetry={retryPipeline}
        />
      )}
      {step === "done" && (
        <DoneStep
          summary={summary}
          applicationId={appId}
          onEnter={finish}
        />
      )}

      {canSkip && (
        <p className="small muted onboard-skip">
          <button className="ghost sm" onClick={skip} disabled={skipping}>
            {skipping ? t("common.skipping") : t("common.skip")}
          </button>
          {t("onboarding.skipLater")}
        </p>
      )}
    </div>
  );
}

function WelcomeStep({ onContinue }: { onContinue: () => void }) {
  const { t } = useT();
  return (
    <div className="panel">
      <h1 className="page-title"><Sparkles className="page-title-icon" aria-hidden /> {t("onboarding.welcomeTitle")}</h1>
      <p className="page-sub">{t("onboarding.welcomeSub")}</p>
      <ol className="onboard-list">
        <li>{t("onboarding.welcome1")}</li>
        <li>{t("onboarding.welcome2")}</li>
        <li>{t("onboarding.welcome3")}</li>
        <li>{t("onboarding.welcome4")}</li>
      </ol>
      <button className="primary mt" onClick={onContinue}>{t("onboarding.getStarted")} <ArrowRight aria-hidden /></button>
    </div>
  );
}

function CareerStep({ onDone }: { onDone: () => Promise<void> }) {
  const { t } = useT();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const finishIngest = async (result: IngestResult) => {
    if (result.pending_ingestion_id) {
      await acceptPending(result.pending_ingestion_id);
    }
    const applied = result.auto_applied || result.created || {};
    const bits = Object.entries(applied)
      .filter(([, v]) => typeof v === "number" && v > 0)
      .map(([k, v]) => `${k}: ${v}`);
    setNote(bits.length ? t("onboarding.extracted", { bits: bits.join(" · ") }) : t("onboarding.stored"));
    await onDone();
  };

  const ingestText = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<IngestResult>("/api/career/ingest-text", { text, doc_type: "cv" });
      await finishIngest(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.extractFailed"));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("doc_type", "cv");
      const doc = await api.upload<{ id: string }>("/api/career/documents", fd);
      const result = await api.post<IngestResult>(`/api/career/documents/${doc.id}/ingest`);
      await finishIngest(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.uploadFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h1 className="page-title"><Upload className="page-title-icon" aria-hidden /> {t("onboarding.careerTitle")}</h1>
      <p className="page-sub">{t("onboarding.careerSub")}</p>
      <label>{t("onboarding.uploadCv")}</label>
      <input type="file" accept=".pdf,.docx,.txt,.md" onChange={upload} disabled={busy} />
      <label>{t("onboarding.orPaste")}</label>
      <textarea
        rows={10}
        placeholder={t("onboarding.pastePlaceholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
      />
      <ErrorBox error={error} />
      {note && <div className="alert ok">{note}</div>}
      {busy ? (
        <ThinkingProgress phrases={THINKING_PHRASES.cvIngest} icon={FileSearch} />
      ) : (
        <button className="primary mt" onClick={ingestText} disabled={!text.trim()}>
          <Sparkles aria-hidden /> {t("onboarding.extractPasted")}
        </button>
      )}
    </div>
  );
}

function ProfileStep({
  user,
  initial,
  onDone,
}: {
  user: User;
  initial: OnboardingStatus["profile"] | null | undefined;
  onDone: () => Promise<void>;
}) {
  const { t } = useT();
  const [form, setForm] = useState({
    full_name: initial?.full_name || user.full_name || "",
    headline: initial?.headline || "",
    summary: initial?.summary || "",
    email: initial?.email || user.email || "",
    phone: initial?.phone || "",
    location: initial?.location || "",
    linkedin: initial?.links?.linkedin || "",
  });
  const extras = useRef({ preferred_positioning: "", career_narratives: [] as CareerProfile["career_narratives"] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.get<CareerProfile | null>("/api/career/profile").then((profile) => {
      if (cancelled || !profile) return;
      extras.current = {
        preferred_positioning: profile.preferred_positioning || "",
        career_narratives: profile.career_narratives || [],
      };
      setForm((prev) => ({
        full_name: profile.full_name || prev.full_name,
        headline: profile.headline || prev.headline,
        summary: profile.summary || prev.summary,
        email: profile.email || prev.email,
        phone: profile.phone || prev.phone,
        location: profile.location || prev.location,
        linkedin: profile.links?.linkedin || prev.linkedin,
      }));
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim()) {
      setError(t("onboarding.fullNameRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.put("/api/career/profile", {
        full_name: form.full_name.trim(),
        headline: form.headline,
        summary: form.summary,
        email: form.email,
        phone: form.phone,
        location: form.location,
        links: { ...(initial?.links || {}), linkedin: form.linkedin },
        preferred_positioning: extras.current.preferred_positioning,
        career_narratives: extras.current.career_narratives,
      });
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.saveProfileFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={save}>
      <h1 className="page-title"><UserIcon className="page-title-icon" aria-hidden /> {t("onboarding.profileTitle")}</h1>
      <p className="page-sub">{t("onboarding.profileSub")}</p>
      <div className="form-row">
        <div>
          <label>{t("login.fullName")} *</label>
          <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required />
        </div>
        <div>
          <label>{t("onboarding.headline")}</label>
          <input value={form.headline} onChange={(e) => set("headline", e.target.value)} placeholder={t("onboarding.headlinePh")} />
        </div>
      </div>
      <label>{t("onboarding.summary")}</label>
      <textarea value={form.summary} onChange={(e) => set("summary", e.target.value)} />
      <div className="form-row">
        <div>
          <label>{t("onboarding.email")}</label>
          <input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </div>
        <div>
          <label>{t("onboarding.phone")}</label>
          <input value={form.phone} onChange={(e) => set("phone", e.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <div>
          <label>{t("onboarding.location")}</label>
          <input value={form.location} onChange={(e) => set("location", e.target.value)} />
        </div>
        <div>
          <label>{t("onboarding.linkedin")}</label>
          <input value={form.linkedin} onChange={(e) => set("linkedin", e.target.value)} />
        </div>
      </div>
      <ErrorBox error={error} />
      <button className="primary mt" disabled={busy}>
        {busy ? <><Spinner /> {t("common.saving")}</> : <>{t("common.continue")} <ArrowRight aria-hidden /></>}
      </button>
    </form>
  );
}

function JobStep({ onCreated }: { onCreated: (jobId: string, runId: string) => Promise<void> }) {
  const { t } = useT();
  const [form, setForm] = useState({
    raw_jd_text: "",
    organization_name: "",
    position_title: "",
    source_url: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.raw_jd_text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const job = await api.post<Job>("/api/jobs", {
        raw_jd_text: form.raw_jd_text,
        organization_name: form.organization_name,
        position_title: form.position_title,
        source_url: form.source_url,
        source_type: "paste",
      });
      const accepted = await api.post<{ workflow_run_id: string }>(`/api/jobs/${job.id}/analyze`, {
        include_research: true,
      });
      await onCreated(job.id, accepted.workflow_run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.analyzeFailed"));
      setBusy(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h1 className="page-title"><FileText className="page-title-icon" aria-hidden /> {t("onboarding.jobTitle")}</h1>
      <p className="page-sub">{t("onboarding.jobSub")}</p>
      <label>{t("onboarding.jd")}</label>
      <textarea
        rows={10}
        placeholder={t("onboarding.jdPh")}
        value={form.raw_jd_text}
        onChange={(e) => setForm({ ...form, raw_jd_text: e.target.value })}
        required
      />
      <div className="form-row">
        <div>
          <label>{t("onboarding.organization")}</label>
          <input
            value={form.organization_name}
            onChange={(e) => setForm({ ...form, organization_name: e.target.value })}
            placeholder={t("onboarding.detectedIfEmpty")}
          />
        </div>
        <div>
          <label>{t("onboarding.position")}</label>
          <input
            value={form.position_title}
            onChange={(e) => setForm({ ...form, position_title: e.target.value })}
            placeholder={t("onboarding.detectedIfEmpty")}
          />
        </div>
      </div>
      <label>{t("onboarding.sourceUrl")}</label>
      <input
        value={form.source_url}
        onChange={(e) => setForm({ ...form, source_url: e.target.value })}
        placeholder="Optional"
      />
      <ErrorBox error={error} />
      <button className="primary mt" disabled={busy || !form.raw_jd_text.trim()}>
        {busy ? <><Spinner /> {t("onboarding.starting")}</> : <><Sparkles aria-hidden /> {t("onboarding.analyzeGenerate")}</>}
      </button>
    </form>
  );
}

function WorkingStep({
  hint,
  analyzeWorkflow,
  generateWorkflow,
  error,
  onRetry,
}: {
  hint: string;
  analyzeWorkflow: WorkflowRun | null;
  generateWorkflow: WorkflowRun | null;
  error: string | null;
  onRetry: () => void;
}) {
  const { t } = useT();
  const workflow = generateWorkflow ?? analyzeWorkflow;
  return (
    <div className="panel">
      <h1 className="page-title">{t("onboarding.workingTitle")}</h1>
      <p className="page-sub">{hint}</p>
      {!error && (
        <ThinkingProgress
          phrases={generateWorkflow ? THINKING_PHRASES.docGeneration : THINKING_PHRASES.jobAnalysis}
          workflow={workflow}
        />
      )}
      <ErrorBox error={error} />
      {error && (
        <button className="primary mt" onClick={onRetry}><RefreshCw aria-hidden /> {t("common.retry")}</button>
      )}
    </div>
  );
}

function DoneStep({
  summary,
  applicationId,
  onEnter,
}: {
  summary: {
    score: JobScore | null;
    experienceCount: number;
    hasStrategy: boolean;
    hasCv: boolean;
    hasCoverLetter: boolean;
    organization: string;
    title: string;
  } | null;
  applicationId: string | null;
  onEnter: () => void;
}) {
  const { t } = useT();
  const score = summary?.score;
  const below = !!score && score.overall_score < score.threshold;
  return (
    <div className="panel">
      <h1 className="page-title"><PartyPopper className="page-title-icon" aria-hidden /> {t("onboarding.doneTitle")}</h1>
      <p className="page-sub">
        {summary?.organization
          ? t("onboarding.doneSubAt", { title: summary.title || t("common.untitledRole"), org: summary.organization })
          : t("onboarding.doneSub", { title: summary?.title || t("common.untitledRole") })}
      </p>
      {score && (
        <div className="mt">
          <ScoreRing score={score.overall_score} threshold={score.threshold} low={score.overall_score_low} high={score.overall_score_high} />
        </div>
      )}
      {below && (
        <div className="alert warn">
          {t("onboarding.belowThreshold")}
        </div>
      )}
      <ul className="onboard-list">
        <li>{(summary?.experienceCount ?? 0) === 1 ? t("onboarding.experiencesStored", { n: summary?.experienceCount ?? 0 }) : t("onboarding.experiencesStoredPlural", { n: summary?.experienceCount ?? 0 })}</li>
        <li>{summary?.hasStrategy ? t("onboarding.strategyCreated") : t("onboarding.strategyPending")}</li>
        <li>{summary?.hasCv ? t("onboarding.resumeGenerated") : t("onboarding.resumeMissing")}</li>
        <li>{summary?.hasCoverLetter ? t("onboarding.clGenerated") : t("onboarding.clMissing")}</li>
      </ul>
      <div className="row mt" style={{ flexWrap: "wrap" }}>
        <button className="primary" onClick={onEnter}>{t("onboarding.enter")} <ArrowRight aria-hidden /></button>
        {applicationId && (
          <button className="ghost" onClick={async () => {
            await api.post("/api/onboarding/complete");
            window.location.assign(`/applications/${applicationId}`);
          }}>
            {t("onboarding.openApp")}
          </button>
        )}
      </div>
      <p className="small muted mt">
        {t("onboarding.afterEnter")}
      </p>
    </div>
  );
}
