# Sub-task 10 — Docker Compose and End-to-End Vertical-Slice Validation Plan

## 1. Objective

Plan the smallest reliable containerized end-to-end environment for the current
PaperScape vertical slice:

```text
selectable-text PDF
→ Flutter Web upload
→ FastAPI extraction
→ persisted ExtractionResult
→ research-map job creation
→ background processing
→ polling
→ persisted ResearchMap
→ Flutter result display
```

The default automated validation path must not call live watsonx.ai and must not
require real watsonx credentials. This document is a plan only; it does not
implement Dockerfiles, Compose changes, integration tests, environment changes,
or application code.

---

## 2. Pre-flight repository state

### 2.1 Git safety check

The requested pre-flight commands were run:

```bash
git status --short
git log -3 --oneline
```

`git status --short` returned no output, so the working tree was clean before
planning.

Recent commits were:

```text
74cefa3 Merge pull request #7 from jadiel-bett/feat/flutter-vertical-slice
627028d Document Sub-task 8 Bob usage
1876d56 Add Flutter research map vertical slice
```

The repository contains the Flutter vertical-slice and Bob usage-log commits.
The current code/docs use the canonical disclaimer:

```text
This AI-generated explanation is grounded in the uploaded document but does not replace expert review.
```

### 2.2 Sub-task 9 status

The original Sub-task 9 scope was job creation, polling, failure handling,
research-map retrieval, findings display, evidence display, limitations display,
and disclaimer display. That scope was completed inside the expanded Sub-task 8
Flutter vertical-slice implementation. Sub-task 10 must not recreate another
polling screen, map screen, API client, controller, or frontend workflow.

Current implementation evidence includes:

- `frontend/lib/features/research_map/presentation/research_map_controller.dart`
  for upload, job creation, polling, retry, reset, failure handling, and map
  retrieval orchestration;
- `frontend/lib/features/research_map/presentation/research_map_screen.dart` for
  research question, findings, confidence labels, page/chunk provenance,
  selectable evidence, limitations, disclaimer, retry, and start-over display;
- `frontend/lib/features/research_map/data/dto/research_map.dart` for the
  canonical disclaimer and research-map DTO validation.

Historical Sub-task 9 requirements must be preserved and superseded explicitly in
future documentation updates; do not silently rewrite the old task description.

---

## 3. Current containerization assessment

### 3.1 Current root `docker-compose.yml`

The current root Compose file is a stub with `backend` and `frontend` services.
It references `backend/Dockerfile` and `frontend/Dockerfile`, maps backend
`8000:8000`, maps frontend `8080:80`, reads root `.env` for backend, and has no
healthchecks, volumes, frontend build args, restart policy, Docker database path,
or Docker-specific CORS override.

### 3.2 Backend Dockerfile state

`backend/Dockerfile` does not exist. Therefore the backend currently has no
containerized definition for Python image version, system packages, dependency
caching, non-root runtime user, writable database directory, Uvicorn startup, or
image-level secret exclusion.

### 3.3 Frontend Dockerfile and nginx state

The repository currently has no `frontend/Dockerfile`, no `frontend/nginx.conf`,
no frontend runtime nginx configuration, and no SPA fallback configuration.

### 3.4 Current `.dockerignore` files

No root, backend, or frontend `.dockerignore` files were found. This is a risk
because local/generated directories exist in the working tree, including root
`.env`, `.git/`, `.bob/`, `.pytest_cache/`, `backend/.venv/`,
`backend/.pytest_cache/`, `frontend/.dart_tool/`, `frontend/build/`, and
`frontend/.idea/`.

Sub-task 10 should add scoped ignore files for the actual build contexts:

- `backend/.dockerignore`
- `frontend/.dockerignore`

A root `.dockerignore` is optional if Compose continues to use `./backend` and
`./frontend` as build contexts.

### 3.5 Backend startup command

`backend/app/main.py` exposes a module-level app:

```python
app = create_app()
```

The planned backend container command should be:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Single-worker behavior is required because duplicate active-job creation is
protected by an in-process `threading.Lock`, FastAPI `BackgroundTasks` are
in-process, SQLite is the persistence layer, and no Redis/Celery/separate worker
is in scope.

