#!/usr/bin/env python3
"""Generate a markdown LLM context file that maps an entire repository."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI helpers (graceful fallback if terminal doesn't support colour)
# ---------------------------------------------------------------------------

_COLOURS = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOURS else text

def green(t):  return _c("32", t)
def cyan(t):   return _c("36", t)
def yellow(t): return _c("33", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)
def magenta(t):return _c("35", t)


def _bar(current: int, total: int, width: int = 28) -> str:
    filled = int(width * current / max(total, 1))
    bar = "#" * filled + "." * (width - filled)
    return f"[{green(bar)}] {current}/{total}"


def _spinner_done(label: str, detail: str = ""):
    tick = green("ok")
    suffix = f"  {dim(detail)}" if detail else ""
    print(f"  {tick}  {label}{suffix}")


def _step(label: str):
    print(f"\n{bold(cyan(label))}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_INTERACTIVE = False


def _interactive_mode():
    """Guided prompts used when the exe is double-clicked with no arguments."""
    global _INTERACTIVE
    _INTERACTIVE = True
    print(bold("repo-brain") + "  —  map a codebase for LLM context\n")

    source = input("  Repo path or GitHub URL: ").strip().strip('"')
    if not source:
        print("Nothing entered. Exiting.")
        input("\nPress Enter to close...")
        sys.exit(0)

    api_key = input("  API key (Enter to skip — static output only): ").strip()

    no_llm = not api_key
    model = "gpt-4o-mini"
    if api_key:
        m = input(f"  Model [{model}]: ").strip()
        if m:
            model = m

    output = input("  Output file [context.md]: ").strip()
    if not output:
        output = "context.md"

    sys.argv = [sys.argv[0], source, "--output", output]
    if no_llm:
        sys.argv.append("--no-llm")
    else:
        sys.argv += ["--model", model, "--api-key", api_key]


def main():
    if len(sys.argv) == 1:
        _interactive_mode()

    parser = argparse.ArgumentParser(
        description="Map a codebase into a single markdown context file for LLMs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  repo-brain /path/to/repo
  repo-brain /path/to/repo -o context.md
  repo-brain https://github.com/user/repo --name MyProject
  repo-brain /path/to/repo --no-llm
        """,
    )
    parser.add_argument("source", help="Local repo path or git URL")
    parser.add_argument("--output", "-o", default="context.md",
                        help="Output file (default: context.md)")
    parser.add_argument("--name", "-n", default="",
                        help="Project name (defaults to directory name)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM analysis — static parsing only")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="Model to use, e.g. gpt-4o-mini, claude-3-5-haiku-20241022, "
                             "deepseek/deepseek-chat, gemini/gemini-2.0-flash (default: gpt-4o-mini)")
    parser.add_argument("--api-key", default="",
                        help="API key override (provider key is also read from env automatically)")
    args = parser.parse_args()

    # ------------------------------------------------------------------ clone
    source = args.source
    if source.startswith(("http://", "https://", "git@")):
        source = _clone(source)

    source_path = Path(source).resolve()
    if not source_path.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        sys.exit(1)

    project_name = args.name or source_path.name

    # ------------------------------------------------------------------ scan
    _step("Scanning repository")
    t0 = time.time()
    from ingest import RepoIngestor
    ingestor = RepoIngestor(str(source_path))
    files, tree = ingestor.scan()
    elapsed = time.time() - t0

    # Print progress bar once complete
    print(f"  {_bar(len(files), len(files))}  {dim(f'{elapsed:.1f}s')}")

    raw_chars = sum(f.char_count for f in files)

    # ------------------------------------------------------------------ LLM
    analysis = None
    semantic_rels = None
    api_key = ""

    if not args.no_llm:
        api_key = args.api_key
        if not api_key:
            # Try to read from the relevant env var for the chosen model prefix
            _ENV_VARS = [
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                "GEMINI_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY",
                "MISTRAL_API_KEY", "XAI_API_KEY", "PPLX_API_KEY",
                "OPENROUTER_API_KEY",
            ]
            for _var in _ENV_VARS:
                _val = os.getenv(_var, "")
                if _val:
                    api_key = _val
                    break
        if not api_key:
            try:
                from config import OPENAI_API_KEY
                api_key = OPENAI_API_KEY
            except ImportError:
                pass

        _step("LLM analysis")
        if api_key:
            print(f"  {dim('architecture ...')}", end="", flush=True)
            t1 = time.time()
            try:
                from analyze import ArchitectureAnalyzer
                analysis = ArchitectureAnalyzer(api_key=api_key, model=args.model).analyze(
                    files, tree, project_name
                )
                print(f"\r", end="")
                _spinner_done("Architecture analysis", f"{time.time()-t1:.1f}s")
            except Exception as exc:
                print(f"\r  {_c('31','!!')}  Architecture analysis failed: {exc}", file=sys.stderr)

            print(f"  {dim('semantic relationships ...')}", end="", flush=True)
            t2 = time.time()
            try:
                from relationships import discover_semantic_relationships
                semantic_rels = discover_semantic_relationships(
                    files, api_key, args.model
                )
                print(f"\r", end="")
                _spinner_done(
                    "Semantic relationships",
                    f"{len(semantic_rels)} found  {time.time()-t2:.1f}s"
                )
            except Exception as exc:
                print(f"\r  {_c('31','!!')}  Relationship discovery failed: {exc}", file=sys.stderr)
        else:
            print(f"  {dim('no API key found — static-only context')}")

    # ------------------------------------------------------------------ generate
    _step("Generating context file")
    from generate_prompt import PromptGenerator
    markdown = PromptGenerator().generate(
        files, analysis, project_name, semantic_rels, tree
    )

    out = Path(args.output)
    out.write_text(markdown, encoding="utf-8")
    _spinner_done(f"Written to {out.resolve()}")

    # ------------------------------------------------------------------ summary
    out_chars  = len(markdown)
    out_tokens = out_chars // 4
    raw_tokens = raw_chars // 4
    n_rels     = len(semantic_rels) if semantic_rels else 0
    pct        = (1 - out_tokens / max(raw_tokens, 1)) * 100

    _print_summary(project_name, len(files), raw_tokens, out_tokens, pct, n_rels, out)

    if _INTERACTIVE:
        input("\nPress Enter to close...")


def _print_summary(name, n_files, raw_tok, out_tok, pct, n_rels, out_path):
    w = 52
    border = "+" + "=" * w + "+"

    def row(text=""):
        pad = w - len(text)
        return "|" + bold(text) + " " * pad + "|"

    lines = [
        "",
        border,
        row(),
        row(f"  {magenta(name)} context ready"),
        row(),
        row(f"  {yellow(str(n_files))} files scanned"),
        row(f"  {yellow(f'{raw_tok:,}')} raw tokens  ->  {green(f'{out_tok:,}')} context tokens"),
        row(f"  {green(f'{pct:.0f}%')} compression  |  {yellow(str(n_rels))} semantic relationships"),
        row(f"  {dim(str(out_path))}"),
        row(),
        border,
        "",
    ]
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Git clone helper
# ---------------------------------------------------------------------------

def _clone(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    target = Path("repos") / name
    if target.exists():
        print(f"  Using cached clone at {target}")
        return str(target)
    target.parent.mkdir(exist_ok=True)
    print(f"  Cloning {url} ...")
    subprocess.run(["git", "clone", "--depth=1", url, str(target)], check=True)
    return str(target)


if __name__ == "__main__":
    main()
