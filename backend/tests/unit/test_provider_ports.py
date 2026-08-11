from uuid import uuid4

import pytest

from app.models.provider import (
    GenerationProvenance,
    GenerationResult,
    ModelCapability,
    ModelDescriptor,
    ModelReference,
    ProviderType,
    StructuredGenerationRequest,
    TaskPolicy,
    TaskType,
)
from app.services.provider_ports import ModelRouter, ProviderAdapter, ProviderRegistry


class FakeAdapter(ProviderAdapter):
    def __init__(self, provider_type: ProviderType, model_id: str, capabilities: set[ModelCapability]):
        self.provider_type = provider_type
        self.model_descriptor = ModelDescriptor(
            provider_type=provider_type,
            model_id=model_id,
            display_name=model_id,
            capabilities=capabilities,
        )

    def generate_text(self, request):
        return GenerationResult(content="ok", provenance=GenerationProvenance(provider_type=self.provider_type, model_id=self.model_descriptor.model_id, adapter_version="test"))

    def generate_structured(self, request):
        return self.generate_text(request)


def test_router_requires_capabilities_and_honours_preferred_model():
    first = FakeAdapter(ProviderType.OPENAI, "cheap", {ModelCapability.TEXT_GENERATION})
    second = FakeAdapter(ProviderType.WATSONX, "grounded", {ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT})
    router = ModelRouter(ProviderRegistry((first, second)))
    policy = TaskPolicy(
        task=TaskType.RESEARCH_MAP,
        required_capabilities={ModelCapability.STRUCTURED_OUTPUT},
        preferred_models=[ModelReference(provider_type=ProviderType.WATSONX, model_id="grounded")],
    )
    assert router.route(policy) is second


def test_structured_request_rejects_blank_prompt():
    with pytest.raises(ValueError):
        StructuredGenerationRequest(prompt=" ", max_tokens=10, temperature=0)

