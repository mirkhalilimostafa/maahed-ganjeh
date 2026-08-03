import { useState } from "react";
import { api } from "../api";

export default function ManualIngestPage() {
  const [source, setSource] = useState("");
  const [dataDate, setDataDate] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setMsg("");
    const fd = new FormData();
    fd.set("source", source);
    fd.set("data_date", dataDate);
    fd.set("description", description);
    if (file) fd.set("file", file);
    try {
      const row = await api("/api/manual-ingest", { method: "POST", formData: fd });
      setMsg(`ثبت شد — شناسه ${row.id}`);
      setSource("");
      setDataDate("");
      setDescription("");
      setFile(null);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="panel" onSubmit={onSubmit}>
      <h2>ورود دستی داده</h2>
      <p className="meta">منبع، تاریخ، توضیح، فایل — همان API که بات بعداً صدا می‌زند</p>
      <label>منبع</label>
      <input value={source} onChange={(e) => setSource(e.target.value)} required placeholder="مثلاً اکسل تیم فروش" />
      <label>تاریخ داده</label>
      <input value={dataDate} onChange={(e) => setDataDate(e.target.value)} required placeholder="1404/05/06" />
      <label>توضیح</label>
      <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      <label>فایل (اختیاری)</label>
      <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <button className="primary" type="submit">
        ثبت
      </button>
      {msg && <p className="freshness">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
