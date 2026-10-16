# Build context is the repository root:
#   docker build -f agents/fleet-console/Dockerfile -t maestro/fleet-console:<tag> .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY agents/common /app/common
RUN pip install /app/common

COPY agents/fleet-console/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY agents/fleet-console /app/svc
WORKDIR /app/svc

ENV SERVICE_NAME=console
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
