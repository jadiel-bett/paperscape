# PaperScape Development Instructions

## Product goal

PaperScape transforms research papers into audience-specific,
evidence-backed explainer packs.

The primary workflow is:

1. Upload a research PDF.
2. Extract page-aware structured content.
3. Build a research map.
4. Select an audience.
5. Generate a plain-language explainer pack.
6. Link every major claim to source evidence.

## Technology

- Flutter Web frontend
- Python FastAPI backend
- Docling for structured PDF conversion
- PyMuPDF as the extraction fallback
- watsonx.ai and IBM Granite for AI generation
- Pydantic for structured schemas
- pytest for backend tests
- Docker for backend deployment

## Architecture rules

- Keep frontend, document processing, retrieval, and model inference separated.
- Access watsonx only through an LLMProvider interface.
- Preserve page numbers and section metadata throughout processing.
- Generated factual claims must include source chunk IDs.
- Do not generate citations after writing the explanation.
- Generate explanations from selected evidence records.
- Never expose API keys to the Flutter application.
- Store all credentials in environment variables.
- Avoid unnecessary frameworks and abstractions.

## AI rules

- Require structured JSON responses.
- Do not request or store model chain-of-thought.
- Accept concise explanations and evidence only.
- Reject claims without supporting evidence.
- Flag partial or uncertain support.
- Include paper limitations in every explainer pack.
- Never claim that PaperScape replaces expert review.

## Development rules

- Work on one bounded feature at a time.
- Present a plan before implementing major features.
- Add tests for all service-layer behavior.
- Run existing tests before declaring a task complete.
- Do not modify unrelated files.
- Explain important architectural changes.
- Update documentation whenever behavior changes.
- Prefer small, reviewable commits.
