import { useEffect, useState } from "react";
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

const SOURCE_OPTIONS = [
  { id: "sepidar", label: "سپیدار (ERP زنده)", locked: true },
  { id: "maahed_site", label: "سایت ماهد", locked: true },
  { id: "darkube_disk", label: "دیسک پایدار دارکوب (فایل/SQLite)", locked: false },
];

export default function DashboardRequestPage() {
  const nav = useNavigate();
  const board = PRESETS[0];
  const [requestText, setRequestText] = useState(board.request);
  const [title, setTitle] = useState(board.title);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [includeDisk, setIncludeDisk] = useState(false);
  const [diskHint, setDiskHint] = useState("");

  useEffect(() => {
    api("/api/sources/status")
      .then((s) => {
        const d = s?.darkube_disk;
        if (d?.ok) {
          setDiskHint(d.usage_label ? `آماده — ${d.usage_label}` : d.freshness_label || "آماده");
        } else if (d) {
          setDiskHint(d.freshness_label || "ناقص");
        }
      })
      .catch(() => {});
  }, []);

  function applyPreset(preset) {
    setTitle(preset.title);
    setRequestText(preset.request);
  }

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const sources = ["sepidar", "maahed_site"];
      if (includeDisk) sources.push("darkube_disk");
      const dash = await api("/api/dashboards", {
        method: "POST",
        body: { request_text: requestText, title, sources },
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
      <h2>درخواست داشبورد</h2>
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
      <fieldset className="source-picker">
        <legend>منابع</legend>
        <p className="meta">سپیدار و سایت همیشه برای اعداد زنده می‌آیند؛ دیسک فقط برای فایل/آپلود است.</p>
        {SOURCE_OPTIONS.map((opt) => (
          <label key={opt.id} className="source-option">
            <input
              type="checkbox"
              checked={opt.locked ? true : includeDisk}
              disabled={opt.locked}
              onChange={(e) => {
                if (!opt.locked) setIncludeDisk(e.target.checked);
              }}
            />
            <span>
              {opt.label}
              {opt.id === "darkube_disk" && diskHint ? ` — ${diskHint}` : ""}
            </span>
          </label>
        ))}
      </fieldset>
      <button className="primary" type="submit" disabled={loading}>
        {loading ? "در حال ساخت…" : "ساخت پیشنهاد داشبورد"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
