"""
ai/providers/base.py
--------------------
Abstract base class for all AI providers in NetSage AI.

Any code outside ai/providers/ must only ever interact with the Provider
interface defined here — never import a provider-specific SDK directly.
"""

from abc import ABC, abstractmethod


class ProviderConfigError(Exception):
    """
    Raised when required configuration for a provider is missing or invalid.

    Examples:
        - ANTHROPIC_API_KEY is not set but AI_PROVIDER=anthropic
        - OLLAMA_MODEL is not set
        - OLLAMA_HOST is not reachable at startup config time
    """
    pass


class ProviderCallError(Exception):
    """
    Raised when the provider is correctly configured but the API call fails.

    Examples:
        - HTTP 4xx/5xx from the provider API
        - Network timeout while calling Ollama
        - Response body is not parseable JSON (for providers that return JSON directly)
    """
    pass


class Provider(ABC):
    """
    Abstract interface that every AI provider must implement.

    Responsibilities:
        - Accept a system prompt and a user prompt.
        - Call the underlying AI service.
        - Return the raw text response (unparsed).

    Must NEVER:
        - Return a fabricated or placeholder diagnosis.
        - Silently substitute a different provider.
        - Swallow errors — always raise ProviderConfigError or ProviderCallError.
    """

    @abstractmethod
    def diagnose(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send the system_prompt and user_prompt to the AI provider and return
        the raw text response.

        Args:
            system_prompt: The system-level instructions for the model.
            user_prompt: The user-level case data and diagnosis request.

        Returns:
            Raw text response from the model (expected to be a JSON string,
            but validation is the caller's responsibility).

        Raises:
            ProviderConfigError: If required configuration (API key, host, model)
                is missing or invalid at call time.
            ProviderCallError: If the configured provider is called but returns
                an error (timeout, HTTP error, unexpected empty response, etc.).
        """
        ...
