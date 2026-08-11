"""Capability-specific provider ports and routing.

The rest of PaperScape depends on these small contracts rather than vendor
SDKs.  Ports are synchronous for compatibility with the current worker; a
future async worker can implement the same request/result shapes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.provider import (
    GenerationResult,
    ModelCapability,
    ModelDescriptor,
    ProviderType,
    StructuredGenerationRequest,
    TaskPolicy,
    TextGenerationRequest,
)


class StructuredGenerationPort(ABC):
    @abstractmethod
    def generate_structured(self, request: StructuredGenerationRequest) -> GenerationResult:
        """Generate JSON text which the caller must validate semantically."""


class TextGenerationPort(ABC):
    @abstractmethod
    def generate_text(self, request: TextGenerationRequest) -> GenerationResult:
        """Generate text; source grounding remains a PaperScape concern."""


class ProviderAdapter(StructuredGenerationPort, TextGenerationPort):
    provider_type: ProviderType
    model_descriptor: ModelDescriptor


@dataclass(frozen=True)
class ProviderRegistry:
    """Immutable registry used by the router and connection tests."""

    adapters: tuple[ProviderAdapter, ...]

    def for_capabilities(self, required: set[ModelCapability]) -> tuple[ProviderAdapter, ...]:
        return tuple(
            adapter for adapter in self.adapters
            if required.issubset(adapter.model_descriptor.capabilities)
        )


class ModelRouter:
    """Select an adapter from task requirements, never from vendor names alone."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def route(self, policy: TaskPolicy) -> ProviderAdapter:
        candidates = list(self._registry.for_capabilities(policy.required_capabilities))
        if policy.allowed_providers is not None:
            candidates = [a for a in candidates if a.provider_type in policy.allowed_providers]
        references = [*policy.preferred_models, *policy.fallback_models]
        for reference in references:
            for adapter in candidates:
                if adapter.provider_type == reference.provider_type and adapter.model_descriptor.model_id == reference.model_id:
                    return adapter
        if candidates:
            return candidates[0]
        raise LookupError("No configured model satisfies the requested task policy.")

