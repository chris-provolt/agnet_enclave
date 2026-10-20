# One image for every Python service in the Enclave. The compose file picks the
# entrypoint per service. Pinned base; rotate the digest when you rebuild.
FROM python:3.13-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
RUN groupadd --gid 1000 enclave && useradd --uid 1000 --gid 1000 --create-home enclave
COPY --from=builder /install /usr/local
WORKDIR /app
COPY enclave ./enclave
COPY agents ./agents
COPY recorder ./recorder
COPY dashboard ./dashboard
COPY scripts ./scripts
COPY config ./config
USER enclave
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('HEALTH_PORT','8000') + '/health', timeout=3)"
CMD ["python", "-m", "agents.main"]
