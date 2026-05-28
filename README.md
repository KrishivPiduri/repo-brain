# repo-brain

> Compress an entire codebase into a single markdown context file. Feed it to any LLM once instead of paying to re-read your repo on every query.

Every time you ask an LLM a question about a codebase it doesn't already know, it burns tokens reading files. A medium-sized repo (200 files) can cost **$0.50–$2.00 per conversation** just loading context. repo-brain reads everything once, maps the architecture, resolves file relationships, and writes a compact markdown file you inject as a system prompt — paying for understanding once, reusing it forever.

## Results

| Repo | Raw source tokens | Context tokens | Compression |
|---|---|---|---|
| lago-python-client | 154,229 | 6,487 | **96%** |
| Your repo | ... | ... | ... |

## What the output contains

A single `context.md` with:

- **Repository structure** — correct nested directory tree
- **Architecture overview** — LLM-identified layers, components, data flow (with `--llm`)
- **Semantic relationships** — producer/consumer links, shared data structures, potential redundancies, polyglot bridges (with `--llm`)
- **File reference** — every source file's purpose, public classes, functions, and local dependencies in ~4 lines per file
- **External dependencies** — third-party libraries and their roles

## Installation

### Option A: One-liner install (recommended for most users)

No cloning, no venv setup, no config files. Just run the installer and go.

**Mac / Linux:**
```bash
curl -fsSL https://github.com/YOUR_USERNAME/repo-brain/releases/latest/download/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://github.com/YOUR_USERNAME/repo-brain/releases/latest/download/install.ps1 | iex
```

This downloads the latest release, creates a `~/.repo-brain` virtualenv, installs dependencies, and adds `repo-brain` to your PATH.

### Option B: From source

Requires Python 3.10+.

```bash
git clone https://github.com/YOUR_USERNAME/repo-brain
cd repo-brain
python -m venv .venv
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

## Set your API key

repo-brain works with **any major LLM provider**. Set the environment variable for whichever one you use:

```bash
# OpenAI (default)
export OPENAI_API_KEY=sk-...

# Anthropic Claude
export ANTHROPIC_API_KEY=sk-ant-...

# Deepseek (very cost-effective)
export DEEPSEEK_API_KEY=...

# Google Gemini
export GEMINI_API_KEY=...

# Groq (fast inference)
export GROQ_API_KEY=...

# Ollama (local, free, no key needed)
# nothing to set — just have Ollama running

# Windows PowerShell equivalent:
$env:OPENAI_API_KEY = "sk-..."
```

## Usage

```bash
# Basic — static analysis only (free, no API key needed)
repo-brain /path/to/your/repo --no-llm

# With LLM architecture analysis + semantic relationship discovery
repo-brain /path/to/your/repo

# Custom output file
repo-brain /path/to/your/repo -o my_context.md

# From a git URL (clones automatically)
repo-brain https://github.com/org/repo

# Use Claude instead of OpenAI
repo-brain /path/to/repo --model claude-3-5-haiku-20241022

# Use Deepseek (cheap!)
repo-brain /path/to/repo --model deepseek/deepseek-chat

# Use Gemini
repo-brain /path/to/repo --model gemini/gemini-2.0-flash

# Use Groq (fast)
repo-brain /path/to/repo --model groq/llama-3.1-8b-instant

# Use local Ollama (free)
repo-brain /path/to/repo --model ollama/llama3.1

# Override project name
repo-brain /path/to/repo --name MyProject
```

### Supported models

| Provider | Model string | Env var |
|---|---|---|
| OpenAI | `gpt-4o-mini`, `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `claude-3-5-haiku-20241022`, `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| Deepseek | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` |
| Gemini | `gemini/gemini-2.0-flash`, `gemini/gemini-1.5-flash` | `GEMINI_API_KEY` |
| Groq | `groq/llama-3.1-8b-instant` | `GROQ_API_KEY` |
| Ollama | `ollama/llama3.1` | *(none — local)* |
| Mistral | `mistral/mistral-small` | `MISTRAL_API_KEY` |
| xAI | `xai/grok-beta` | `XAI_API_KEY` |
| Perplexity | `perplexity/sonar` | `PPLX_API_KEY` |
| OpenRouter | `openrouter/<model>` | `OPENROUTER_API_KEY` |

For Claude models, also run: `pip install anthropic`

### CLI output

```
Scanning repository
  [############################] 262/262  0.3s

LLM analysis
  ok  Architecture analysis  1.2s
  ok  Semantic relationships  23 found  3.1s

Generating context file
  ok  Written to context.md

+====================================================+
|                                                    |
|  lago-python-client context ready                  |
|                                                    |
|  262 files scanned                                 |
|  154,229 raw tokens  ->  6,487 context tokens      |
|  96% compression  |  23 semantic relationships     |
|  context.md                                        |
|                                                    |
+====================================================+
```

## Using the context file

Paste the contents of `context.md` into your LLM's system prompt, or add it as the first user message in a conversation. The file is structured for easy comprehension — the LLM won't need to ask clarifying questions about what files do or how they relate.

**Example prompt after injecting context:**

> I've attached a codebase context file above. Based on it, walk me through what happens when a new invoice is created and which files I'd need to modify to add a custom field to it.

## How it works

1. **Ingest** — Scans all source files using Tree-sitter (Python, JS, TS, Go, Rust) with regex fallback for other languages. Extracts classes, functions, imports, and module descriptions.

2. **Analyze** *(with LLM)* — Single LLM call over a condensed file manifest to derive architecture: layers, components, data flow, entry points.

3. **Relationships** *(with LLM)* — LLM pass to identify semantic cross-file links (producer/consumer flows, shared data structures, parallel implementations, polyglot bridges). Scales to `N` relationships for `N` files.

4. **Generate** — Assembles everything into a structured markdown file. Data files, empty `__init__.py` markers, and test fixture files are filtered out. Test files are summarized. File reference entries are capped at ~4 lines each.

## MCP server

repo-brain also ships as an MCP tool for use with Claude and other MCP-compatible agents. Install the optional dep and run:

```bash
pip install mcp
python mcp_server.py
```

Tools exposed:
- `generate_context(source_dir, output_file?, no_llm?, model?)` — generate and return the context markdown
- `get_file_structure(source_dir)` — quick scan without LLM

## Configuration

Copy `config.example.py` to `config.py` to customise which directories and file extensions are scanned, max file size, and default model.

## Supported languages

Tree-sitter parsing (accurate AST-based extraction): **Python, JavaScript, TypeScript, Go, Rust**

Regex fallback (import/class/function extraction): Java, Ruby, PHP, C#, C/C++, Swift, Kotlin, Scala, Shell, and others.
