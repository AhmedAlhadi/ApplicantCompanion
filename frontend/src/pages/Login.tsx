import { FormEvent, useEffect, useRef, useState } from "react";
import { LogIn, UserPlus } from "lucide-react";
import { api, setToken } from "../api/client";
import type { AuthConfig, User } from "../api/types";
import { Brand } from "../components/ui";
import { LoginLangFlag } from "../components/LanguageSettings";
import { getUiLanguage, useT } from "../lib/i18n";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            ux_mode?: string;
            use_fedcm_for_prompt?: boolean;
            callback: (resp: { credential: string }) => void;
          }) => void;
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
        };
      };
    };
  }
}

function loadGis(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>("script[data-google-gis]");
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("gis")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.dataset.googleGis = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("gis"));
    document.head.appendChild(script);
  });
}

export default function Login() {
  const { t, lang } = useT();
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const googleBtnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<AuthConfig>("/api/auth/config").then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!config?.google_client_id || !googleBtnRef.current) return;
    let cancelled = false;
    loadGis()
      .then(() => {
        if (cancelled || !window.google?.accounts?.id || !googleBtnRef.current) return;
        googleBtnRef.current.innerHTML = "";
        window.google.accounts.id.initialize({
          client_id: config.google_client_id,
          ux_mode: "popup",
          use_fedcm_for_prompt: false,
          callback: async (resp) => {
            setBusy(true);
            setError(null);
            try {
              const result = await api.post<{ access_token: string; user: User }>("/api/auth/google", {
                id_token: resp.credential,
              });
              setToken(result.access_token);
              await persistUiLanguage();
              window.location.assign("/onboarding");
            } catch (err: any) {
              setError(typeof err.detail === "string" ? err.detail : t("login.googleFailed"));
              setBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: "outline",
          size: "large",
          width: 352,
          text: "signin_with",
          locale: lang === "ar" ? "ar" : "en",
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [config?.google_client_id, t, lang]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp =
        mode === "login"
          ? await api.post<{ access_token: string; user: User }>("/api/auth/login", { email, password })
          : await api.post<{ access_token: string; user: User }>("/api/auth/register", { email, password, full_name: fullName });
      setToken(resp.access_token);
      await persistUiLanguage();
      window.location.assign("/onboarding");
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : err.message);
    } finally {
      setBusy(false);
    }
  };

  const showRegister = mode === "register" || config?.registration_open;

  return (
    <div className="auth-page">
      <LoginLangFlag />
      <div className="auth-wrap">
        <Brand />
        <p className="muted" style={{ textAlign: "center" }}>
          {t("login.tagline")}
        </p>
        {config?.google_client_id ? (
          <div className="panel">
            <div className="google-btn-slot" ref={googleBtnRef} />
          </div>
        ) : null}
        <form className="panel" onSubmit={submit}>
          {config?.google_client_id ? <div className="auth-divider">{t("login.or")}</div> : null}
          {mode === "register" && (
            <>
              <label>{t("login.fullName")}</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </>
          )}
          <label>{t("login.email")}</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label>{t("login.password")}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          {error && <div className="alert error mt">{error}</div>}
          <button className="primary mt" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
            {mode === "login" ? <><LogIn aria-hidden /> {t("login.signIn")}</> : <><UserPlus aria-hidden /> {t("login.createWorkspace")}</>}
          </button>
          {showRegister && (
            <p className="small muted mt" style={{ textAlign: "center" }}>
              {mode === "login" ? (
                <>
                  {t("login.firstTime")}{" "}
                  <a href="#" onClick={(e) => (e.preventDefault(), setMode("register"))}>
                    {t("login.createAccount")}
                  </a>
                </>
              ) : (
                <a href="#" onClick={(e) => (e.preventDefault(), setMode("login"))}>
                  {t("login.backToSignIn")}
                </a>
              )}
            </p>
          )}
        </form>
      </div>
    </div>
  );
}

async function persistUiLanguage() {
  try {
    await api.put("/api/settings", { ui_language: getUiLanguage() });
  } catch {
    /* local preference still applied */
  }
}