### 3.6 Python runtime baseline

Use the verified backend runtime baseline:

```dockerfile
FROM python:3.12.10-slim-bookworm
```

The backend has already been verified on Python 3.12.10 with 422 backend tests
passing, the offline evaluation passing, and pinned Docling, PyMuPDF, and IBM SDK
dependencies installed successfully. Python 3.11 remains technically possible,
but choosing it would introduce a second runtime baseline and require the full
backend test suite and offline evaluation to be rerun inside that image, with the
runtime divergence documented.

### 3.7 Backend non-root user

No backend image exists, so no non-root runtime user exists yet. Sub-task 10
should create an explicit user and group:

```dockerfile
RUN groupadd --gid 10001 paperscape \
    && useradd \
       --uid 10001 \
       --gid 10001 \
       --create-home \
       --shell /usr/sbin/nologin \
       paperscape \
    && install -d -o 10001 -g 10001 /data
```

Runtime verification must include:

```bash
docker compose exec backend id
docker compose exec backend test -w /data
```

### 3.8 Secret-copy risk

A root `.env` file exists locally and is ignored by Git/Bob, but Docker build
contexts can still include ignored files unless `.dockerignore` excludes them.
Sub-task 10 must ensure `.env` and `.env.*` are excluded from backend and
frontend image contexts, no Dockerfile copies `.env` files, credentials are never
passed as frontend build arguments, watsonx credentials remain backend runtime
environment only, examples contain placeholders only, and build logs do not print
secrets.

### 3.9 Current SQLite path behavior

`backend/app/config.py` accepts `sqlite:///:memory:` and `sqlite:///` followed by
a non-empty path. `Settings.db_path` strips the prefix and returns the filesystem
path. Important examples:

```text
sqlite:///./paperscape.db      -> ./paperscape.db
sqlite:///data/paperscape.db   -> data/paperscape.db
sqlite:////data/paperscape.db  -> /data/paperscape.db
```

The current validator accepts an absolute Linux container path using:

```text
sqlite:////data/paperscape.db
```

`backend/app/database.py` opens SQLite with `sqlite3.connect(db_path)`, sets
`row_factory = sqlite3.Row`, enables foreign keys, enables WAL for file-backed
databases, creates `jobs`, `extractions`, and `research_maps`, and resets stale
`pending` and `running` jobs to `failed` with `server_restart` on startup.

### 3.10 Current CORS defaults

`backend/app/config.py` defaults to:

```text
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

`backend/app/main.py` configures `CORSMiddleware` with
`allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]`.
Docker-local frontend access at `http://localhost:8080` therefore requires at
least:

```text
CORS_ORIGINS=http://localhost:8080
```

Wildcard CORS should not be used while credentials are allowed.

### 3.11 Current frontend compile-time API URL behavior

`frontend/lib/app/app_config.dart` uses `String.fromEnvironment` with the current
configuration name:

```text
PAPERSCAPE_API_BASE_URL
```

and default:

```text
http://localhost:8000/api/v1
```

The frontend API client appends route paths under that base URL. Do not
reintroduce the obsolete `BACKEND_URL` setting. For local Compose, the Flutter
Web image should be built with:

```text
PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
```

because browser JavaScript normally cannot resolve the Compose service hostname
`backend`. Changing this value requires rebuilding the Flutter Web image because
it is compile-time configuration.

### 3.12 Current health endpoint

`backend/app/routers/health.py` exposes:

```text
GET /api/v1/health -> {"status":"ok"}
```

This should be used for the backend container healthcheck.

### 3.13 Docker availability

Docker is available in the development environment:

```text
Docker version 28.5.1, build e180ab8
Docker Compose version v2.40.3-desktop.1
```

`docker compose config` currently succeeds against the stub. `docker compose
build` currently fails because referenced Dockerfiles are absent. This is an
expected Sub-task 10 implementation target, not a planning blocker.

---

## 4. Corrected Docker Compose topology

Use the minimal topology:

- `backend`
- `frontend`

Do not add Redis, Celery, PostgreSQL, a separate worker service, a reverse-proxy
service beyond the frontend nginx container, or live watsonx dependencies for
automated tests.

### 4.1 Backend service design

