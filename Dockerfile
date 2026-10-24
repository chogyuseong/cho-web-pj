FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    DATEMATE_RUNTIME=/data/runtime \
    DATEMATE_BOOTSTRAP_INDEX=1

WORKDIR /app
COPY datemate/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 datemate \
    && mkdir -p /data/runtime /data/backups \
    && chown -R datemate:datemate /data

# Explicit copies prevent local credentials and user data entering the image.
COPY datemate/app ./app
COPY datemate/data ./data
COPY datemate/static ./static

USER datemate
EXPOSE 8080
CMD ["python", "-m", "app.cloud_start"]
