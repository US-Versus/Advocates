FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ui.py monitor.py guides_seed.py ./
ENV APP_DB=/data/app.db
# app.db is NOT baked into the image — it lives on the mounted GCS volume (/data),
# uploaded separately per SETUP_GCP.md. The container refuses to start without it.
# Wait up to 30s for the gcsfuse volume to become consistent (the object can be
# invisible for a beat on a cold mount) before the fail-safe fires — avoids a
# spurious startup abort while still refusing to start if app.db is truly absent.
CMD ["/bin/sh","-c","i=0; while [ ! -f \"$APP_DB\" ] && [ $i -lt 30 ]; do i=$((i+1)); echo \"waiting for $APP_DB on the volume ($i/30)\"; sleep 1; done; [ -f \"$APP_DB\" ] || { echo 'FATAL: app.db not found on /data volume — see SETUP_GCP.md §4'; exit 1; }; uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