| Property | Plan |
|---|---|
| build context | `./backend` |
| Dockerfile | `Dockerfile` |
| container port | `8000` |
| host port | `8000` |
| command | Dockerfile `CMD` running Uvicorn with `--workers 1` |
| database env | `DATABASE_URL=sqlite:////data/paperscape.db` |
| CORS env | `CORS_ORIGINS=http://localhost:8080` |
| volumes | named volume mounted at `/data` |
| healthcheck | Python stdlib request to `/api/v1/health` |
| restart | `unless-stopped` for local app-like behavior |
| depends_on | none |
| network | default Compose network |

Compose should not invent a second Granite model default. It should omit
`GRANITE_MODEL_ID` and rely on `Settings.granite_model_id`, or interpolate the
variable without adding a different default.

### 4.2 Frontend service design

| Property | Plan |
|---|---|
| build context | `./frontend` |
| Dockerfile | `Dockerfile` |
| build arg | `PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1` |
| runtime image | nginx unprivileged image where practical |
| container port | `8080` when using unprivileged nginx |
| host port | `8080` |
| healthcheck | `http://127.0.0.1:8080/health` |
| restart | `unless-stopped` |
| depends_on | backend `service_healthy` |
| network | default Compose network |

The frontend container serves static assets and must not receive backend secrets,
watsonx values, model configuration, database configuration, or prompts.

### 4.3 Named volume

Use a named volume for backend SQLite persistence:

```yaml
volumes:
  paperscape_backend_data:
```

Default cleanup preserves this volume:

```bash
docker compose down
```

Destructive cleanup must be explicit:

```bash
docker compose down -v
```

Document that `-v` deletes the persistent SQLite database.

---

## 5. Backend container plan

### 5.1 Dockerfile design

Planned `backend/Dockerfile`:

```dockerfile
FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Start minimal. Retain optional native packages only when build/runtime evidence
# shows Docling/PyMuPDF need them in this image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

RUN groupadd --gid 10001 paperscape \
    && useradd \
       --uid 10001 \
       --gid 10001 \
       --create-home \
       --shell /usr/sbin/nologin \
       paperscape \
    && install -d -o 10001 -g 10001 /data

COPY app ./app

USER paperscape

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

Potential native packages to add only if verified by build/runtime failures:

- `libgl1`
- `libglib2.0-0`
- `libgomp1`
- `libstdc++6`

Do not install `curl` merely for healthchecks because the planned backend
healthcheck uses Python's standard library.

### 5.2 Backend `.dockerignore`

Planned `backend/.dockerignore`:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
*.db
*.db-wal
*.db-shm
*.sqlite3
.idea/
.vscode/
*.log
logs/
```

Do not require `.env.example` inside the backend runtime image unless the
Dockerfile explicitly needs it. The runtime application should receive
configuration from environment variables, not copied example files.

### 5.3 Backend runtime requirements

Implementation must verify Python 3.12.10 in the image, non-root execution,
`/data` writability, SQLite `.db`/`-wal`/`-shm` creation under `/data`, one
Uvicorn worker, health endpoint success, database initialization during FastAPI
lifespan, no `.env` copied into the image, and no credentials baked into image
layers.

---

## 6. SQLite ownership and persistence plan

Use:

```text
DATABASE_URL=sqlite:////data/paperscape.db
```

This is accepted by current `Settings` validation and resolves to
`/data/paperscape.db`.

Runtime files expected:

```text
/data/paperscape.db
/data/paperscape.db-wal
/data/paperscape.db-shm
```

Requirements:

- current application code does not create the database parent directory;
- `sqlite3.connect()` expects the parent directory to exist for file-backed
  databases;
- `/data` must be created before Uvicorn starts;
- `/data` must be writable by UID/GID `10001`.
- WAL mode must be enabled for the file-backed database.
- database files must persist across container recreation via the named volume.
- application source under `/app` must not be used as a persistent DB directory.
- automated integration tests must use pytest temporary SQLite files, not the
  Compose named volume.
- DB, WAL, and SHM files must all be created under the mounted `/data` volume.

Runtime checks must include:

```bash
docker compose exec backend id
docker compose exec backend test -w /data
```

Implementation must also verify that the database exists and WAL mode is enabled
inside the mounted volume after startup/upload.

