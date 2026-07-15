# AGENTS.md — Agent (coding) mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Coding Rules

### Backend
- **Services must be framework-agnostic**: `backend/app/services/` files must never `import fastapi`. Only files in `backend/app/api/` may use FastAPI constructs (routers, `Depends`, `HTTPException`, etc.).
- **All prompts go in `backend/app/prompts/`**: LLM prompt strings must not be inlined in service code. Load them at service init time.
- **Pydantic models are the contract**: every API endpoint request/response uses a model from `backend/app/models/`. Never accept/return raw `dict` at the route level.
- **Config is injected, never imported directly**: use FastAPI `Depends` with the settings object from `backend/app/core/config.py`; do not call `os.getenv()` inside services or routes.

### Frontend
- **Web-only target**: never add packages that require mobile permissions or native plugins. Always validate with `flutter run -d chrome`.
- **One widget per file**, file name = widget class name in `snake_case` (e.g., `PaperCard` → `paper_card.dart`).

### Evals
- `evals/evaluation_results/` is runtime output — never commit it. Writing there is expected; reading there is for reporting only.
- Fixture files in `evals/fixtures/` are the source of truth for eval inputs; do not modify them during a run.

### Docker / Environment
- All secrets are in `.env` (from `.env.example`). When adding a new env var, add it to `.env.example` with a placeholder value and document it in `backend/app/core/config.py`.
