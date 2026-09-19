# Aegis Eval web UI.
#
# Uses Next.js standalone output so the runtime image carries only what the
# server needs -- no package manager, no build toolchain.
#
# The base is pinned by digest, not by tag. `node:22-alpine` is a moving
# pointer: two builds of the same commit can sit on different bases, and every
# layer above changes with it. A signature over an image whose inputs nobody
# recorded says when it was built, not what it was built from. Bump this
# deliberately -- that is the point of it being a line in the diff.
FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85 AS deps
WORKDIR /app
# The lockfile is required, not optional: `package-lock.json*` would glob to
# nothing if it were missing and let the build carry on without one.
COPY package.json package-lock.json ./
# `npm ci` and nothing else. The previous `|| npm install` fallback meant a
# lockfile that did not match package.json silently became a fresh resolution
# of whatever was newest that day -- a dependency change nobody reviewed,
# inside a build we then sign. A stale lockfile should stop the build.
RUN npm ci --omit=dev --ignore-scripts

FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
# Baked at build time: Next.js inlines NEXT_PUBLIC_* into the client bundle.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -g 10001 aegis && adduser -D -u 10001 -G aegis aegis

COPY --from=build --chown=aegis:aegis /app/.next/standalone ./
COPY --from=build --chown=aegis:aegis /app/.next/static ./.next/static

USER aegis
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD wget -q --spider http://127.0.0.1:3000/login || exit 1

CMD ["node", "server.js"]
