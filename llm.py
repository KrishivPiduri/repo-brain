"""
Unified LLM client — works with any OpenAI-compatible provider and Anthropic.

Model strings:
  OpenAI:      gpt-4o-mini, gpt-4o
  Anthropic:   claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022
  Deepseek:    deepseek/deepseek-chat
  Gemini:      gemini/gemini-1.5-flash, gemini/gemini-2.0-flash
  Groq:        groq/llama-3.1-8b-instant
  Ollama:      ollama/llama3.1          (runs locally, no key needed)
  Mistral:     mistral/mistral-small
  Together:    together/meta-llama/Llama-3-8b-chat-hf
  xAI:         xai/grok-beta
  Perplexity:  perplexity/sonar

API keys are read from environment variables automatically.
Passing --api-key on the CLI sets the key for whichever provider is active.
"""
from __future__ import annotations

import json
import os
import re

# provider prefix -> (base_url, env_var_for_api_key)
_PROVIDERS: dict[str, tuple[str, str | None]] = {
    "deepseek":    ("https://api.deepseek.com",                                    "DEEPSEEK_API_KEY"),
    "groq":        ("https://api.groq.com/openai/v1",                              "GROQ_API_KEY"),
    "ollama":      ("http://localhost:11434/v1",                                    None),
    "gemini":      ("https://generativelanguage.googleapis.com/v1beta/openai/",    "GEMINI_API_KEY"),
    "together":    ("https://api.together.xyz/v1",                                 "TOGETHER_API_KEY"),
    "mistral":     ("https://api.mistral.ai/v1",                                   "MISTRAL_API_KEY"),
    "xai":         ("https://api.x.ai/v1",                                         "XAI_API_KEY"),
    "perplexity":  ("https://api.perplexity.ai",                                   "PPLX_API_KEY"),
    "openrouter":  ("https://openrouter.ai/api/v1",                                "OPENROUTER_API_KEY"),
}


def complete_json(
    model: str,
    system: str,
    user: str,
    api_key: str = "",
    temperature: float = 0,
) -> dict:
    """Call any supported LLM and return a parsed JSON dict."""
    raw = _complete(model, system, user, api_key, temperature)
    return _parse_json(raw)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _complete(model: str, system: str, user: str, api_key: str, temperature: float) -> str:
    if _is_anthropic(model):
        return _anthropic(model, system, user, api_key, temperature)
    return _openai_compat(model, system, user, api_key, temperature)


def _is_anthropic(model: str) -> bool:
    m = model.lower()
    return m.startswith("claude") or m.startswith("anthropic/")


def _anthropic(model: str, system: str, user: str, api_key: str, temperature: float) -> str:
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package not installed. Run: pip install anthropic"
        )
    clean_model = model.removeprefix("anthropic/")
    key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=clean_model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
    )
    return resp.content[0].text


def _openai_compat(model: str, system: str, user: str, api_key: str, temperature: float) -> str:
    from openai import OpenAI

    prefix, clean_model = _split_prefix(model)
    base_url, env_var = _PROVIDERS.get(prefix, ("", "OPENAI_API_KEY"))

    key = api_key or (os.getenv(env_var, "") if env_var else "no-key-needed")
    client = OpenAI(
        api_key=key or "no-key-needed",
        base_url=base_url or None,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Try native JSON mode first, fall back gracefully for models that don't support it
    try:
        resp = client.chat.completions.create(
            model=clean_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
    except Exception:
        resp = client.chat.completions.create(
            model=clean_model,
            messages=messages,
            temperature=temperature,
        )

    return resp.choices[0].message.content


def _split_prefix(model: str) -> tuple[str, str]:
    """'deepseek/deepseek-chat' -> ('deepseek', 'deepseek-chat')"""
    if "/" in model:
        prefix, rest = model.split("/", 1)
        if prefix.lower() in _PROVIDERS:
            return prefix.lower(), rest
    return "", model


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return json.loads(text)
