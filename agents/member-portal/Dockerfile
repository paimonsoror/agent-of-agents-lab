# Build context is the repository root:
#   docker build -f agents/member-portal/Dockerfile -t maestro/member-portal:<tag> .
# One image, three entrypoints: portal.api (default), portal.consumer, portal.loadgen.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY agents/member-portal/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY agents/member-portal/portal /app/portal
COPY agents/member-portal/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN useradd --uid 10001 --no-create-home portal
USER 10001
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["portal-api"]
