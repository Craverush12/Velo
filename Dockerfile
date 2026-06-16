FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    APP_ENV=production \
    STORAGE_PATH=/data

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Playwright (added for scripts/outbound_browser_runner.py) needs its browser
# binary + OS deps downloaded separately from the pip package itself.
# --with-deps pulls the apt packages Chromium needs; must run as root (still
# the active user at this point in the build, before USER app below).
RUN playwright install --with-deps chromium

COPY . .

RUN mkdir -p /data \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/health', timeout=3).read()"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
