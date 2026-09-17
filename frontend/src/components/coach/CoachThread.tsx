import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, MessageSquare } from "lucide-react";
import type { CoachMessage } from "../../api/types";
import { useT } from "../../lib/i18n";
import { Empty, ErrorBox, Spinner } from "../ui";
import CoachEvidencePeek from "./CoachEvidencePeek";
import type { CoachSelection } from "./coachContext";
import { isGeneralSelection } from "./coachContext";

type Props = {
  messages: CoachMessage[];
  draft: string;
  onDraft: (value: string) => void;
  busy: boolean;
  error: string | null;
  selection: CoachSelection;
  onSend: () => Promise<unknown>;
};

function suggestions(selection: CoachSelection, t: (key: string) => string) {
  if (selection.applicationId) return [t("coach.suggestApp1"), t("coach.suggestApp2")];
  if (selection.jobId) return [t("coach.suggestJob1"), t("coach.suggestJob2")];
  return [t("coach.suggestGeneral1"), t("coach.suggestGeneral2")];
}

export default function CoachThread({ messages, draft, onDraft, busy, error, selection, onSend }: Props) {
  const { t } = useT();
  const scrollerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [openCite, setOpenCite] = useState<string | null>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, busy]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || busy) return;
    await onSend();
    textareaRef.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    void submit();
  };

  return (
    <div className="coach-thread">
      <div className="coach-messages" ref={scrollerRef}>
        {!messages.length && (
          <div className="coach-empty">
            <Empty icon={MessageSquare}>{t("coach.empty")}</Empty>
            <div className="coach-suggestions">
              {suggestions(selection, t).map((prompt) => (
                <button key={prompt} type="button" className="coach-suggestion" onClick={() => { onDraft(prompt); textareaRef.current?.focus(); }}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <article key={m.id} className={`coach-msg ${m.role}`}>
            <div className="coach-msg-role">{m.role === "user" ? t("map.you") : t("coach.title")}</div>
            <p className="coach-msg-body" dir="auto">{m.content}</p>
            {!!m.citations?.length && (
              <div className="coach-cites">
                <span className="small muted">{t("coach.citations")}</span>
                {m.citations.map((cite) => {
                  const key = `${cite.entity_type}:${cite.entity_id}`;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`coach-cite${openCite === key ? " open" : ""}`}
                      onClick={() => setOpenCite(openCite === key ? null : key)}
                    >
                      {cite.label}
                      {cite.verification_status ? ` · ${cite.verification_status}` : ""}
                    </button>
                  );
                })}
              </div>
            )}
            {m.citations?.map((cite) => {
              const key = `${cite.entity_type}:${cite.entity_id}`;
              return openCite === key ? <CoachEvidencePeek key={key} entityType={cite.entity_type} entityId={cite.entity_id} /> : null;
            })}
          </article>
        ))}
        {busy && (
          <div className="coach-msg assistant pending">
            <div className="coach-msg-role">{t("coach.title")}</div>
            <p className="coach-msg-body"><Spinner /> {t("coach.sending")}</p>
          </div>
        )}
      </div>
      <ErrorBox error={error} />
      <form className="coach-composer" onSubmit={submit}>
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("coach.placeholder")}
          rows={1}
          aria-label={t("coach.composerAria")}
          disabled={busy}
        />
        <button type="submit" className="primary coach-send" disabled={busy || !draft.trim()} aria-label={t("coach.send")}>
          <ArrowUp aria-hidden />
        </button>
        <p className="coach-composer-hint">
          {t("coach.enterHint")}
          {isGeneralSelection(selection) ? ` · ${t("coach.generalTitle")}` : ""}
        </p>
      </form>
    </div>
  );
}