---

## 7. Frontend container plan

### 7.1 Flutter builder image gate

Before relying on the Flutter SDK image, implementation must run:

```bash
docker pull ghcr.io/cirruslabs/flutter:3.24.5
```

Do not use an unpinned `latest` tag. If the pinned image is unavailable or has
architecture problems, use a reproducible official Flutter 3.24.5 SDK
installation strategy instead, and record the selected image or SDK archive
source. Where practical, record the resolved image digest.

### 7.2 Dockerfile design

Planned `frontend/Dockerfile`:

```dockerfile
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
```

Do not assert that `wget` is available until implementation verifies the selected
runtime image. Implementation must inspect the selected
`nginxinc/nginx-unprivileged:1.27-alpine` runtime image using a temporary
container. If `wget` exists, use:

```bash
wget --quiet --tries=1 --spider http://127.0.0.1:8080/health
```

If `wget` is absent, use another command that is actually available in the image
or add the smallest justified healthcheck tool. Do not switch to a root nginx
image merely for healthchecking.

### 7.3 nginx design

Planned `frontend/nginx.conf`:

```nginx
server {
    listen 8080;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location = /health {
        access_log off;
        add_header Content-Type text/plain;
        return 200 "ok\n";
    }
}
```

The `/health` route is used for the container healthcheck. The root URL remains a
separate smoke assertion to prove Flutter HTML loads.

### 7.4 Frontend `.dockerignore`

Planned `frontend/.dockerignore`:

```gitignore
.env
.env.*
.dart_tool/
build/
.idea/
*.iml
.flutter-plugins
.flutter-plugins-dependencies
.pub-cache/
.vscode/
*.log
```

Do not require `.env.example` inside the frontend runtime image unless the
Dockerfile explicitly needs it. No backend secrets or backend runtime settings
belong in frontend image layers or generated assets.

---

## 8. CORS plan

Minimum Docker-local backend setting:

```text
CORS_ORIGINS=http://localhost:8080
```

Flutter development origins can vary. Developers should serve the built frontend
from `http://localhost:8080`, run Flutter Web on a fixed allowed port, or add the
actual Flutter dev origin to `CORS_ORIGINS`. Production should replace local HTTP
origins with deployed HTTPS origins and avoid mixed content.

CORS is enforced by the browser using the page origin. Compose DNS is relevant
only to container-to-container traffic. Therefore the browser-visible backend URL
is `http://localhost:8000/api/v1`, the frontend browser origin is
`http://localhost:8080`, and the internal Compose hostname `backend` is not used
by Flutter Web browser code.

---

## 9. Environment and credential strategy

Sub-task 10 must clearly distinguish:

- root `.env`: local Docker Compose interpolation source; ignored; never copied
  into images;
- root `.env.example`: committed placeholder template for Compose/local use;
- `backend/.env.example`: committed placeholder template for direct backend
  development;
- `PAPERSCAPE_API_BASE_URL`: non-secret frontend build argument compiled into
  Flutter Web assets.

| Setting | Classification | Consumer | Notes |
|---|---|---|---|
| `WATSONX_API_KEY` | required secret for optional live generation | backend only | Must never reach Flutter. |
| `WATSONX_URL` | required non-secret for optional live generation | backend only | Use current examples/settings only. |
| `WATSONX_PROJECT_ID` | required non-secret identifier for optional live generation | backend only | Do not expose to Flutter. |
| `GRANITE_MODEL_ID` | optional backend model configuration | backend only | Do not invent a Compose default. |
| `DATABASE_URL` | required non-secret runtime config | backend only | Compose value should be `sqlite:////data/paperscape.db`. |
| `UPLOAD_MAX_BYTES` | optional config | backend and mirrored by frontend client limit | Backend remains authoritative. |
| `CORS_ORIGINS` | required non-secret browser security config | backend only | Use exact origins. |
| `PAPERSCAPE_API_BASE_URL` | required non-secret frontend build config | frontend only | Rebuild frontend image when changed. |

### 9.1 Credential-free startup verification gate

Current code-supported behavior is:

