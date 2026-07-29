import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, getToken } from "../api";

export default function DashboardViewPage({ publicMode = false }) {
  const { publicId } = useParams();
  const [dash, setDash] = useState(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const data = await api(`/api/dashboards/${publicId}`, { auth: !publicMode || Boolean(getToken()) });
      setDash(data);
    } catch (err) {
      // public endpoint works without auth
      try {
        const res = await fetch(`/api/dashboards/${publicId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "خطا");
        setDash(data);
      } catch (e2) {
        setError(e2.message || err.message);
      }
    }
  }

  useEffect(() => {
    load();
  }, [publicId]);

  async function revise() {
    setBusy(true);
    setError("");
    try {
      const data = await api(`/api/dashboards/${publicId}/revise`, {
        method: "POST",
        body: { revision_notes: revision },
      });
      setDash(data);
      setRevision("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    setBusy(true);
    try {
      const data = await api(`/api/dashboards/${publicId}/publish`, { method: "POST", body: {} });
      setDash(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !dash) return <div className="panel error">{error}</div>;
  if (!dash) return <div className="panel">در حال بارگذاری…</div>;

  return (
    <div>
      <div className="panel motion-fade">
        <h2 style={{ marginTop: 0 }}>{dash.title}</h2>
        <p className="meta">وضعیت: {dash.status}</p>
        <p className="meta">لینک: {dash.url}</p>
        {dash.bot_notify && <p className="freshness">بات: {dash.bot_notify.detail}</p>}
        <p>{dash.request_text}</p>
        {!publicMode && getToken() && (
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="primary" type="button" disabled={busy} onClick={publish}>
              انتشار
            </button>
          </div>
        )}
      </div>

      <div className="panel">
        {dash.widgets?.map((w) => (
          <div className="widget" key={w.key}>
            <h3 style={{ margin: 0 }}>{w.title}</h3>
            <p className="freshness">{w.freshness_label}</p>
            <p className="meta">
              منبع: {w.source} — فیلد: {w.source_field}
            </p>
            <pre>{JSON.stringify(w.data, null, 2)}</pre>
          </div>
        ))}
      </div>

      {!publicMode && getToken() && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>درخواست اصلاح</h3>
          <textarea
            rows={3}
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
            placeholder="مثلاً: رشد ماهانه را برجسته کن و هزینه جاری را از سپیدار جدا نشان بده"
          />
          <button className="primary" type="button" disabled={busy || !revision.trim()} onClick={revise}>
            اعمال اصلاح
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      )}
    </div>
  );
}
