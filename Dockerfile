# NFL fantasy agent: the API (POST /run, GET /trace/<run_id>, GET /health) on port 8000
# and the web UI on port 8080 (open http://localhost:8080).
#
#   docker build -t nfl-agent .
#   docker run -p 8000:8000 -p 8080:8080 nfl-agent                  # no credentials: sample data, rule-based model steps
#   docker run -p 8000:8000 -p 8080:8080 --env-file .env nfl-agent  # with your Meterless (and Zetaris) settings
#
# The browser calls the API on 8000 from the UI's origin, http://localhost:8080 (or
# 127.0.0.1:8080); set UI_ORIGINS if you open the UI under another host name.
#
# Nightshift runs on the host, so from inside the container 127.0.0.1 is the container
# itself: set METERLESS_BASE_URL=http://host.docker.internal:8088 (on Linux also pass
# --add-host=host.docker.internal:host-gateway). No settings or secrets are baked in.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAMPLE_MODE=true \
    PORT=8000 \
    UI_PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY data/sample/ data/sample/
COPY run.py .

# Run as a non-root user; logs/ (traces) and data/memory/ (league memory) are written at run time.
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p logs data/memory \
    && chown -R agent:agent /app
USER agent

EXPOSE 8000 8080
CMD ["python", "run.py", "--serve"]
