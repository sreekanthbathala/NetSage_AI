"""
tests/test_providers.py
------------------------
Tests for the AI provider factory and provider implementations.

Tests:
  - Factory returns the correct provider class for each AI_PROVIDER value
  - ProviderConfigError is raised for unknown AI_PROVIDER values
  - ProviderConfigError is raised when required env vars are missing
  - No provider SDK is imported outside ai/providers/ (import hygiene check)
  - Rule checker works independently with no AI_PROVIDER set
"""

import sys
import os
import pytest
import importlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.providers.base import ProviderConfigError, ProviderCallError


class TestProviderFactory:
    """Tests for ai/providers/provider_factory.py"""

    def test_default_provider_is_ollama(self):
        """When AI_PROVIDER is not set, factory should default to Ollama."""
        env = {k: v for k, v in os.environ.items() if k != "AI_PROVIDER"}
        env.setdefault("OLLAMA_MODEL", "llama3.1")

        with patch.dict(os.environ, env, clear=True):
            from ai.providers.provider_factory import get_provider
            from ai.providers.ollama_provider import OllamaProvider
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_ollama_provider_selected(self):
        """AI_PROVIDER=ollama should return OllamaProvider."""
        with patch.dict(os.environ, {"AI_PROVIDER": "ollama", "OLLAMA_MODEL": "llama3.1"}):
            from ai.providers.provider_factory import get_provider
            from ai.providers.ollama_provider import OllamaProvider
            provider = get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises_config_error(self):
        """Unknown AI_PROVIDER value should raise ProviderConfigError."""
        with patch.dict(os.environ, {"AI_PROVIDER": "nonexistent_ai_service"}):
            from ai.providers.provider_factory import get_provider
            with pytest.raises(ProviderConfigError) as exc_info:
                get_provider()
            assert "nonexistent_ai_service" in str(exc_info.value)

    def test_anthropic_missing_key_raises_config_error(self):
        """AI_PROVIDER=anthropic with no ANTHROPIC_API_KEY should raise ProviderConfigError."""
        env = {"AI_PROVIDER": "anthropic"}
        # Remove any existing key
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("ANTHROPIC_API_KEY", "AI_PROVIDER")}
        env_clean["AI_PROVIDER"] = "anthropic"

        with patch.dict(os.environ, env_clean, clear=True):
            from ai.providers.provider_factory import get_provider
            with pytest.raises((ProviderConfigError, ImportError)):
                get_provider()

    def test_gemini_missing_key_raises_config_error(self):
        """AI_PROVIDER=gemini with no GEMINI_API_KEY should raise ProviderConfigError."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("GEMINI_API_KEY", "AI_PROVIDER")}
        env_clean["AI_PROVIDER"] = "gemini"

        with patch.dict(os.environ, env_clean, clear=True):
            from ai.providers.provider_factory import get_provider
            with pytest.raises((ProviderConfigError, ImportError)):
                get_provider()

    def test_openrouter_missing_key_raises_config_error(self):
        """AI_PROVIDER=openrouter with no OPENROUTER_API_KEY should raise ProviderConfigError."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("OPENROUTER_API_KEY", "AI_PROVIDER")}
        env_clean["AI_PROVIDER"] = "openrouter"

        with patch.dict(os.environ, env_clean, clear=True):
            from ai.providers.provider_factory import get_provider
            with pytest.raises(ProviderConfigError) as exc_info:
                get_provider()
            assert "OPENROUTER_API_KEY" in str(exc_info.value)


