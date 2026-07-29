# ماهد گنجه (Maahed Ganjeh)

سیستم مرکزی داشبورد (و بعداً مکاتبات) روی سرور داخلی شرکت.

## نسخه اول — سناریوی قبولی

داشبورد جلسه سرمایه‌گذار: فروش + مالی پایه + برچسب تازگی هر بخش + لینک وب + اصلاح پس از مشاهده.

جزئیات اجرا: [docs/OPERATIONS.md](docs/OPERATIONS.md)

## فازها

1. اسکلت (لاگین، منابع، StubBot) — پیاده‌سازی‌شده
2. موتور داشبورد — پیاده‌سازی‌شده
3. تست MVP — صفحه `/mvp` + API end-to-end
4+ نامه / RBAC / مفاهیم — [docs/PHASES-LATER.md](docs/PHASES-LATER.md)

## استک

FastAPI + PostgreSQL + React (Vite) + nginx + Docker Compose
