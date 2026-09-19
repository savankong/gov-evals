# Aegis Eval web UI.
#
# Uses Next.js standalone output so the runtime image carries only what the
# server needs -- no package manager, no build toolchain.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts || npm install --omit=dev --ignore-scripts

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY . .
# Baked at build time: Next.js inlines NEXT_PUBLIC_* into the client bundle.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:22-alpine
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
