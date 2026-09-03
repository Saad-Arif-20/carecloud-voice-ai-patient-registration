FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# Overridden by Railway/Render's env vars in production; this default keeps `docker run`
# usable standalone. Mount a persistent volume at /data in production so patient records
# survive redeploys, not just process restarts.
ENV DATABASE_PATH=/data/patients.db
ENV LOG_FILE=/data/agent_calls.log
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
