import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api/client";
import type { User } from "../api/types";

export default function Login() {
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

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
      navigate("/");
      window.location.reload();
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
        Career intelligence workspace
      </p>
      <form className="panel" onSubmit={submit}>
        {mode === "register" && (
          <>
            <label>Full name</label>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </>
        )}
        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        {error && <div className="alert error mt">{error}</div>}
        <button className="primary mt" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
          {mode === "login" ? "Sign in" : "Create workspace"}
        </button>
        <p className="small muted mt" style={{ textAlign: "center" }}>
          {mode === "login" ? (
            <>
              First time?{" "}
              <a href="#" onClick={(e) => (e.preventDefault(), setMode("register"))}>
                Create the workspace account
              </a>
            </>
          ) : (
            <a href="#" onClick={(e) => (e.preventDefault(), setMode("login"))}>
              Back to sign in
            </a>
          )}
        </p>
      </form>
    </div>
  );
}
