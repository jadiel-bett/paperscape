# PaperScape Flutter Web Frontend

PaperScape's frontend is a Flutter Web application for the current vertical
slice: select a PDF, upload it to the FastAPI backend, start or reuse a
research-map job, poll for completion, and display grounded findings with source
evidence and limitations.

## Research Atlas visual system

The interface uses a PaperScape “Research Atlas” treatment: paper-like result
surfaces, a page-aware evidence trail, contour-map decoration, and an
IBM-inspired electric blue/cyan/violet palette. The technology badge references
watsonx.ai and Granite without exposing credentials or requiring IBM event logo
assets. The upload surface remains picker-based; the visual treatment does not
claim drag-and-drop support.

## Local Flutter development

From `frontend/`:

```bash
flutter pub get
flutter run -d chrome \
  --dart-define=PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
```

The backend must be running separately at `http://localhost:8000`. If Flutter Web
uses a random development port, add that browser origin to the backend
`CORS_ORIGINS` setting. The backend default allows `http://localhost:3000` and
`http://localhost:8080`; Docker Compose uses `http://localhost:8080`.

Useful checks from `frontend/`:

```bash
dart format lib test
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test --reporter expanded
flutter build web --release \
  --dart-define=PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
```

## API base URL

The frontend reads one non-secret compile-time value:

```text
PAPERSCAPE_API_BASE_URL
```

Default value:

```text
http://localhost:8000/api/v1
```

This value is compiled into Flutter Web assets with `String.fromEnvironment`.
Changing it requires rebuilding the frontend app or Docker image.

Do not pass backend credentials, IBM project IDs, model IDs, database URLs, or
watsonx URLs to Flutter. All watsonx access stays in the backend behind the
`LLMProvider` interface.

## Local Docker Compose

From the repository root:

```bash
docker compose build
docker compose up -d
docker compose ps
```

Local URLs:

- Frontend: `http://localhost:8080`
- Frontend health: `http://localhost:8080/health`
- Backend API: `http://localhost:8000/api/v1`
- Backend health: `http://localhost:8000/api/v1/health`

The browser-visible API URL must use `localhost`, not the Compose service name
`backend`, because browser JavaScript runs on the host browser and cannot resolve
Compose DNS names. Compose service hostnames are only for container-to-container
traffic.

To rebuild with a different non-secret API URL:

```bash
PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1 docker compose build frontend
```

On Windows `cmd.exe`, set environment variables before running Compose, or edit a
root `.env` copied from `.env.example`.

## Credential-free behavior

Docker Compose can start without watsonx credentials. In that mode:

- backend health works;
- frontend health and static serving work;
- PDF upload and selectable-text extraction work;
- research-map generation returns a safe `503` error with
  `detail.code = "generation_unavailable"`;
- no frontend fake-provider mode is available;
- no job is created for the generation-unavailable path.

This is expected for local smoke testing. It proves the upload/extraction and
container wiring without making live model calls.

## Optional live watsonx walkthrough

For a live end-to-end research-map generation demo, configure backend-only values
in the repository-root `.env` file used by Compose:

```text
COMPOSE_WATSONX_API_KEY=...
WATSONX_URL=https://us-south.ml.cloud.ibm.com
COMPOSE_WATSONX_PROJECT_ID=...
```

Compose maps the two `COMPOSE_WATSONX_*` credential names above to the backend's
`WATSONX_*` settings and forwards the documented non-secret values in
`docker-compose.yml`. It does not expose a `GRANITE_MODEL_ID` override; the
Compose backend uses the application's `granite_model_id` default. Direct
backend development may set `GRANITE_MODEL_ID` as documented in
`backend/.env.example`.

Then rebuild/start as needed:

```bash
docker compose up -d --build
```

Open `http://localhost:8080`, upload a small selectable-text PDF, and verify that
the generated research map displays exactly three findings, source evidence with
chunk IDs and one-based pages, limitations, and the canonical disclaimer:

```text
This AI-generated explanation is grounded in the uploaded document but does not replace expert review.
```

## Shutdown and persistence

Stop containers while preserving the named SQLite volume:

```bash
docker compose down
```

Delete containers and the persistent SQLite named volume only when you explicitly
want to destroy local data:

```bash
docker compose down -v
```

The `-v` flag is destructive: it removes the Compose named volume that stores the
backend SQLite database under `/data`.
