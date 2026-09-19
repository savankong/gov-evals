# Aegis Eval API.
#
# Built from the repository root, not apps/api, because the evaluation packs
# live at <repo>/packs and the image has to carry them: App Platform mounts no
# volumes, so a pack directory that only exists as a compose bind mount is
# empty in production.
#
# Built on a slim base with no build toolchain in the final image, so the
# runtime carries nothing an evaluation deployment does not need.
FROM python:3.11-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

COPY apps/api/pyproject.toml ./
COPY apps/api/aegis ./aegis
RUN pip install --no-cache-dir --prefix=/install ".[postgres,redis,s3]"

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Runs unprivileged.
RUN useradd --create-home --uid 10001 aegis
WORKDIR /app

COPY --from=build /install /usr/local
COPY apps/api/aegis ./aegis
COPY apps/api/pyproject.toml ./

# The evaluation packs are data the API installs at startup. The image shipped
# without them, relying on the compose bind mount that App Platform has no
# equivalent for, so AEGIS_PACK_DIR named an empty directory in production and
# every pack resolved to nothing: no evaluations, no scenarios, no frameworks,
# on an instance that still reported healthy.
COPY packs /packs

RUN mkdir -p /data/evidence && chown -R aegis:aegis /data /app
USER aegis

ENV AEGIS_DATABASE_URL=sqlite:////data/aegis.db \
    AEGIS_EVIDENCE_PATH=/data/evidence \
    AEGIS_PACK_DIR=/packs

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "aegis.main:app", "--host", "0.0.0.0", "--port", "8000"]
