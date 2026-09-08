import { useState } from "react";
import { api } from "../api/client";
import type { AppLanguage } from "../api/types";
import { getContentLanguage, setContentLanguage, useT } from "../lib/i18n";

export function LanguagePickers({ persist = false }: { persist?: boolean }) {
  const { t, lang, setLang } = useT();
  const [content, setContent] = useState<AppLanguage>(() => getContentLanguage());

  const save = async (ui: AppLanguage, contentLang: AppLanguage) => {
    setLang(ui);
    setContentLanguage(contentLang);
    setContent(contentLang);
    if (persist) {
      try {
        await api.put("/api/settings", { ui_language: ui, content_language: contentLang });
      } catch {
        /* local preference still applied */
      }
    }
  };

  return (
    <div className="grid cols-2">
      <div>
        <label>{t("language.interface")}</label>
        <div className="row">
          <button type="button" className={lang === "ar" ? "primary" : ""} onClick={() => save("ar", content)}>
            {t("language.arabic")}
          </button>
          <button type="button" className={lang === "en" ? "primary" : ""} onClick={() => save("en", content)}>
            {t("language.english")}
          </button>
        </div>
      </div>
      <div>
        <label>{t("language.content")}</label>
        <div className="row">
          <button type="button" className={content === "ar" ? "primary" : ""} onClick={() => save(lang, "ar")}>
            {t("language.arabic")}
          </button>
          <button type="button" className={content === "en" ? "primary" : ""} onClick={() => save(lang, "en")}>
            {t("language.english")}
          </button>
        </div>
        <p className="small muted mt">{t("language.contentHint")}</p>
      </div>
    </div>
  );
}
