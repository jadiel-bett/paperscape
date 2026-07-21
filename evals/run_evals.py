"""
Deterministic offline evaluation for research-map parsing and grounding.

Usage from repository root::

    python evals/run_evals.py

Exit codes:
    0   ResearchMap matches expected fixture.
    1   ResearchMap differs from expected fixture.
    2   Setup or runtime error.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure backend/ is on sys.path so ``app`` imports work from the repo root.
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.paper import ExtractionResult
from app.models.research_map import ResearchMap
from app.services.llm_provider import LLMProvider
from app.services.research_map import ResearchMapService

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EXPECTED_DIR = Path(__file__).resolve().parent / "expected"


class _FakeEvalProvider(LLMProvider):
    """Fake provider returning a fixed model-response fixture."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.call_count: int = 0

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        self.call_count += 1
        return self._response_text


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    # ---- Load fixtures ----
    try:
        extraction_data = _load_json(FIXTURES_DIR / "research_map_extraction.json")
        model_response = _load_text(FIXTURES_DIR / "research_map_model_response.json")
        expected_data = _load_json(EXPECTED_DIR / "research_map_fixture.json")
    except FileNotFoundError as exc:
        print(f"ERROR: Missing fixture file: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in fixture: {exc}", file=sys.stderr)
        return 2

    # ---- Build extraction ----
    try:
        extraction = ExtractionResult.model_validate(extraction_data)
    except Exception as exc:
        print(f"ERROR: Invalid ExtractionResult fixture: {exc}", file=sys.stderr)
        return 2

    # ---- Run service ----
    provider = _FakeEvalProvider(model_response)
    service = ResearchMapService(provider=provider)

    try:
        result = service.generate_map(extraction)
    except Exception as exc:
        print(f"FAIL: ResearchMapService raised {type(exc).__name__}: {exc}")
        return 1

    # ---- Compare ----
    result_dict = json.loads(result.model_dump_json())

    if result_dict == expected_data:
        print("PASS: ResearchMap matches expected fixture.")
        provider.call_count == 1  # noqa: B015 (intentionally verify single call)
        return 0

    print("FAIL: ResearchMap differs from expected fixture.")
    print()
    print("--- GOT ---")
    print(json.dumps(result_dict, indent=2, ensure_ascii=False))
    print()
    print("--- EXPECTED ---")
    print(json.dumps(expected_data, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())