- missing or empty `WATSONX_API_KEY` is accepted by `Settings`;
- missing or empty `WATSONX_PROJECT_ID` is accepted by `Settings`;
- the real `WatsonxProvider` is constructed lazily, not during import,
  `create_app()`, health checks, upload, polling, or map retrieval;
- the app should start without generation credentials;
- research-map job creation should return HTTP `503` with
  `detail.code = "generation_unavailable"` when no runner factory exists;
- no job should be created in this `generation_unavailable` branch.

Keep real Docker startup as an implementation verification gate rather than
claiming it has already been container-tested. Implementation must still verify
watsonx defaults, empty-string validation, `create_app()` startup behavior, lazy
provider construction, and the safe `generation_unavailable` path inside the
containerized environment.

Required credential-free Compose smoke commands:

```bash
docker compose up -d
docker compose ps
curl -fsS http://localhost:8000/api/v1/health
```

If startup fails because settings reject missing/empty generation credentials,
that is a verified Docker blocker. The smallest backend correction should make
credentials backend-only, allow health/upload startup without credentials,
require credentials only for real provider construction/generation, return the
existing curated `generation_unavailable` response, and avoid fake or placeholder
credentials.

---

## 10. Three validation tiers

### 10.1 Tier A — automated backend integration

No live network and no real credentials.

```text
PDF HTTP upload
→ real extraction
→ fake LLMProvider
→ real ResearchMapService
→ real ResearchMapJobRunner
→ SQLite persistence
→ job status
→ map retrieval
```

### 10.2 Tier B — credential-free Compose smoke

No watsonx credentials. This tier verifies backend/frontend startup,
healthchecks, frontend HTML, upload/extraction, curated `generation_unavailable`,
credential-free startup, and logs without credentials. It does not prove
successful research-map generation or rendered map results.

### 10.3 Tier C — optional live browser end-to-end

Requires valid backend-only watsonx credentials. This tier covers Flutter
selection, upload, extraction, job creation, polling, real watsonx generation,
persisted research map, and displayed results. It is optional and manual. Do not
add a runtime fake-provider mode to production application code unless separately
approved.

---

## 11. Automated integration-test design

Create:

```text
backend/tests/integration/test_pipeline.py
```

`backend/tests/integration/__init__.py` already exists.

### 11.1 PDF fixture generation

Generate a tiny selectable-text PDF in a pytest fixture using PyMuPDF. The PDF
must be deterministic, selectable text, small, at least one page, sufficient to
produce non-empty extraction chunks, synthetic, and license-safe. Do not require
a committed binary fixture by default.

### 11.2 Fake `LLMProvider`

Use an injected fake `LLMProvider`, not a fake `ResearchMapService`. The fake
provider must receive the real prompt, identify supplied paper-context chunk IDs,
return deterministic valid structured JSON, reference real extracted chunk IDs,
require no network, require no watsonx credentials, and expose no secrets.

The current provider interface is:

```python
def generate(
    self,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str: ...
```

The fake must receive the real prompt generated by `ResearchMapService`. It must
locate the serialized paper-context section inserted in place of the prompt
template sentinel:

```text
__PAPER_CONTEXT_JSON__
```

The inserted context contains chunk objects with fields such as:

- `chunk_id`
- `page`
- `section`
- `text`

The fake must return deterministic JSON matching the current internal
`ResearchMapService` response schema, not the public `ResearchMap` model. The
response must contain:

- `research_question` with `statement` and `evidence`;
- exactly three `findings`;
- each finding's `statement`, `evidence`, and `confidence`;
- `limitations` entries with grounded evidence.

Use only internal confidence values currently accepted by the service:

- `high`
- `partial`

Do not return `uncertain` from the fake provider because the current internal
service schema rejects it, even though the public backend/frontend model can
represent `uncertain`. Evidence must reference real chunk IDs, pages, and
excerpts from the supplied prompt context so the real grounding validator
succeeds without a corrective retry.

This exercises real prompt construction, model-response parsing, evidence
validation, `ResearchMapService`, `ResearchMapJobRunner`, repositories, routes,
and temporary SQLite persistence.

### 11.3 Temporary SQLite

Use pytest `tmp_path` and explicit settings with `_env_file=None`, for example:

```python
Settings(
    _env_file=None,
    database_url=f"sqlite:///{tmp_path / 'pipeline.db'}",
    cors_origins="http://localhost:8080",
)
```

