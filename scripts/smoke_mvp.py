"""Smoke test for MVP path (phase 3). Run while API is up on :8000."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
USER = os.environ.get("ADMIN_USERNAME", "admin")
PASS = os.environ.get("ADMIN_PASSWORD", "admin123")


def call(method: str, path: str, token: str | None = None, data: dict | None = None, form: dict | None = None):
    headers: dict[str, str] = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(f"{BASE}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def main() -> int:
    health = call("GET", "/health")
    assert health and health.get("ok"), health

    tok = call("POST", "/api/auth/login", form={"username": USER, "password": PASS})["access_token"]
    sources = call("GET", "/api/sources/status", token=tok)
    assert "sepidar" in sources and "maahed_site" in sources and "bot" in sources

    dash = call(
        "POST",
        "/api/dashboards",
        token=tok,
        data={
            "title": "MVP جلسه سرمایه‌گذار",
            "request_text": "ساخت گزارش/داشبورد برای جلسه با سرمایه‌گذار جدید، شامل رشد و عملکرد فروش و داده مالی پایه",
        },
    )
    assert dash["public_id"]
    assert all(w.get("freshness_label") for w in dash["widgets"]), dash["widgets"]
    assert any(w["key"] == "sales_performance" for w in dash["widgets"])
    assert any(w["key"] == "finance_baseline" for w in dash["widgets"])

    revised = call(
        "POST",
        f"/api/dashboards/{dash['public_id']}/revise",
        token=tok,
        data={"revision_notes": "بخش فروش را برجسته کن"},
    )
    assert revised["status"] == "revised"

    published = call("POST", f"/api/dashboards/{dash['public_id']}/publish", token=tok, data={})
    assert published["status"] == "published"
    assert published.get("bot_notify", {}).get("ok") is True

    public = call("GET", f"/api/dashboards/{dash['public_id']}")
    assert public["public_id"] == dash["public_id"]

    print("SMOKE OK")
    print(json.dumps({"url": published["url"], "widgets": [w["key"] for w in published["widgets"]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print("SMOKE FAIL:", exc, file=sys.stderr)
        raise SystemExit(1)
