"""MCP server exposing repo-context generation as a tool."""
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ingest import RepoIngestor
from generate_prompt import PromptGenerator

mcp = FastMCP("repo-brain")


@mcp.tool()
def generate_context(
    source_dir: str,
    output_file: str = "",
    project_name: str = "",
    no_llm: bool = False,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Parse a repository and return a markdown context file mapping its structure.

    Args:
        source_dir:   Absolute path to the repo root.
        output_file:  If provided, also write the markdown to this path.
        project_name: Override the project name (defaults to directory name).
        no_llm:       Skip LLM architecture analysis and do static parsing only.
        model:        OpenAI model to use for analysis (default gpt-4o-mini).

    Returns:
        The generated markdown string.
    """
    root = Path(source_dir).resolve()
    if not root.exists():
        return f"Error: {source_dir} does not exist."

    name = project_name or root.name

    ingestor = RepoIngestor(str(root))
    files, tree = ingestor.scan()

    analysis = None
    semantic_rels = None
    if not no_llm:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            try:
                from analyze import ArchitectureAnalyzer
                analysis = ArchitectureAnalyzer(api_key=api_key, model=model).analyze(
                    files, tree, name
                )
            except Exception:
                pass
            try:
                from relationships import discover_semantic_relationships
                semantic_rels = discover_semantic_relationships(files, api_key, model)
            except Exception:
                pass

    markdown = PromptGenerator().generate(files, analysis, name, semantic_rels, tree)

    if output_file:
        Path(output_file).write_text(markdown, encoding="utf-8")

    return markdown


@mcp.tool()
def get_file_structure(source_dir: str) -> str:
    """
    Return a quick annotated directory tree and file manifest without LLM analysis.

    Args:
        source_dir: Absolute path to the repo root.

    Returns:
        Plain-text directory tree.
    """
    root = Path(source_dir).resolve()
    if not root.exists():
        return f"Error: {source_dir} does not exist."

    ingestor = RepoIngestor(str(root))
    files, tree = ingestor.scan()

    lines = [tree, "", f"Files scanned: {len(files)}", ""]
    for f in sorted(files, key=lambda x: x.path):
        desc = f.description.splitlines()[0][:80] if f.description else ""
        entry = " [entry]" if f.is_entry_point else ""
        lines.append(f"{f.path}{entry}  ({f.language}, {f.line_count}L){('  — ' + desc) if desc else ''}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
