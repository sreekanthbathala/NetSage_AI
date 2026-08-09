"""
ai/providers/ollama_provider.py
--------------------------------
Ollama provider — local, free, no API key required.

Environment variables:
    OLLAMA_HOST  (default: http://localhost:11434)
    OLLAMA_MODEL (required — e.g. llama3.1, mistral, phi3)

No SDK needed; communicates via plain HTTP requests to the Ollama REST API.
"""

import os
import json
import requests
from ai.providers.base import Provider, ProviderConfigError, ProviderCallError

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "llama3.1"
REQUEST_TIMEOUT_SECONDS = 120


class OllamaProvider(Provider):
    """
    Provider implementation for local Ollama inference.
    Uses the Ollama /api/chat endpoint with the configured model.
    """

    def __init__(self):
        self.host = os.environ.get("OLLAMA_HOST", OLLAMA_DEFAULT_HOST).rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL)

        if not self.model:
            raise ProviderConfigError(
                "OLLAMA_MODEL is not set. Please set it in your .env file "
                "(e.g. OLLAMA_MODEL=llama3.1)."
            )

    def diagnose(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send system + user prompt to the Ollama /api/chat endpoint.

        Returns:
            The model's raw text reply.

        Raises:
            ProviderConfigError: If the host is unreachable (likely not running).
            ProviderCallError: If the API returns an error or unexpected response.
        """
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.ConnectionError as e:
            raise ProviderConfigError(
                f"Cannot connect to Ollama at {self.host}. "
                f"Is Ollama running? (ollama serve). Error: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ProviderCallError(
                f"Ollama request timed out after {REQUEST_TIMEOUT_SECONDS}s "
                f"(model: {self.model}). Try a smaller model or increase timeout. Error: {e}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise ProviderCallError(f"Ollama request failed: {e}") from e

        if response.status_code != 200:
            raise ProviderCallError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise ProviderCallError(
                f"Ollama response was not valid JSON: {response.text[:200]}. Error: {e}"
            ) from e

        # Extract the assistant's message content
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise ProviderCallError(
                "Ollama returned an empty response. "
                f"Full response: {json.dumps(data)[:300]}"
            )

        return content

    def __repr__(self) -> str:
        return f"OllamaProvider(host={self.host!r}, model={self.model!r})"
