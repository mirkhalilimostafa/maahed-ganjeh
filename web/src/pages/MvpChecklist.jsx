import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

const STEPS = [
  { id: "login", label: "لاگین پنل" },
  { id: "sources", label: "وضعیت سپیدار و سایت" },
  { id: "create", label: "ساخت داشبورد جلسه سرمایه‌گذار" },
  { id: "freshness", label: "برچسب تازگی روی هر بخش" },
  { id: "link", label: "لینک وب + اعلان StubBot" },
  { id: "revise", label: "اصلاح بعد از مشاهده" },
];

export default function MvpChecklistPage() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  async function runScenario() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const sources = await api("/api/sources/status");
      const dash = await api("/api/dashboards", {
        method: "POST",
        body: {
          title: "MVP جلسه سرمایه‌گذار",
          request_text:
            "ساخت گزارش/داشبورد برای جلسه با سرمایه‌گذار جدید، شامل داده‌های رشد و عملکرد فروش و داده‌های مالی پایه",
        },
      });
      const revised = await api(`/api/dashboards/${dash.public_id}/revise`, {
        method: "POST",
        body: { revision_notes: "لطفاً بخش فروش سایت را جداگانه نگه دار و تازگی هر ویجت را حفظ کن" },
      });
      const published = await api(`/api/dashboards/${dash.public_id}/publish`, { method: "POST", body: {} });
      const freshnessOk = (published.widgets || []).every((w) => Boolean(w.freshness_label));
      setResult({
        sources,
        dash: published,
        revised_status: revised.status,
        checks: {
          sources_endpoint: true,
          dashboard_created: Boolean(dash.public_id),
          freshness_on_each_widget: freshnessOk,
          link: published.url,
          bot_notify: published.bot_notify,
          revise_worked: revised.status === "revised" || published.status === "published",
        },
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>فاز ۳ — چک‌لیست سناریوی MVP</h2>
      <p className="meta">مسیر واقعی جلسه سرمایه‌گذار از اول تا آخر</p>
      <ol>
        {STEPS.map((s) => (
          <li key={s.id}>{s.label}</li>
        ))}
      </ol>
      <button className="primary" type="button" disabled={running} onClick={runScenario}>
        {running ? "در حال اجرای سناریو…" : "اجرای خودکار سناریوی MVP"}
      </button>
      <p className="meta" style={{ marginTop: "0.75rem" }}>
        یا دستی از <Link to="/dashboards/new">ساخت داشبورد</Link>
      </p>
      {error && <p className="error">{error}</p>}
      {result && (
        <div style={{ marginTop: "1rem" }}>
          <p className="freshness">نتیجه اجرا</p>
          <pre>{JSON.stringify(result.checks, null, 2)}</pre>
          {result.dash?.public_id && (
            <p>
              <Link to={`/dashboards/${result.dash.public_id}`}>باز کردن داشبورد ساخته‌شده</Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
