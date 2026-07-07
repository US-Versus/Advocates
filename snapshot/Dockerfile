FROM python:3.12-slim
WORKDIR /job
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY snapshot_job.py .
CMD ["python", "snapshot_job.py"]
