FROM ghcr.io/cirruslabs/flutter:3.24.5 AS build

WORKDIR /app

COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

ARG PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
RUN flutter build web --release \
    --dart-define=PAPERSCAPE_API_BASE_URL=${PAPERSCAPE_API_BASE_URL}

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build/web /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/health || exit 1