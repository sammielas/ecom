FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Detects installed libraries (FastAPI, SQLAlchemy, psycopg2, httpx, redis)
# and installs the matching OpenTelemetry auto-instrumentation packages for
# each - this is what lets opentelemetry-instrument patch them at startup
# with zero code changes in app.py.
RUN opentelemetry-bootstrap -a install

COPY app.py .

EXPOSE 8000

# opentelemetry-instrument wraps the real start command, patching
# instrumented libraries before uvicorn/the app code even runs.
CMD ["opentelemetry-instrument", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
