# syntax=docker/dockerfile:1
#
# Production frontend: Vite build -> static files served by unprivileged nginx, which also
# reverse-proxies /api and /health to FastAPI on the SAME origin. Build context: frontend/.
# Development is unchanged: `npm run dev` (Vite dev server) never runs in this image.

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# "/" = same origin as the page (see src/config.ts). VITE_* values end up in the public JS
# bundle, so never put secrets in them; this one is just a routing choice.
ENV VITE_API_BASE_URL=/
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
# The base image already runs as the unprivileged `nginx` user (uid 101) on port 8080.
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