### 11.4 Successful pipeline test

Required flow:

1. Upload PDF through `POST /api/v1/papers`.
2. Assert `201` and extraction metadata.
3. Create research-map job.
4. Assert `202` and job ID.
5. Execute/control background job deterministically without sleeps.
6. Poll job status.
7. Assert `succeeded`.
8. Retrieve research map.
9. Assert correct `paper_id`, non-empty `research_question`, exactly three
   findings, at least one evidence item per finding, one-based page provenance,
   non-empty limitations, and the canonical disclaimer.
10. Confirm persisted extraction, job, and map can be read back.

### 11.5 Failure-path integration test

Add one focused failure-path test using a fake provider that fails through the
real job runner path:

1. Fake `LLMProvider.generate()` raises `LLMProviderError`.
2. The real `ResearchMapJobRunner` catches it.
3. The persisted and public job error is exactly `llm_provider_error`.
4. The failed job response remains frontend-compatible.
5. Research-map retrieval returns HTTP `404` with
   `detail.code = "map_not_found"`.
6. The raw fake-provider exception message is not exposed.
7. No real network or credentials are used.

Also document, but do not require as the main integration failure test, that
invalid model output after the corrective attempt produces `map_generation_failed`.
Do not use a generic or invented error code.

---

## 12. Container smoke validation

### 12.1 Configuration and build

```bash
docker compose config
docker pull ghcr.io/cirruslabs/flutter:3.24.5
docker compose build
```

Before finalizing the frontend healthcheck, implementation must inspect the
selected nginx runtime image with a temporary container to confirm which
healthcheck command is available. This inspection must not be confused with the
default application runtime and should not switch to a root nginx image merely
for healthchecking.

### 12.2 Startup and health

```bash
docker compose up -d
docker compose ps
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8080/health
curl -fsSI http://localhost:8080/
```

### 12.3 Runtime user and database checks

```bash
docker compose exec backend id
docker compose exec backend test -w /data
```

After startup/upload, verify SQLite exists in the named volume, WAL mode is
enabled, and `/data/paperscape.db`, `/data/paperscape.db-wal`, and
`/data/paperscape.db-shm` can be created by the non-root user.

### 12.4 Credential-free upload and generation-unavailable check

With no watsonx credentials configured, upload a small selectable-text PDF to
`POST /api/v1/papers`, assert upload/extraction succeeds, call
`POST /api/v1/papers/{paper_id}/research-map-jobs`, and assert the documented
curated `generation_unavailable` error with no raw exception or credential leak.

### 12.5 Logs and cleanup

```bash
docker compose logs --no-color backend
docker compose logs --no-color frontend
docker compose down
```

Expected: no credentials in logs, no stack traces during healthy smoke flow, and
`docker compose down` preserves the named volume. Optional destructive cleanup:

```bash
docker compose down -v
```

---

## 13. Optional live browser walkthrough

Only run this tier with valid backend-only watsonx credentials. Open
`http://localhost:8080` with a small selectable-text research PDF and verify the
frontend loads, PDF can be selected, filename and size appear, upload succeeds,
extraction metadata appears, job begins, pending/running state appears when
processing is not instantaneous, map loads after success, research question
appears, exactly three findings appear, evidence excerpts are selectable, page
numbers are one-based, chunk IDs appear, confidence labels appear, limitations
appear, the canonical disclaimer appears exactly, retry/start-over paths are
usable, and narrow plus 1280×800 layouts do not overflow.

---

## 14. Acceptance-criteria reconciliation

The original `docs/vertical-slice-plan.md` has historical drift. Sub-task 10
implementation should document corrections rather than silently rewriting old
requirements. A future modification should add a clearly marked
status/supersession section recording Sub-task 9 completion inside expanded
Sub-task 8, stale upload route/status, stale duplicate-job behavior, stale
frontend configuration name, stale disclaimer, current verified test baselines,
and Docker implementation ownership by Sub-task 10.

