import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, type LucideIcon } from "lucide-react";
import type { WorkflowRun } from "../api/types";
import { tList, useT } from "../lib/i18n";
import { ProgressStages } from "./ui";

export const THINKING_PHRASES = {
  get jobAnalysis() { return tList("thinking.jobAnalysis"); },
  get cvIngest() { return tList("thinking.cvIngest"); },
  get strategy() { return tList("thinking.strategy"); },
  get docGeneration() { return tList("thinking.docGeneration"); },
  get sectionRegen() { return tList("thinking.sectionRegen"); },
  get generic() { return tList("thinking.generic"); },
};

const DEFAULT_INTERVAL_MS = 2200;

export default function ThinkingProgress({
  phrases,
  icon: Icon = Sparkles,
  workflow,
  intervalMs = DEFAULT_INTERVAL_MS,
}: {
  phrases: readonly string[];
  icon?: LucideIcon;
  workflow?: WorkflowRun | null;
  intervalMs?: number;
}) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
    const timer = window.setInterval(() => {
      setIndex((i) => (i + 1) % phrases.length);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [phrases, intervalMs]);

  const hasStages = (workflow?.stages?.length ?? 0) > 0;
  const { t } = useT();

  return (
    <div className="thinking" role="status" aria-live="polite">
      <div className="thinking-icon">
        <Icon aria-hidden />
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={index}
          className="thinking-phrase"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          {phrases[index]}
        </motion.div>
      </AnimatePresence>
      <div className="progress-bar thinking-bar" role="progressbar" aria-busy="true" aria-label={t("common.working")}>
        <div className="progress-bar-indeterminate" />
      </div>
      {hasStages && (
        <details className="thinking-details">
          <summary>{t("thinking.technical")}</summary>
          <ProgressStages workflow={workflow ?? null} />
        </details>
      )}
    </div>
  );
}
