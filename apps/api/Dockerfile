# Aegis Eval API.
#
# Built on a slim base with no build toolchain in the final image, so the
# runtime carries nothing an evaluation deployment does not need.
FROM python:3.11-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

COPY pyproject.toml ./
COPY aegis ./aegis
RUN pip install --no-cache-dir --prefix=/install ".[postgres,redis,s3]"

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Runs unprivileged.
RUN useradd --create-home --uid 10001 aegis
WORKDIR /app

COPY --from=build /install /usr/local
COPY aegis ./aegis
COPY pyproject.toml ./

RUN mkdir -p /data/evidence && chown -R aegis:aegis /data /app
USER aegis

ENV AEGIS_DATABASE_URL=sqlite:////data/aegis.db \
    AEGIS_EVIDENCE_PATH=/data/evidence

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "aegis.main:app", "--host", "0.0.0.0", "--port", "8000"]
