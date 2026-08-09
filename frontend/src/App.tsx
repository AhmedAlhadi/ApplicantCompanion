import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api, getToken } from "./api/client";
import type { User } from "./api/types";
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
import Settings from "./pages/Settings";
import Templates from "./pages/Templates";

export default function App() {
  const token = getToken();
  const me = useApi<User>(() => api.get("/api/auth/me"), [token]);

  if (!token) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login />} />
        </Routes>
      </BrowserRouter>
    );
  }
  if (me.loading) return <p className="muted" style={{ padding: 40 }}>Loading…</p>;
  if (me.error || !me.data) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login />} />
        </Routes>
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
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
