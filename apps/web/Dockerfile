# Build the SPA, then serve it from nginx (also proxies /v1 to the API).
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Unprivileged nginx: runs as non-root (uid 101) on port 8080. Fixes Trivy DS-0002.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
