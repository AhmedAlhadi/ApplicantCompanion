import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { api, getToken } from "./api/client";
import type { OnboardingStatus, User, UserSettings } from "./api/types";
import { Layout, useApi } from "./components/ui";
import AIConfig from "./pages/AIConfig";
import ApplicationDetail from "./pages/ApplicationDetail";
import Applications from "./pages/Applications";
import CareerKnowledge from "./pages/CareerKnowledge";
import Dashboard from "./pages/Dashboard";
import DocumentEditor from "./pages/DocumentEditor";
import Documents from "./pages/Documents";
import JobDetail from "./pages/JobDetail";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";
import Templates from "./pages/Templates";
import { setContentLanguage, setUiLanguage } from "./lib/i18n";

export default function App() {
  const token = getToken();
  const me = useApi<User>(() => api.get("/api/auth/me"), [token]);
  const onboarding = useApi<OnboardingStatus | null>(
    () => (token ? api.get("/api/onboarding") : Promise.resolve(null)),
    [token],
  );

  useEffect(() => {
    if (!token) return;
    api.get<UserSettings>("/api/settings").then((s) => {
      if (s.ui_language === "ar" || s.ui_language === "en") setUiLanguage(s.ui_language);
      if (s.content_language === "ar" || s.content_language === "en") setContentLanguage(s.content_language);
    }).catch(() => undefined);
  }, [token]);

  if (!token) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login />} />
        </Routes>
      </BrowserRouter>
    );
  }
  if (me.loading || onboarding.loading) {
    return (
      <div className="boot-splash">
        <div className="brand">
          Applicant<span>Companion</span>
        </div>
        <div className="skeleton skeleton-text" style={{ width: 180 }} />
        <div className="skeleton skeleton-text" style={{ width: 120 }} />
      </div>
    );
  }
  if (me.error || !me.data) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login />} />
        </Routes>
      </BrowserRouter>
    );
  }

  const finished = onboarding.data?.status === "completed" || onboarding.data?.status === "skipped";

  if (!finished) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/onboarding" element={<Onboarding user={me.data} />} />
          <Route path="*" element={<Navigate to="/onboarding" replace />} />
        </Routes>
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<Navigate to="/" replace />} />
        <Route element={<Layout user={me.data} />}>
          <Route index element={<Dashboard />} />
          <Route path="/career" element={<CareerKnowledge />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/applications/:id" element={<ApplicationDetail />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:id" element={<DocumentEditor />} />
          <Route path="/templates" element={<Templates documentType="cv" />} />
          <Route path="/cover-letter-templates" element={<Templates documentType="cover_letter" />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/ai-config" element={<AIConfig />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
