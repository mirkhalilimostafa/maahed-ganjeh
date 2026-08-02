import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const PRESETS = [
  {
    id: "board",
    label: "گزارش هیئت‌مدیره (مدیرعامل)",
    title: "گزارش مالی هیئت‌مدیره",
    request:
      "داشبورد مالی برای مدیرعامل جهت گزارش به هیئت‌مدیره: درآمد و رشد فروش، حاشیه و عملکرد فروش، مانده مطالبات و نقدینگی (مانده بانکی سپیدار)، کانال فروش سایت، روند فروش ماهانه و ریسک‌های عملیاتی برای تصمیم‌گیری هیئت مدیره",
  },
  {
    id: "investor",
    label: "جلسه سرمایه‌گذار",
    title: "جلسه سرمایه‌گذار",
    request:
      "ساخت گزارش/داشبورد برای جلسه با سرمایه‌گذار جدید شامل رشد و عملکرد فروش و داده مالی پایه",
  },
];

export default function DashboardRequestPage() {
  const nav = useNavigate();
  const board = PRESETS[0];
  const [requestText, setRequestText] = useState(board.request);
  const [title, setTitle] = useState(board.title);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function applyPreset(preset) {
    setTitle(preset.title);
    setRequestText(preset.request);
  }

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
      <p className="meta">زبان طبیعی → پیشنهاد اجزا → لینک وب (+ اعلان بات در صورت تنظیم گیرنده)</p>
      <div className="preset-row">
        {PRESETS.map((p) => (
          <button key={p.id} type="button" className="linkish" onClick={() => applyPreset(p)}>
            {p.label}
          </button>
        ))}
      </div>
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
