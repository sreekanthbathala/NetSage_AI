"""
ai/providers/provider_factory.py
---------------------------------
Reads the AI_PROVIDER environment variable and returns the correct Provider instance.

Allowed AI_PROVIDER values: ollama, gemini, anthropic, openrouter
Default (if AI_PROVIDER is unset): ollama

Rules:
  - Each provider module is only imported when that provider is selected.
  - If the selected provider's required config is missing, ProviderConfigError is raised.
  - We NEVER silently fall back to a different provider.
  - We NEVER require an Anthropic key unless AI_PROVIDER=anthropic is set.
"""

import os
from ai.providers.base import Provider, ProviderConfigError

# Map of allowed provider names
ALLOWED_PROVIDERS = {"ollama", "gemini", "anthropic", "openrouter"}
DEFAULT_PROVIDER = "ollama"


def get_provider() -> Provider:
    """
    Read AI_PROVIDER from environment and return the matching Provider instance.

    Returns:
        An instantiated Provider ready to call .diagnose().

    Raises:
        ProviderConfigError: If AI_PROVIDER is set to an unrecognized value,
            or if the selected provider's required config (API key, host, model)
            is missing.
    """
    provider_name = os.environ.get("AI_PROVIDER", DEFAULT_PROVIDER).strip().lower()

    if provider_name not in ALLOWED_PROVIDERS:
        raise ProviderConfigError(
            f"Unknown AI_PROVIDER='{provider_name}'. "
            f"Allowed values: {', '.join(sorted(ALLOWED_PROVIDERS))}. "
            f"Default is '{DEFAULT_PROVIDER}'."
        )

    # Lazy imports — only load the SDK for the selected provider
    if provider_name == "ollama":
        from ai.providers.ollama_provider import OllamaProvider
        return OllamaProvider()

    elif provider_name == "gemini":
        from ai.providers.gemini_provider import GeminiProvider
        return GeminiProvider()

    elif provider_name == "anthropic":
        from ai.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()

    elif provider_name == "openrouter":
        from ai.providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider()

    # This line is unreachable given the check above, but included for safety
    raise ProviderConfigError(f"Unhandled provider: {provider_name}")
