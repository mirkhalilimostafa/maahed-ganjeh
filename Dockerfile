# Production single-image deploy for Hamravesh Darkube.
# Base images from Docker Hub (GitHub Actions); final tags push to hamdocker/ghcr.
FROM node:22-bookworm-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# Isolated captcha deps (do NOT reuse root package.json — it only has @playwright/test as devDep)
FROM node:22-bookworm-slim AS captcha
WORKDIR /captcha
RUN npm init -y \
    && npm install --no-fund --no-audit tesseract.js@5.1.1 playwright@1.62.0 \
    && test -f node_modules/playwright/cli.js \
    && node node_modules/playwright/cli.js install --with-deps chromium

FROM python:3.12-slim-bookworm
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Node runtime for captcha helper scripts
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=captcha /captcha/node_modules /app/node_modules
COPY --from=captcha /root/.cache/ms-playwright /root/.cache/ms-playwright

# Chromium shared libraries for this distro (browsers already downloaded in captcha stage)
RUN node node_modules/playwright/cli.js install-deps chromium

COPY api/app ./app
COPY scripts/maahed_admin_login.js scripts/ocr_digits.js /app/scripts/
COPY --from=webbuild /web/dist ./app/static

ENV PLAYWRIGHT_CHANNEL= \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
RUN mkdir -p /data /app/uploads

ENV DATABASE_URL=sqlite+aiosqlite:////data/ganjeh.db \
    UPLOAD_DIR=/app/uploads \
    APP_PUBLIC_BASE_URL=http://localhost:8000 \
    ADMIN_USERNAME=admin \
    ADMIN_PASSWORD=admin123 \
    APP_SECRET_KEY=change-me-in-darkube-env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
