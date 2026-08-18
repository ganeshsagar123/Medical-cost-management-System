from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings


class AdvisorLLMProvider(Protocol):
    name: str
    model: str | None

    def available(self) -> bool: ...

    def generate(self, *, instructions: str, input_text: str) -> str: ...


class UnavailableProvider:
    name = "disabled"
    model = None

    def available(self) -> bool:
        return False

    def generate(self, *, instructions: str, input_text: str) -> str:
        raise RuntimeError("No LLM provider is configured.")


class OpenAIResponsesProvider:
    """Adapter for OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, *, api_key: str | None, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"
        self.base_url = base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def generate(self, *, instructions: str, input_text: str) -> str:
        if not self.available():
            raise RuntimeError("OpenAI provider credentials are not configured.")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        # Try standard OpenAI Chat Completions API
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": input_text},
                    ],
                },
                timeout=30.0,
            )
            if response.status_code == 200:
                payload = response.json()
                choices = payload.get("choices", [])
                if choices and isinstance(choices, list):
                    content = choices[0].get("message", {}).get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
            else:
                try:
                    err_json = response.json()
                    detail = err_json.get("error", {}).get("message") or response.text
                except Exception:
                    detail = response.text
                raise RuntimeError(f"OpenAI API Error ({response.status_code}): {detail}")
        except RuntimeError:
            raise
        except Exception as error:
            raise RuntimeError(f"OpenAI Connection Error: {error}") from error

        raise RuntimeError("The configured OpenAI provider returned no text response.")


def create_llm_provider(settings: Settings) -> AdvisorLLMProvider:
    if settings.advisor_llm_provider.lower() == "openai":
        return OpenAIResponsesProvider(
            api_key=settings.advisor_llm_api_key,
            model=settings.advisor_llm_model,
            base_url=settings.advisor_llm_base_url,
        )
    return UnavailableProvider()
