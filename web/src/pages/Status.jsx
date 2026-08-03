import { useEffect, useState } from "react";
import { api } from "../api";

function StatusCard({ title, info }) {
  if (!info) return null;
  const ok = Boolean(info.ok);
  return (
    <div className="panel">
      <h3>{title}</h3>
      <span className={`badge ${ok ? "ok" : "bad"}`}>{ok ? "متصل / آماده" : "ناقص یا قطع"}</span>
      <p className="freshness">{info.freshness_label || info.note || "—"}</p>
      {info.mount_path && <p className="meta">مسیر مونت: {info.mount_path}</p>}
      {info.upload_dir && <p className="meta">آپلود: {info.upload_dir}</p>}
      {info.usage_label && <p className="meta">مصرف: {info.usage_label}</p>}
      {typeof info.upload_file_count === "number" && (
        <p className="meta">فایل‌های آپلود: {info.upload_file_count}</p>
      )}
      {info.note && info.source === "darkube_disk" && <p className="meta">{info.note}</p>}
      <p className="meta">{info.detail || (!info.mount_path && JSON.stringify(info).slice(0, 180))}</p>
    </div>
  );
}

export default function StatusPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/sources/status")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <div className="panel">
        <h2>وضعیت اتصالات</h2>
        <p className="meta">سپیدار، سایت ماهد، دیسک پایدار دارکوب، و بات اعلان</p>
        {error && <p className="error">{error}</p>}
      </div>
      <div className="status-grid status-grid-spaced">
        <StatusCard title="سپیدار" info={data?.sepidar} />
        <StatusCard title="سایت maahed.ir" info={data?.maahed_site} />
        <StatusCard title="دیسک پایدار دارکوب" info={data?.darkube_disk} />
        <StatusCard title="بات (اعلان)" info={data?.bot} />
      </div>
    </div>
  );
}
