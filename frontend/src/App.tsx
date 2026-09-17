import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { api, getToken } from "./api/client";
import type { OnboardingStatus, User, UserSettings } from "./api/types";
import { Brand, Layout, useApi } from "./components/ui";
import AdminDashboard from "./pages/AdminDashboard";
import AdminUsers from "./pages/AdminUsers";
import AIConfig from "./pages/AIConfig";
import ApplicationDetail from "./pages/ApplicationDetail";
import Applications from "./pages/Applications";
import CareerCoach from "./pages/CareerCoach";
import CareerKnowledge from "./pages/CareerKnowledge";
import Dashboard from "./pages/Dashboard";
import DocumentEditor from "./pages/DocumentEditor";
import Documents from "./pages/Documents";
import JobDetail from "./pages/JobDetail";
import Jobs from "./pages/Jobs";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Settings from "./pages/Settings";
import CoachWidget from "./components/coach/CoachWidget";
import { setContentLanguage, setUiLanguage } from "./lib/i18n";

function AuthenticatedShell({ user }: { user: User }) {
  return (
    <>
      <Layout user={user} />
      <CoachWidget />
    </>
  );
}

export default function App() {
  const token = getToken();
  const me = useApi<User | null>(
    () => (token ? api.get("/api/auth/me") : Promise.resolve(null)),
    [token],
  );
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
        <Brand />
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
        <Route element={<AuthenticatedShell user={me.data} />}>
          <Route index element={<Dashboard />} />
          <Route path="/career" element={<CareerKnowledge />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/applications/:id" element={<ApplicationDetail />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:id" element={<DocumentEditor />} />
          <Route path="/coach" element={<CareerCoach />} />
          <Route path="/templates" element={<Navigate to="/settings" replace />} />
          <Route path="/cover-letter-templates" element={<Navigate to="/settings" replace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/ai-config" element={<AIConfig />} />
          <Route
            path="/admin"
            element={me.data.is_admin ? <AdminDashboard /> : <Navigate to="/" replace />}
          />
          <Route
            path="/admin/users"
            element={me.data.is_admin ? <AdminUsers currentUser={me.data} /> : <Navigate to="/" replace />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
