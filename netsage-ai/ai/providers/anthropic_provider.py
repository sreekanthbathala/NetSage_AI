"""
ai/providers/anthropic_provider.py
------------------------------------
Anthropic (Claude) provider.

Environment variables:
    ANTHROPIC_API_KEY  (required when AI_PROVIDER=anthropic)
    ANTHROPIC_MODEL    (optional, default: claude-3-haiku-20240307)

Requires: pip install anthropic
(Only needed when AI_PROVIDER=anthropic is explicitly selected.)
"""

import os
from ai.providers.base import Provider, ProviderConfigError, ProviderCallError

ANTHROPIC_DEFAULT_MODEL = "claude-3-haiku-20240307"
ANTHROPIC_MAX_TOKENS = 1024


class AnthropicProvider(Provider):
    """
    Provider implementation for Anthropic Claude via the anthropic SDK.
    """

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigError(
                "ANTHROPIC_API_KEY is not set but AI_PROVIDER=anthropic. "
                "Set it in your .env file or environment, or switch to a provider "
                "that doesn't require an API key (e.g. AI_PROVIDER=ollama)."
            )
        self.model_name = os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_DEFAULT_MODEL).strip()
        self._api_key = api_key

        # Import SDK only when this provider is actually used
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        except ImportError as e:
            raise ProviderConfigError(
                "anthropic package is not installed. "
                "Run: pip install anthropic"
            ) from e

    def diagnose(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the Anthropic Claude model with system and user prompt.

        Returns:
            Raw text response from Claude.

        Raises:
            ProviderCallError: On any API failure.
        """
        try:
            message = self._client.messages.create(
                model=self.model_name,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            content = message.content[0].text.strip()
            if not content:
                raise ProviderCallError("Anthropic returned an empty response.")
            return content
        except Exception as e:
            raise ProviderCallError(f"Anthropic API call failed: {e}") from e

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model_name!r})"