class TestImportHygiene:
    """
    Ensure that no provider-specific SDK is imported outside ai/providers/.

    The rule: app.py, ai/diagnose.py, checker/, review/, dashboard/ must
    NEVER directly import anthropic, google.generativeai, etc.
    """

    def _read_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
        return ""

    PROJECT_ROOT = Path(__file__).parent.parent
    FORBIDDEN_IMPORTS = [
        "import anthropic",
        "from anthropic",
        "import google.generativeai",
        "from google.generativeai",
        "import google-generativeai",
    ]
    ALLOWED_FILES = [
        "ai/providers/anthropic_provider.py",
        "ai/providers/gemini_provider.py",
    ]

    def _get_files_to_check(self):
        """Return Python files that must not import provider SDKs directly."""
        files = []
        for pattern in ["app.py", "ai/diagnose.py", "ai/schema_validator.py"]:
            files.append(self.PROJECT_ROOT / pattern)

        for d in ["checker", "review", "dashboard"]:
            for f in (self.PROJECT_ROOT / d).glob("*.py"):
                files.append(f)

        return files

    def test_app_py_no_direct_sdk_imports(self):
        app_content = self._read_file(self.PROJECT_ROOT / "app.py")
        for forbidden in self.FORBIDDEN_IMPORTS:
            assert forbidden not in app_content, \
                f"app.py must not directly import '{forbidden}'. Use ai/diagnose.py."

    def test_diagnose_py_no_direct_sdk_imports(self):
        diagnose_content = self._read_file(self.PROJECT_ROOT / "ai" / "diagnose.py")
        for forbidden in self.FORBIDDEN_IMPORTS:
            assert forbidden not in diagnose_content, \
                f"ai/diagnose.py must not directly import '{forbidden}'."

    def test_checker_no_sdk_imports(self):
        checker_path = self.PROJECT_ROOT / "checker"
        for py_file in checker_path.glob("*.py"):
            content = self._read_file(py_file)
            for forbidden in self.FORBIDDEN_IMPORTS:
                assert forbidden not in content, \
                    f"{py_file.name} (in checker/) must not import '{forbidden}'."

    def test_checker_has_no_ai_provider_import(self):
        """checker/rules.py must never import from ai/ package."""
        rules_content = self._read_file(self.PROJECT_ROOT / "checker" / "rules.py")
        assert "from ai" not in rules_content, \
            "checker/rules.py must not import from the ai/ package"
        assert "import ai" not in rules_content, \
            "checker/rules.py must not import from the ai/ package"


class TestRuleCheckerIndependence:
    """
    Verify that the rule checker works with no AI provider configured.
    Correct behavior: AI_PROVIDER unset + no API keys = rule checker unaffected.
    """

    def test_rule_checker_works_without_ai_provider(self):
        """Rule checker must work regardless of AI_PROVIDER env var state."""
        env_no_ai = {k: v for k, v in os.environ.items()
                     if k not in ("AI_PROVIDER", "ANTHROPIC_API_KEY",
                                  "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_HOST")}

        with patch.dict(os.environ, env_no_ai, clear=True):
            from checker.rules import run_all_checks

            sample_output = """
Router#show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.1.1     YES NVRAM  administratively down down
"""
            results = run_all_checks(sample_output)
            assert len(results) == 6  # All 6 checks run

            # Should detect the admin-down interface
            triggered = [r for r in results if r["triggered"]]
            assert any(r["rule"] == "check_interface_down" for r in triggered), \
                "Rule checker should detect admin-down even with no AI provider"

    def test_rule_checker_produces_6_results_always(self):
        """run_all_checks always returns exactly 6 results."""
        from checker.rules import run_all_checks

        # Empty input
        results = run_all_checks("")
        assert len(results) == 6

        # Gibberish input
        results = run_all_checks("xyz abc 123 !!!!")
        assert len(results) == 6


class TestOllamaProviderConfig:
    def test_missing_model_raises_config_error(self):
        """OLLAMA_MODEL being blank should raise ProviderConfigError."""
        env = {"AI_PROVIDER": "ollama", "OLLAMA_MODEL": ""}
        with patch.dict(os.environ, env):
            from ai.providers.ollama_provider import OllamaProvider
            with pytest.raises(ProviderConfigError) as exc_info:
                OllamaProvider()
            assert "OLLAMA_MODEL" in str(exc_info.value)
