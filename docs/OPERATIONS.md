# ماهد گنجه — عملیات

## یک‌فرمان اجرا

```bash
cp .env.example .env
# مقادیر را پر کنید؛ حداقل ADMIN_PASSWORD
docker compose up --build -d
```

سپس باز کنید: `http://localhost:8080`

- سلامت: `GET /health`
- مستندات API: `/docs`
- لاگین پنل با `ADMIN_USERNAME` / `ADMIN_PASSWORD`

## متغیرهای ضروری

| متغیر | نقش |
|---|---|
| `APP_SECRET_KEY` | JWT |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | کاربر پنل v0 |
| `SEPIDAR_MCP_URL` / `SEPIDAR_MCP_TOKEN` | اتصال سپیدار سمت سرور |
| `MAAHED_SITE_USERNAME` / `MAAHED_SITE_PASSWORD` | لاگین سایت |
| `APP_PUBLIC_BASE_URL` | لینک داشبورد در پیام بات |

توکن تلگرام/بله فعلاً لازم نیست (StubBot).

## توسعه محلی بدون Docker (API)

پایتون **۳.۱۲** توصیه می‌شود (۳.۱۴ روی ویندوز ممکن است wheel نداشته باشد).

```bash
py -3.12 -m venv .venv
# Windows:
.\.venv\Scripts\activate
pip install -r api/requirements.txt
set DATABASE_URL=sqlite+aiosqlite:///./api/ganjeh.db
cd api
uvicorn app.main:app --reload --port 8000
```

```bash
cd web
npm install
npm run dev
```

### تست دود MVP (فاز ۳)

با API روشن:

```bash
.\.venv\Scripts\python.exe scripts\smoke_mvp.py
```

## توقف بین فازها

طبق بریف: بعد از هر فاز منتظر تأیید مالک بمانید. نامه اداری / RBAC کامل / دفترچه مفاهیم در `docs/PHASES-LATER.md`.
