import { Navigate, Route, Routes, Link, useLocation, useNavigate } from "react-router-dom";
import { clearToken, getToken } from "./api";
import LoginPage from "./pages/Login.jsx";
import StatusPage from "./pages/Status.jsx";
import ManualIngestPage from "./pages/ManualIngest.jsx";
import DashboardRequestPage from "./pages/DashboardRequest.jsx";
import DashboardViewPage from "./pages/DashboardView.jsx";
import MvpChecklistPage from "./pages/MvpChecklist.jsx";

function Shell({ children }) {
  const loc = useLocation();
  const nav = useNavigate();
  const authed = Boolean(getToken());
  return (
    <div className="app-shell motion-fade">
      <h1 className="brand">
        ماهد <span>گنجه</span>
      </h1>
      <p className="sub">داشبورد و مکاتبات هوشمند — سرور داخلی شرکت</p>
      {authed && (
        <nav className="nav">
          <Link className={loc.pathname === "/" ? "active" : ""} to="/">
            وضعیت منابع
          </Link>
          <Link className={loc.pathname.startsWith("/dashboards") ? "active" : ""} to="/dashboards/new">
            ساخت داشبورد
          </Link>
          <Link className={loc.pathname === "/ingest" ? "active" : ""} to="/ingest">
            ورود دستی
          </Link>
          <Link className={loc.pathname === "/mvp" ? "active" : ""} to="/mvp">
            تست MVP
          </Link>
          <button
            type="button"
            className="linkish"
            onClick={() => {
              clearToken();
              nav("/login");
            }}
          >
            خروج
          </button>
        </nav>
      )}
      {children}
    </div>
  );
}

function RequireAuth({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/d/:publicId" element={<DashboardViewPage publicMode />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Shell>
              <StatusPage />
            </Shell>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboards/new"
        element={
          <RequireAuth>
            <Shell>
              <DashboardRequestPage />
            </Shell>
          </RequireAuth>
        }
      />
      <Route
        path="/dashboards/:publicId"
        element={
          <RequireAuth>
            <Shell>
              <DashboardViewPage />
            </Shell>
          </RequireAuth>
        }
      />
      <Route
        path="/ingest"
        element={
          <RequireAuth>
            <Shell>
              <ManualIngestPage />
            </Shell>
          </RequireAuth>
        }
      />
      <Route
        path="/mvp"
        element={
          <RequireAuth>
            <Shell>
              <MvpChecklistPage />
            </Shell>
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
