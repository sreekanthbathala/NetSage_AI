"""
ai/providers/openrouter_provider.py
-------------------------------------
OpenRouter provider — access many models via a single API.

Environment variables:
    OPENROUTER_API_KEY  (required when AI_PROVIDER=openrouter)
    OPENROUTER_MODEL    (optional, default: mistralai/mistral-7b-instruct)

No special SDK needed — uses plain HTTP requests to the OpenRouter REST API.
"""

import os
import json
import requests
from ai.providers.base import Provider, ProviderConfigError, ProviderCallError

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "mistralai/mistral-7b-instruct"
REQUEST_TIMEOUT_SECONDS = 60


class OpenRouterProvider(Provider):
    """
    Provider implementation for OpenRouter via plain HTTP requests.
    Supports many models (Mistral, Llama, Claude, GPT, etc.) via one API key.
    """

    def __init__(self):
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigError(
                "OPENROUTER_API_KEY is not set but AI_PROVIDER=openrouter. "
                "Set it in your .env file or environment, or switch to a provider "
                "that doesn't require an API key (e.g. AI_PROVIDER=ollama)."
            )
        self.model_name = os.environ.get("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL).strip()
        self._api_key = api_key

    def diagnose(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the OpenRouter API with system and user prompt.

        Returns:
            Raw text response from the model.

        Raises:
            ProviderCallError: On any API failure.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://netsage-ai",  # Required by OpenRouter
            "X-Title": "NetSage AI",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as e:
            raise ProviderCallError(
                f"OpenRouter request timed out after {REQUEST_TIMEOUT_SECONDS}s. Error: {e}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise ProviderCallError(f"OpenRouter request failed: {e}") from e

        if response.status_code != 200:
            raise ProviderCallError(
                f"OpenRouter returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise ProviderCallError(
                f"OpenRouter response was not valid JSON: {response.text[:200]}. Error: {e}"
            ) from e

        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderCallError(
                f"Unexpected OpenRouter response structure: {json.dumps(data)[:300]}. Error: {e}"
            ) from e

        if not content:
            raise ProviderCallError("OpenRouter returned an empty response.")

        return content

    def __repr__(self) -> str:
        return f"OpenRouterProvider(model={self.model_name!r})"
