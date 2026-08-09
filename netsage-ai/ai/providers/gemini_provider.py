"""
ai/providers/gemini_provider.py
--------------------------------
Google Gemini provider.

Environment variables:
    GEMINI_API_KEY  (required when AI_PROVIDER=gemini)
    GEMINI_MODEL    (optional, default: gemini-1.5-flash)

Requires: pip install google-generativeai
(Only needed when AI_PROVIDER=gemini is explicitly selected.)
"""

import os
from ai.providers.base import Provider, ProviderConfigError, ProviderCallError

GEMINI_DEFAULT_MODEL = "gemini-1.5-flash"


class GeminiProvider(Provider):
    """
    Provider implementation for Google Gemini via the google-generativeai SDK.
    """

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigError(
                "GEMINI_API_KEY is not set but AI_PROVIDER=gemini. "
                "Set it in your .env file or environment, or switch to a provider "
                "that doesn't require an API key (e.g. AI_PROVIDER=ollama)."
            )
        self.model_name = os.environ.get("GEMINI_MODEL", GEMINI_DEFAULT_MODEL).strip()
        self._api_key = api_key

        # Import SDK only when this provider is actually used
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(self.model_name)
        except ImportError as e:
            raise ProviderConfigError(
                "google-generativeai package is not installed. "
                "Run: pip install google-generativeai"
            ) from e

    def diagnose(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the Gemini model with system and user prompt.

        Returns:
            Raw text response from Gemini.

        Raises:
            ProviderCallError: On any API failure.
        """
        # Gemini SDK combines system + user into a single call
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
        try:
            response = self._model.generate_content(full_prompt)
            content = response.text.strip()
            if not content:
                raise ProviderCallError("Gemini returned an empty response.")
            return content
        except Exception as e:
            # Catch all Gemini SDK errors and re-raise as ProviderCallError
            raise ProviderCallError(f"Gemini API call failed: {e}") from e

    def __repr__(self) -> str:
        return f"GeminiProvider(model={self.model_name!r})"
