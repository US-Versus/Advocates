FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ui.py guides_seed.py ./
ENV APP_DB=/data/app.db
# app.db is NOT baked into the image — it lives on the mounted GCS volume (/data),
# uploaded separately per SETUP_GCP.md. The container refuses to start without it.
CMD ["/bin/sh","-c","[ -f \"$APP_DB\" ] || { echo 'FATAL: app.db not found on /data volume — see SETUP_GCP.md §4'; exit 1; }; uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
