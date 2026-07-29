import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const DEFAULT_REQUEST =
  "ساخت گزارش/داشبورد برای جلسه با سرمایه‌گذار جدید شامل رشد و عملکرد فروش و داده مالی پایه";

export default function DashboardRequestPage() {
  const nav = useNavigate();
  const [requestText, setRequestText] = useState(DEFAULT_REQUEST);
  const [title, setTitle] = useState("جلسه سرمایه‌گذار");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const dash = await api("/api/dashboards", {
        method: "POST",
        body: { request_text: requestText, title },
      });
      nav(`/dashboards/${dash.public_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="panel" onSubmit={onSubmit}>
      <h2 style={{ marginTop: 0 }}>درخواست داشبورد</h2>
      <p className="meta">زبان طبیعی → پیشنهاد اجزا → لینک وب (+ StubBot)</p>
      <label>عنوان</label>
      <input value={title} onChange={(e) => setTitle(e.target.value)} />
      <label>متن درخواست</label>
      <textarea rows={5} value={requestText} onChange={(e) => setRequestText(e.target.value)} required />
      <button className="primary" type="submit" disabled={loading}>
        {loading ? "در حال ساخت…" : "ساخت پیشنهاد داشبورد"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
