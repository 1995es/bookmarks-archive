"""Resolves LLM_MODEL and validates its provider's API key is set.

litellm reads provider API keys from the environment implicitly (e.g. GEMINI_API_KEY for
gemini/* models); it doesn't expose a clean "which env var does this provider need" lookup, so
that mapping is owned here instead.
"""

import os

import litellm

from app.domain.exceptions import MissingLLMCredentialsError

DEFAULT_MODEL = "gemini/gemini-3.5-flash"

_PROVIDER_API_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "replicate": "REPLICATE_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def resolve_llm_model() -> str:
    """Reads LLM_MODEL (defaulting to DEFAULT_MODEL) and checks its provider's API key is set.

    Raises MissingLLMCredentialsError if the model's provider needs a key this codebase knows
    about and it isn't in the environment. Meant to be called once, at app startup.
    """
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    _, provider, _, _ = litellm.get_llm_provider(model)

    required_env_var = _PROVIDER_API_KEY_ENV.get(provider)
    if required_env_var and not os.environ.get(required_env_var):
        raise MissingLLMCredentialsError(model=model, provider=provider, env_var=required_env_var)

    return model
