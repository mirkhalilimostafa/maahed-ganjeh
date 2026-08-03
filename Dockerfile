# Production single-image for Hamravesh Darkube (lean: API + web, no Chromium).
# Playwright browsers were OOM/not-ready on 500MB pods; site captcha soft-fails without them.
FROM node:22-bookworm-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# ddddocr pulls onnxruntime; needed for maahed.ir captcha without Chromium/Node.

COPY api/app ./app
COPY scripts/maahed_admin_login.js scripts/ocr_digits.js /app/scripts/
COPY --from=webbuild /web/dist ./app/static

RUN mkdir -p /data /app/uploads

ENV DATABASE_URL=sqlite+aiosqlite:////data/ganjeh.db \
    UPLOAD_DIR=/app/uploads \
    APP_PUBLIC_BASE_URL=http://localhost:8000 \
    ADMIN_USERNAME=admin \
    ADMIN_PASSWORD=admin123 \
    APP_SECRET_KEY=change-me-in-darkube-env \
    PLAYWRIGHT_CHANNEL=

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
