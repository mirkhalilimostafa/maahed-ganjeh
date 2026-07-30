# Production single-image deploy for Hamravesh Darkube.
# Base images from Docker Hub (GitHub Actions); final tags push to hamdocker/ghcr.
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

# Proper Node/npm from official image (Debian apt node+npm breaks `npx playwright`)
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Captcha OCR + Chromium (CI runners can reach Playwright CDN)
COPY package.json ./package.json
RUN npm install --omit=dev --no-package-lock tesseract.js playwright@1.62.0 \
    && ./node_modules/.bin/playwright install --with-deps chromium

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
