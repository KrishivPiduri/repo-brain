"""
Copy this file to config.py and fill in your settings.
API keys can also be set via environment variables (recommended).
"""
import os

# OpenAI — https://platform.openai.com/api-keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Default model — change to whichever provider you prefer
# ---------------------------------------------------------------------------

# OpenAI
DEFAULT_MODEL = "gpt-4o-mini"

# Anthropic Claude — also set ANTHROPIC_API_KEY env var (pip install anthropic)
# DEFAULT_MODEL = "claude-3-5-haiku-20241022"

# Deepseek (OpenAI-compatible, very cheap) — also set DEEPSEEK_API_KEY
# DEFAULT_MODEL = "deepseek/deepseek-chat"

# Google Gemini — also set GEMINI_API_KEY
# DEFAULT_MODEL = "gemini/gemini-2.0-flash"

# Groq (fast inference) — also set GROQ_API_KEY
# DEFAULT_MODEL = "groq/llama-3.1-8b-instant"

# Ollama (local, free, no key needed)
# DEFAULT_MODEL = "ollama/llama3.1"

# Mistral — also set MISTRAL_API_KEY
# DEFAULT_MODEL = "mistral/mistral-small"

# xAI Grok — also set XAI_API_KEY
# DEFAULT_MODEL = "xai/grok-beta"

# Perplexity — also set PPLX_API_KEY
# DEFAULT_MODEL = "perplexity/sonar"

# OpenRouter (access 100s of models) — also set OPENROUTER_API_KEY
# DEFAULT_MODEL = "openrouter/anthropic/claude-3.5-haiku"

# ---------------------------------------------------------------------------
# Scan settings
# ---------------------------------------------------------------------------

# Directories to skip during scanning
IGNORE_DIRS = {
    ".venv", "node_modules", ".git", "repos", "build", "dist",
    "__pycache__", ".idea", ".mypy_cache", "coverage", ".pytest_cache",
    "target", "vendor", "tmp", "temp", ".next", ".nuxt", "out", ".tox",
}

# File extensions to skip entirely
IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp",
    ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".tar", ".gz", ".whl",
    ".lock", ".sum",
}

# File extensions to include
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".hpp", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".sql", ".yaml", ".yml",
    ".toml", ".json", ".xml", ".html", ".css", ".scss", ".md",
    ".txt", ".env", ".cfg", ".ini", ".conf", ".r",
}

MAX_FILE_SIZE_KB = 500