| Area | Stale wording | Correct current wording |
|---|---|---|
| Upload route | `POST /api/v1/papers/upload` | `POST /api/v1/papers` |
| Upload success status | `202 Accepted` | `201 Created` |
| Duplicate active job | `409 Conflict` | Idempotent `202 Accepted` returning existing active job |
| Frontend config | `BACKEND_URL` | `PAPERSCAPE_API_BASE_URL` |
| Disclaimer | older shorter wording | canonical expert-review disclaimer |
| Frontend architecture | old `api/` and `screens/` layout | current `frontend/lib/app` and `frontend/lib/features/research_map` layout |
| Test totals | older estimates | record actual collected/passed totals; current verified baseline was backend 422 and frontend 42 |
| Eval baseline | planned future eval | current offline research-map evaluation passed |
| Docker | assumed/stubbed | Dockerfiles absent and Compose stubbed; owned by Sub-task 10 |

---

## 15. Expected files

### 15.1 Likely create during implementation

```text
backend/Dockerfile
backend/.dockerignore
frontend/Dockerfile
frontend/nginx.conf
frontend/.dockerignore
backend/tests/integration/test_pipeline.py
docs/subtask-10-docker-compose-e2e-plan.md
```

Do not list a binary PDF fixture by default because the integration test should
generate its tiny selectable-text PDF programmatically.

### 15.2 Likely modify during implementation

```text
docker-compose.yml
.env.example
backend/.env.example
frontend/README.md
docs/vertical-slice-plan.md
```

No backend application behavior should be changed merely to fit Docker unless a
verified blocker appears, such as credential-free startup failing.

---

## 16. Verification commands

### 16.1 Backend

Use the established backend virtual environment path on Windows where
appropriate. Record actual collected and passed totals rather than hardcoding a
test count.

```bash
python -m pip check
python -m pytest --collect-only backend/tests
python -m pytest backend/tests
python -m pytest backend/tests/integration/test_pipeline.py
python evals/run_evals.py
```

Windows backend venv examples:

```cmd
backend\.venv\Scripts\python.exe -m pip check
backend\.venv\Scripts\python.exe -m pytest backend\tests --collect-only -q
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_pipeline.py -q
backend\.venv\Scripts\python.exe evals\run_evals.py
```

For commands that import `app` directly, either run them after changing to
`backend/`, or set `PYTHONPATH` to the backend directory explicitly. Prefer
PowerShell-safe examples such as:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -c "from app.config import Settings; print(Settings(_env_file=None).database_url)"
Pop-Location
```

or from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
backend\.venv\Scripts\python.exe -c "from app.config import Settings; print(Settings(_env_file=None).database_url)"
Remove-Item Env:PYTHONPATH
```

Do not rely on fragile `cd backend && ...` syntax in PowerShell examples.

### 16.2 Frontend

From `frontend/`:

```bash
flutter pub get
dart format lib test
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build web --release --dart-define=PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
```

The first `dart format` command formats. The second verifies that nothing remains
unformatted.

### 16.3 Docker

```bash
docker compose config
docker pull ghcr.io/cirruslabs/flutter:3.24.5
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8080/health
curl -fsSI http://localhost:8080/
docker compose exec backend id
docker compose exec backend test -w /data
docker compose logs --no-color backend
docker compose logs --no-color frontend
docker compose down
```

Optional destructive cleanup:

```bash
docker compose down -v
```

### 16.4 Repository hygiene

```bash
git diff --check
git status --short
```

Secret scan options:

```bash
git grep -n "WATSONX_API_KEY=.*[^-]" -- . ":!*.example"
git grep -n "your-watsonx-api-key-here\|your-watsonx-project-id-here"
```

---

## 17. Docker acceptance checks

Sub-task 10 implementation is acceptable when these checks pass or any deviation
is documented with a verified reason:

- `docker compose config` succeeds.
- Flutter builder image gate succeeds or a reproducible pinned fallback is used.
- backend image builds.
- frontend image builds.
- both services become healthy.
- backend runs as non-root.
- `/data` is writable.
- SQLite database exists in the named volume after startup/upload.
- WAL mode is enabled and sidecar files can be created.
- backend health returns `{"status":"ok"}`.
- frontend `/health` returns success.
- frontend root returns HTML.
- credential-free upload/extraction succeeds.
- credential-free generation request returns curated `generation_unavailable`.
- logs contain no credentials.
- `docker compose down` preserves the volume.
- `docker compose down -v` removes the volume only when explicitly requested.
- automated backend integration test passes without network or credentials.
- optional live browser E2E is documented separately and remains manual.

