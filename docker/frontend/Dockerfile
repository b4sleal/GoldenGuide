# React frontend and same-origin API proxy. No Python runtime or backend dependencies.

# Stage 1: build the React app (frontend/). Only the lockfile's exact versions are installed.
FROM node:24-alpine AS development
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM development AS build
RUN pnpm build

# Stage 2: serve the built files. Pin the existing local Nginx image by digest; updates are deliberate build changes.
FROM nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2 AS proxy
COPY docker/frontend/default.conf.template /etc/nginx/templates/default.conf.template

# Development keeps the same public proxy; only UI requests go to Vite (including its HMR socket).
FROM proxy AS development-proxy
COPY docker/frontend/dev.conf.template /etc/nginx/templates/default.conf.template

# Keep runtime last so a plain docker build still produces the production image.
FROM proxy AS runtime
COPY --from=build /app/dist/ /usr/share/nginx/html/
