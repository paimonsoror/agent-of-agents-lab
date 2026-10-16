# Build context is the repository root:
#   docker build -f agents/maestro/Dockerfile -t maestro/maestro:<tag> .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY agents/common /app/common
RUN pip install /app/common

COPY agents/maestro/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY agents/maestro /app/svc
COPY skills /app/skills

ENV SKILLS_DIR=/app/skills
WORKDIR /app/svc
EXPOSE 8000
CMD ["python", "main.py"]
