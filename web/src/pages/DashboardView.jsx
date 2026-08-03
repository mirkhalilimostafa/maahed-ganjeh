import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getToken } from "../api";

const STATUS_FA = {
  proposed: "پیشنهاد شده",
  revised: "اصلاح‌شده",
  published: "منتشر شده",
  draft: "پیش‌نویس",
};

function formatRial(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Number(n).toLocaleString("fa-IR")} ریال`;
}

function KpiGrid({ items }) {
  if (!items?.length) return null;
  return (
    <div className="kpi-grid">
      {items.map((item) => (
        <div className="kpi-card" key={item.label}>
          <div className="kpi-label">{item.label}</div>
          <div className="kpi-value">{item.value}</div>
          {item.hint && <div className="meta">{item.hint}</div>}
        </div>
      ))}
    </div>
  );
}

function RankTable({ title, rows, nameKey = "name", valueKey = "net" }) {
  if (!rows?.length) return null;
  return (
    <div className="rank-table-wrap">
      <h4 className="rank-title">{title}</h4>
      <table className="rank-table">
        <thead>
          <tr>
            <th>نام</th>
            <th>مبلغ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r[nameKey]}-${r[valueKey]}`}>
              <td>{r[nameKey]}</td>
              <td className="num">{formatRial(r[valueKey])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WidgetBody({ w, publicMode = false }) {
  const data = w.data || {};
  const kpis = data.kpis;
  const cash = data.cash_banks;
  const [showRaw, setShowRaw] = useState(false);

  if (w.key === "sales_performance" && kpis) {
    return (
      <div>
        <KpiGrid
          items={[
            { label: "فروش خالص (نمونه)", value: formatRial(kpis.net_sales) },
            { label: "تعداد فاکتور", value: String(kpis.invoice_count ?? 0) },
            { label: "تعداد ردیف", value: String(kpis.row_count ?? 0) },
            { label: "تخفیف", value: formatRial(kpis.discount_total) },
          ]}
        />
        {data.period && (
          <p className="meta">
            دوره: {data.period.from} تا {data.period.to}
          </p>
        )}
        <div className="split-tables">
          <RankTable title="برترین مشتریان (نمونه)" rows={kpis.top_customers} />
          <RankTable title="برترین اقلام (نمونه)" rows={kpis.top_items} />
        </div>
        {kpis.by_month?.length > 0 && (
          <RankTable title="روند ماهانه (خالص)" rows={kpis.by_month} nameKey="month" />
        )}
        <p className="meta">{data.note}</p>
        <button type="button" className="linkish raw-toggle" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "بستن JSON خام" : "نمایش JSON خام"}
        </button>
        {showRaw && <pre>{JSON.stringify(data, null, 2)}</pre>}
      </div>
    );
  }

  if (w.key === "finance_baseline") {
    return (
      <div>
        {cash?.accounts?.length > 0 ? (
          <>
            <KpiGrid
              items={[
                {
                  label: "جمع خام مانده حساب‌ها",
                  value: formatRial(cash.balance_sum_raw),
                  hint: cash.note,
                },
                { label: "تعداد حساب", value: String(cash.account_count ?? cash.accounts.length) },
              ]}
            />
            <table className="rank-table">
              <thead>
                <tr>
                  <th>حساب</th>
                  <th>نوع</th>
                  <th>مانده</th>
                </tr>
              </thead>
              <tbody>
                {cash.accounts.map((a) => (
                  <tr key={a.account_no || a.title}>
                    <td>{a.title}</td>
                    <td>{a.type || "—"}</td>
                    <td className="num">{formatRial(a.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="meta">مانده بانکی در دسترس نیست — فقط وضعیت اتصال نمایش داده می‌شود.</p>
        )}
        {data.connection && (
          <p className="meta">
            اتصال سپیدار: {data.connection.ok ? "برقرار" : "قطع"} — {data.connection.detail}
          </p>
        )}
        {data.disclaimer && <p className="freshness">{data.disclaimer}</p>}
        <button type="button" className="linkish raw-toggle" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "بستن JSON خام" : "نمایش JSON خام"}
        </button>
        {showRaw && <pre>{JSON.stringify(data, null, 2)}</pre>}
      </div>
    );
  }

  if (w.key === "board_framing" || w.key === "investor_framing") {
    return (
      <div>
        {data.audience && <p className="meta">مخاطب: {data.audience}</p>}
        {data.suggested_narrative && <p>{data.suggested_narrative}</p>}
        {Array.isArray(data.focus) && data.focus.length > 0 && (
          <ul className="focus-list">
            {data.focus.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (w.key === "site_channel") {
    const st = data.status || {};
    const snap = data.snapshot || {};
    return (
      <div>
        <KpiGrid
          items={[
            {
              label: "وضعیت سایت",
              value: st.ok ? "در دسترس" : "قطع",
              hint: st.freshness_label || st.detail,
            },
            {
              label: "پنل ادمین",
              value: st.admin_reachable ? "قابل دسترس" : "محدود",
              hint: st.logged_in ? "لاگین شده" : "بدون لاگین ادمین",
            },
          ]}
        />
        {snap.title && <p className="meta">عنوان صفحه: {snap.title}</p>}
        {snap.note && <p className="meta">{snap.note}</p>}
        <button type="button" className="linkish raw-toggle" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "بستن JSON خام" : "نمایش JSON خام"}
        </button>
        {showRaw && <pre>{JSON.stringify(data, null, 2)}</pre>}
      </div>
    );
  }

  if (w.key === "darkube_disk_storage") {
    const st = data.status || {};
    return (
      <div>
        <p className="meta">{data.disclaimer}</p>
        <KpiGrid
          items={[
            {
              label: "وضعیت دیسک",
              value: st.ok ? "متصل" : "ناقص",
              hint: st.freshness_label || st.detail,
            },
            {
              label: "مصرف",
              value: st.usage_label || "—",
              hint: st.mount_path || st.upload_dir,
            },
            {
              label: "فایل آپلود",
              value: typeof st.upload_file_count === "number" ? String(st.upload_file_count) : "—",
              hint: st.upload_dir,
            },
          ]}
        />
        {!publicMode && data.manual_ingest_path && (
          <p className="meta">
            <Link to={data.manual_ingest_path}>ورود دستی / فایل‌ها</Link>
          </p>
        )}
        <button type="button" className="linkish raw-toggle" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "بستن JSON خام" : "نمایش JSON خام"}
        </button>
        {showRaw && <pre>{JSON.stringify(data, null, 2)}</pre>}
      </div>
    );
  }

  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}

export default function DashboardViewPage({ publicMode = false }) {
  const { publicId } = useParams();
  const [dash, setDash] = useState(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function load() {
    try {
      const data = await api(`/api/dashboards/${publicId}`, { auth: !publicMode || Boolean(getToken()) });
      setDash(data);
    } catch (err) {
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
    setError("");
    try {
      const data = await api(`/api/dashboards/${publicId}/publish`, { method: "POST", body: {} });
      setDash(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!dash?.url) return;
    try {
      await navigator.clipboard.writeText(dash.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("کپی لینک ناموفق بود");
    }
  }

  if (error && !dash) return <div className="panel error">{error}</div>;
  if (!dash) return <div className="panel">در حال بارگذاری…</div>;

  const statusLabel = STATUS_FA[dash.status] || dash.status;

  return (
    <div>
      <div className="panel motion-fade">
        <h2>{dash.title}</h2>
        <p className="meta">
          وضعیت: <span className="badge">{statusLabel}</span>
          <span className="meta status-code"> ({dash.status})</span>
        </p>
        <p className="meta share-row">
          لینک:{" "}
          <a href={dash.url} target="_blank" rel="noreferrer">
            {dash.url}
          </a>
          <button type="button" className="linkish" onClick={copyLink}>
            {copied ? "کپی شد" : "کپی"}
          </button>
        </p>
        {dash.bot_notify && (
          <p className={dash.bot_notify.ok ? "freshness" : "error"}>
            اعلان بات ({dash.bot_notify.channel}): {dash.bot_notify.detail}
          </p>
        )}
        <p>{dash.request_text}</p>
        {!publicMode && getToken() && (
          <div className="action-row">
            <button className="primary" type="button" disabled={busy} onClick={publish}>
              انتشار
            </button>
          </div>
        )}
      </div>

      <div className="panel">
        {dash.widgets?.map((w) => (
          <div className="widget" key={w.key}>
            <h3>{w.title}</h3>
            <p className="freshness">{w.freshness_label}</p>
            <p className="meta">
              منبع: {w.source} — فیلد: {w.source_field}
            </p>
            <WidgetBody w={w} publicMode={publicMode} />
          </div>
        ))}
      </div>

      {!publicMode && getToken() && (
        <div className="panel">
          <h3>درخواست اصلاح</h3>
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
