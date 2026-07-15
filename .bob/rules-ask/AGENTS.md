# AGENTS.md — Ask mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Documentation Context

- **`backend/app/prompts/`** is the canonical location for all LLM prompt wording — check there first before looking at service code for what the AI is actually doing.
- **`docs/`** contains the full design record: `product-spec.md`, `architecture.md`, `data-model.md`, `evaluation-plan.md`. These are the authoritative source on intent; code may diverge during development.
- **`evals/expected/`** holds ground-truth outputs and is the best reference for understanding what a correct response looks like end-to-end.
- **`sample_papers/`** contains real PDFs used for manual testing — useful context when answering questions about parsing edge cases.
- **`docs/bob-usage-log.md`** records decisions made during AI-assisted development; check it for rationale behind non-obvious choices.
