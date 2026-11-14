# TagAlong web app for Google Cloud Run. Run scripts/prepare_deploy.sh first to fill deploy_data/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TAGALONG_DATA_DIR=/app/deploy_data \
    TAGALONG_OUT_DIR=/app/deploy_data/out

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The repo (code, library/, devices/) together with deploy_data/ (photos, manuals, figure crops)
COPY . .
RUN test -d deploy_data/chairs || (echo "deploy_data/ is empty: run scripts/prepare_deploy.sh first" >&2; exit 1)

# Cloud Run sets PORT (8080); the app reads it and listens on 0.0.0.0.
CMD ["python", "-m", "app"]