---

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Docling image size | Keep topology minimal; cache pip layer; avoid unnecessary system packages. |
| Native dependency failures | Start minimal and retain optional packages only after build/runtime evidence. |
| Docker build time | Copy dependency manifests before app source; use `.dockerignore`; pin images. |
| Flutter SDK image unavailable | Gate with `docker pull`; use reproducible official Flutter 3.24.5 SDK fallback if needed. |
| Browser-visible backend URL mismatch | Compile Flutter with `http://localhost:8000/api/v1`, not Compose hostname. |
| CORS mismatch | Set exact `CORS_ORIGINS=http://localhost:8080`; document dev/prod replacements. |
| SQLite volume permissions | Explicit UID/GID, `/data` ownership, runtime write checks. |
| WAL sidecar file permissions | Verify `.db`, `-wal`, and `-shm` creation under `/data`. |
| BackgroundTasks process lifetime | Use one Uvicorn worker; rely on startup reset for stale pending/running jobs. |
| Container restart during active jobs | Startup recovery marks stale jobs failed with `server_restart`; frontend retry path handles failure. |
| Stale pending/running jobs | Already reset by `init_db`; preserve test coverage. |
| watsonx credentials | Backend-only env vars; optional live tier; no frontend exposure. |
| Credential-free startup failure | Treat as implementation gate; make credentials optional for health/upload startup only if verified blocker appears. |
| Live-network dependence | Default automated integration uses fake `LLMProvider`; live path manual only. |
| Windows/Unix line endings | Run `git diff --check`; keep scripts shell-portable where practical. |
| nginx SPA routing | Use `try_files $uri $uri/ /index.html`. |
| Docker Desktop resource limits | Keep services minimal; document Docling/Flutter build resource needs if observed. |

---

## 19. Scope exclusions

Keep out of Sub-task 10:

- cloud deployment
- Kubernetes
- Terraform
- CI/CD pipelines
- authentication
- OCR
- Redis
- Celery
- separate workers
- PostgreSQL
- monitoring platform integration
- production TLS termination
- audience adaptation
- narration
- visual abstracts
- export
- embeddings
- vector search

---

## 20. Implementation order

1. Create this plan document.
2. Add backend `.dockerignore`.
3. Add backend Dockerfile with Python 3.12.10 and non-root user.
4. Add frontend `.dockerignore`.
5. Verify/pin Flutter builder image or implement reproducible SDK fallback.
6. Add frontend nginx config.
7. Add frontend Dockerfile.
8. Replace Compose stub with backend/frontend services, named volume,
   healthchecks, and build args.
9. Reconcile `.env.example` and `backend/.env.example` with placeholders and
   source-of-truth notes.
10. Add backend integration pipeline test using generated PDF and fake
    `LLMProvider`.
11. Update `frontend/README.md` with Docker/API URL instructions.
12. Add a clearly marked supersession section to `docs/vertical-slice-plan.md`.
13. Run backend verification.
14. Run frontend verification.
15. Run Docker config/build/startup smoke checks.
16. Run repository hygiene checks.
17. Document any verified deviations or blockers.

---

## 21. Rollback strategy

Rollback Docker-related work by reverting:

```text
docker-compose.yml
backend/Dockerfile
backend/.dockerignore
frontend/Dockerfile
frontend/nginx.conf
frontend/.dockerignore
```

Rollback test/documentation additions by reverting:

```text
backend/tests/integration/test_pipeline.py
docs/subtask-10-docker-compose-e2e-plan.md
.env.example
backend/.env.example
frontend/README.md
docs/vertical-slice-plan.md
```

Clean containers without deleting persistent data:

```bash
docker compose down
```

Only remove the SQLite named volume when explicitly intended:

```bash
docker compose down -v
```

---

## 22. Final status statements

1. Original Sub-task 9 is fully covered by the expanded Sub-task 8.
2. No functional Sub-task 9 gap remains.
3. The repository is ready for Sub-task 10 implementation after this plan audit.
4. Credential-free backend startup remains an implementation verification gate
   until tested.