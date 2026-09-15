import { FormEvent, useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { api } from "../api/client";
import type { UserSettings } from "../api/types";
import { ErrorBox, useApi } from "../components/ui";
import { useT } from "../lib/i18n";
import { useTheme, type ThemePref } from "../lib/theme";
import { ThemePicker } from "./Templates";

const THEME_KEYS: { key: ThemePref; labelKey: string; icon: typeof Sun }[] = [
  { key: "system", labelKey: "settings.themeSystem", icon: Monitor },
  { key: "light", labelKey: "settings.themeLight", icon: Sun },
  { key: "dark", labelKey: "settings.themeDark", icon: Moon },
];

export default function Settings() {
  const { t } = useT();
  const { data, reload, loading } = useApi<UserSettings>(() => api.get("/api/settings"));
  const { pref, setPref } = useTheme();
  const [threshold, setThreshold] = useState(0.8);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [cvTheme, setCvTheme] = useState("minimal-ats");
  const [clTheme, setClTheme] = useState("minimal-ats");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setThreshold(data.score_threshold ?? 0.8);
      setWeights(data.scoring_weights ?? {});
      setCvTheme(data.default_cv_template || "minimal-ats");
      setClTheme(data.default_cover_letter_template || "minimal-ats");
    }
  }, [data]);

  const total = Object.values(weights).reduce((a, b) => a + (Number(b) || 0), 0);

  const persistThemes = async (next: { default_cv_template?: string; default_cover_letter_template?: string }) => {
    setError(null);
    try {
      await api.put("/api/settings", next);
      reload();
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("settings.saveFailed"));
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.put("/api/settings", { score_threshold: Number(threshold), scoring_weights: weights });
      setSaved(true);
      reload();
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : t("settings.saveFailed"));
    }
  };

  if (loading) return <p className="muted">{t("common.loading")}</p>;

  return (
    <>
      <h1 className="page-title">{t("settings.title")}</h1>
      <p className="page-sub">{t("settings.sub")}</p>
      <div className="panel" style={{ maxWidth: 640 }}>
        <h3>{t("settings.appearance")}</h3>
        <div className="row">
          {THEME_KEYS.map(({ key, labelKey, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={pref === key ? "primary" : ""}
              onClick={() => setPref(key)}
              aria-pressed={pref === key}
            >
              <Icon aria-hidden /> {t(labelKey)}
            </button>
          ))}
        </div>
        <p className="small muted mt">{t("settings.themeHint")}</p>
      </div>
      <div className="panel">
        <h3>{t("settings.resumeTheme")}</h3>
        <p className="small muted">{t("settings.themeSelectHint")}</p>
        <ThemePicker
          documentType="cv"
          selected={cvTheme}
          onSelect={(key) => {
            setCvTheme(key);
            persistThemes({ default_cv_template: key });
          }}
        />
      </div>
      <div className="panel">
        <h3>{t("settings.coverTheme")}</h3>
        <p className="small muted">{t("settings.themeSelectHint")}</p>
        <ThemePicker
          documentType="cover_letter"
          selected={clTheme}
          onSelect={(key) => {
            setClTheme(key);
            persistThemes({ default_cover_letter_template: key });
          }}
        />
      </div>
      <form className="panel" onSubmit={save} style={{ maxWidth: 640 }}>
        <h3>{t("settings.threshold")}</h3>
        <label>{t("settings.thresholdLabel", { pct: Math.round(threshold * 100) })}</label>
        <input type="range" min={0.5} max={0.95} step={0.01} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
        <p className="small muted">{t("settings.thresholdHint")}</p>

        <h3 className="mt">{t("settings.weights")}</h3>
        {Object.entries(weights).map(([key, value]) => (
          <div className="score-row" key={key}>
            <span className="name">{t(`category.${key}`)}</span>
            <input type="range" min={0} max={0.5} step={0.01} value={value} onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })} />
            <span className="pct">{Math.round(value * 100)}%</span>
          </div>
        ))}
        <p className={`small ${Math.abs(total - 1) > 0.01 ? "" : "muted"}`} style={Math.abs(total - 1) > 0.01 ? { color: "var(--danger)" } : {}}>
          {t("settings.total", { pct: Math.round(total * 100) })}
        </p>
        <ErrorBox error={error} />
        <div className="row mt">
          <button className="primary" disabled={Math.abs(total - 1) > 0.01}>{t("settings.save")}</button>
          {saved && <span className="badge verified">{t("common.saved")}</span>}
        </div>
      </form>
    </>
  );
}
