import { FormEvent, useState } from "react";
import { LogIn, UserPlus } from "lucide-react";
import { api, setToken } from "../api/client";
import type { User } from "../api/types";
import { LanguagePickers } from "../components/LanguageSettings";
import { useT } from "../lib/i18n";

export default function Login() {
  const { t } = useT();
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      window.location.assign("/onboarding");
    } catch (err: any) {
      setError(typeof err.detail === "string" ? err.detail : err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="brand">
        Applicant<span>Companion</span>
      </div>
      <p className="muted" style={{ textAlign: "center" }}>
        {t("login.tagline")}
      </p>
      <form className="panel" onSubmit={submit}>
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
      </form>
      <div className="panel">
        <LanguagePickers />
      </div>
    </div>
  );
}
