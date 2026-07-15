# AGENTS.md — Plan mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Architectural Constraints

- **Services layer is the isolation boundary**: the `backend/app/services/` layer must remain free of HTTP/FastAPI concepts so it can be called from both the API layer and the eval pipeline without spinning up a server.
- **Prompt templates are a first-class artifact**: changes to `backend/app/prompts/` affect eval baselines in `evals/expected/`. Any prompt change requires a re-run of evals and a deliberate update to expected outputs.
- **Evals are fixture-driven, not live**: the eval pipeline in `evals/` runs against static fixtures, not a live backend, to keep results reproducible. Do not design eval flows that require a running server.
- **Flutter web communicates with backend via HTTP only** — no WebSockets or shared memory. All long-running AI calls should be async and return a job ID for polling, or use SSE.
- **Docker Compose is the integration harness**: `docker-compose.yml` at the root wires frontend, backend, and any supporting services. Local dev outside Docker is fine for single-layer work but integration testing must go through Compose.
- **`docs/data-model.md`** defines the canonical data shapes; Pydantic models in `backend/app/models/` should match it exactly — plan schema changes there first.
