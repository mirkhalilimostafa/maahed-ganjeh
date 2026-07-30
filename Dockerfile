# Production single-image deploy for Hamravesh Darkube
FROM hub.hamdocker.ir/library/node:22-alpine AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM hub.hamdocker.ir/library/python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Captcha OCR + admin login helper (Playwright). Browsers installed in CI outside Iran.
COPY package.json ./package.json
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install --omit=dev tesseract.js playwright@1.62.0 \
    && npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY api/app ./app
COPY scripts/maahed_admin_login.js scripts/ocr_digits.js /app/scripts/
COPY --from=webbuild /web/dist ./app/static

ENV PLAYWRIGHT_CHANNEL=
RUN mkdir -p /data /app/uploads

ENV DATABASE_URL=sqlite+aiosqlite:////data/ganjeh.db \
    UPLOAD_DIR=/app/uploads \
    APP_PUBLIC_BASE_URL=http://localhost:8000 \
    ADMIN_USERNAME=admin \
    ADMIN_PASSWORD=admin123 \
    APP_SECRET_KEY=change-me-in-darkube-env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
