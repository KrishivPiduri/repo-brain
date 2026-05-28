"""Assemble a markdown context file optimised for LLM consumption."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ingest import FileInfo
from analyze import ArchitectureAnalysis
from relationships import FileRelationship

_DATA_LANGS = {"YAML", "TOML", "JSON", "Markdown", "HTML", "CSS", "SCSS", "XML", "Text"}


class PromptGenerator:
    """Produces a single markdown file that gives an LLM instant codebase understanding."""

    def generate(
        self,
        files: list[FileInfo],
        analysis: Optional[ArchitectureAnalysis],
        project_name: str,
        semantic_rels: Optional[list[FileRelationship]] = None,
        tree: str = "",
    ) -> str:
        import_rels = [
            FileRelationship(source=f.path, target=dep, rel_type="imports",
                             description="", confidence=1.0)
            for f in files for dep in f.local_deps
        ]
        parts = [
            _header(project_name, analysis),
            _overview(analysis),
            _repo_structure(tree, files),
            _architecture(analysis),
            _relationships(semantic_rels or []),
            _file_reference(files),
            _patterns(analysis),
            _external_deps(files, analysis),
        ]
        return "\n\n".join(p for p in parts if p.strip())


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _header(project_name: str, analysis: Optional[ArchitectureAnalysis]) -> str:
    subtitle = ""
    if analysis and analysis.overview:
        first_sentence = analysis.overview.split(".")[0].strip()
        subtitle = f"\n> {first_sentence}."
    return (
        f"# CODEBASE CONTEXT: {project_name}\n"
        f"\n"
        f"> Auto-generated repository map. Use this file as context when working on the "
        f"codebase: it maps every file's purpose, public API, and relationships so you "
        f"don't need to read raw source to orient yourself.{subtitle}"
    )


def _overview(analysis: Optional[ArchitectureAnalysis]) -> str:
    if not analysis:
        return ""
    lines = ["## Project Overview", "", analysis.overview]
    if analysis.entry_points:
        lines += ["", "**Entry points**"]
        for ep in analysis.entry_points:
            lines.append(f"- `{ep}`")
    if analysis.data_flow:
        lines += ["", "**Data flow**"]
        for i, step in enumerate(analysis.data_flow, 1):
            lines.append(f"{i}. {step}")
    return "\n".join(lines)


def _repo_structure(tree: str, files: list[FileInfo]) -> str:
    lines = ["## Repository Structure", ""]
    if tree:
        lines.append("```")
        lines.append(tree)
        lines.append("```")
    else:
        # Fallback: flat listing grouped by top-level dir with full paths shown
        lines.append("```")
        for f in sorted(files, key=lambda x: x.path):
            marker = " [entry]" if f.is_entry_point else ""
            lines.append(f"{f.path}{marker}")
        lines.append("```")
    return "\n".join(lines)


def _architecture(analysis: Optional[ArchitectureAnalysis]) -> str:
    if not analysis:
        return ""
    lines = ["## Architecture"]

    if analysis.layers:
        lines += ["", "### Layers"]
        for layer in analysis.layers:
            files_str = " · ".join(f"`{f}`" for f in layer.get("files", [])[:5])
            lines.append(f"**{layer['name']}** - {layer['description']}")
            if files_str:
                lines.append(f"  -> {files_str}")

    if analysis.components:
        lines += ["", "### Components"]
        for comp in analysis.components:
            files_str = " · ".join(f"`{f}`" for f in comp.get("files", [])[:5])
            lines.append(f"**{comp['name']}** - {comp['role']}")
            if files_str:
                lines.append(f"  -> {files_str}")

    return "\n".join(lines)


def _relationships(semantic_rels: list[FileRelationship]) -> str:
    if not semantic_rels:
        return ""

    lines = ["## Semantic Relationships", ""]
    lines.append(
        "LLM-identified cross-file relationships: data flows, shared structures, "
        "potential redundancies, polyglot bridges."
    )
    lines.append("")

    type_labels = {
        "produces_for":      "Producer -> Consumer",
        "same_pipeline":     "Same Pipeline",
        "derived_from":      "Evolutionary / Derived",
        "shared_concept":    "Shared Concept (potential redundancy)",
        "cross_lang_bridge": "Cross-Language Bridge",
        "configures":        "Configuration",
        "imports":           "Direct Dependency",
    }

    by_type: dict[str, list[FileRelationship]] = {}
    for r in semantic_rels:
        by_type.setdefault(r.rel_type, []).append(r)

    for rel_type, rels in sorted(by_type.items()):
        label = type_labels.get(rel_type, rel_type)
        lines.append(f"**{label}**")
        for r in sorted(rels, key=lambda x: -x.confidence):
            conf = f" ({r.confidence:.0%})" if r.confidence < 1.0 else ""
            lines.append(f"- `{r.source}` -> `{r.target}`{conf}: {r.description}")
        lines.append("")

    return "\n".join(lines)


def _file_reference(files: list[FileInfo]) -> str:
    lines = [
        "## File Reference",
        "",
        "Source files only. Each entry: language, size, local deps, public API surface.",
        "",
    ]

    for f in sorted(files, key=lambda x: x.path):
        if _skip(f):
            continue
        _render_file(f, lines)

    return "\n".join(lines)


def _skip(f: FileInfo) -> bool:
    if f.language in _DATA_LANGS:
        return True
    if f.line_count <= 3:
        return True
    fname = Path(f.path).name
    if fname == "__init__.py" and not f.classes and not f.functions:
        return True
    return False


def _is_test(f: FileInfo) -> bool:
    return Path(f.path).name.startswith("test_") or "test_" in f.path.split("/")[-1]


def _render_file(f: FileInfo, lines: list):
    # --- header line ---
    meta = [f.language, f"{f.line_count}L"]
    if f.is_entry_point:
        meta.append("entry")
    lines.append(f"### `{f.path}`")
    lines.append("  ".join(meta))

    # --- description ---
    if f.description:
        first = f.description.splitlines()[0].strip()[:200]
        lines.append(f"*{first}*")

    # --- local deps (inline, compact) ---
    if f.local_deps:
        dep_names = [_short(d) for d in f.local_deps[:6]]
        extra = f" +{len(f.local_deps)-6}" if len(f.local_deps) > 6 else ""
        lines.append(f"deps: {', '.join(dep_names)}{extra}")

    if _is_test(f):
        test_fns = [fn.name for fn in f.functions if fn.name.startswith("test_")]
        if test_fns:
            lines.append(f"{len(test_fns)} test functions")
    else:
        # --- classes (compact, one line) ---
        if f.classes:
            names = [c.name for c in f.classes]
            shown = names[:7]
            extra = f"  +{len(names)-7} more" if len(names) > 7 else ""
            lines.append(f"classes: {' · '.join(shown)}{extra}")

        # --- public functions (compact, one line) ---
        pub = [fn.name for fn in f.functions if not fn.name.startswith("_")]
        if pub:
            shown = pub[:7]
            extra = f"  +{len(pub)-7} more" if len(pub) > 7 else ""
            lines.append(f"functions: {' · '.join(shown)}{extra}")

    lines.append("")


def _short(path: str) -> str:
    """Return just the stem of a local dep path."""
    return Path(path).stem


def _patterns(analysis: Optional[ArchitectureAnalysis]) -> str:
    if not analysis or not analysis.patterns:
        return ""
    lines = ["## Key Patterns & Conventions", ""]
    for p in analysis.patterns:
        lines.append(f"- {p}")
    return "\n".join(lines)


def _external_deps(files: list[FileInfo], analysis: Optional[ArchitectureAnalysis]) -> str:
    lines = ["## External Dependencies", ""]

    if analysis and analysis.external_deps:
        for dep in analysis.external_deps:
            lines.append(f"- **{dep['name']}** - {dep['purpose']}")
        return "\n".join(lines)

    _STDLIB = {
        "__future__", "os", "sys", "re", "json", "typing", "dataclasses", "pathlib",
        "collections", "functools", "itertools", "abc", "copy", "io",
        "struct", "hashlib", "uuid", "enum", "contextlib", "inspect",
        "ast", "subprocess", "threading", "time", "datetime", "math",
        "random", "string", "logging", "warnings", "traceback", "types",
        "weakref", "gc", "importlib", "pkgutil", "platform", "socket",
    }
    seen: set[str] = set()
    for f in files:
        for imp in f.imports:
            if f.language == "Python":
                m = re.match(r'(?:from|import)\s+([\w.]+)', imp)
                if m:
                    mod = m.group(1).split(".")[0]
                    if mod not in _STDLIB:
                        seen.add(mod)
    for dep in sorted(seen)[:30]:
        lines.append(f"- `{dep}`")
    return "\n".join(lines)
