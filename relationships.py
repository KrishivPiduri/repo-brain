"""Discover relationships between files — static import graph + LLM semantic analysis."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ingest import FileInfo

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

REL_TYPES = {
    "imports":           "Direct import / require dependency",
    "produces_for":      "A produces data or objects consumed by B",
    "same_pipeline":     "Sequential steps in the same data-processing flow",
    "derived_from":      "B is an evolved or refactored version of A",
    "shared_concept":    "Parallel implementations of the same idea (potential redundancy)",
    "cross_lang_bridge": "Polyglot interface — one side calls or is called by the other language",
    "configures":        "A supplies configuration or constants consumed by B",
}


@dataclass
class FileRelationship:
    source: str         # relative file path
    target: str         # relative file path
    rel_type: str       # one of REL_TYPES keys
    description: str
    confidence: float   # 1.0 = static fact, <1.0 = LLM inference
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Static import-graph resolution
# ---------------------------------------------------------------------------

def resolve_import_graph(files: list[FileInfo]) -> list[FileRelationship]:
    """Resolve each file's raw imports to local file paths, returning direct-dep edges."""
    path_set = {f.path for f in files}
    file_map = {f.path: f for f in files}
    relationships: list[FileRelationship] = []

    for f in files:
        resolved = _resolve_deps(f, path_set)
        for dep in resolved:
            if dep != f.path:
                relationships.append(FileRelationship(
                    source=f.path,
                    target=dep,
                    rel_type="imports",
                    description=f"`{f.path}` imports from `{dep}`",
                    confidence=1.0,
                ))
    return relationships


def _resolve_deps(f: FileInfo, path_set: set[str]) -> list[str]:
    if f.language == "Python":
        return _resolve_python(f, path_set)
    if f.language in ("JavaScript", "TypeScript"):
        return _resolve_js(f, path_set)
    if f.language == "Rust":
        return _resolve_rust(f, path_set)
    return []


def _resolve_python(f: FileInfo, path_set: set[str]) -> list[str]:
    result: list[str] = []
    for imp in f.imports:
        m = re.match(r'(?:from|import)\s+([\w.]+)', imp)
        if not m:
            continue
        module = m.group(1)
        parts = module.split(".")
        # Try absolute from repo root
        candidates = [
            "/".join(parts) + ".py",
            "/".join(parts) + "/__init__.py",
        ]
        # Try relative to the file's own directory
        parent = str(Path(f.path).parent)
        if parent and parent != ".":
            candidates += [
                parent + "/" + "/".join(parts) + ".py",
                parent + "/" + parts[0] + ".py",
            ]
        for c in candidates:
            c = c.lstrip("./")
            if c in path_set:
                result.append(c)
                break
    return result


def _resolve_js(f: FileInfo, path_set: set[str]) -> list[str]:
    result: list[str] = []
    parent = str(Path(f.path).parent).replace("\\", "/")
    for imp in f.imports:
        m = re.search(r"from\s+['\"](\.[^'\"]+)['\"]", imp)
        if not m:
            continue
        raw = m.group(1)
        base = (parent + "/" + raw).replace("\\", "/")
        # normalise .. segments crudely
        parts = base.split("/")
        stack: list[str] = []
        for p in parts:
            if p == "..":
                if stack:
                    stack.pop()
            elif p and p != ".":
                stack.append(p)
        base = "/".join(stack)
        for ext in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
            candidate = base + ext if not any(base.endswith(e) for e in (".ts", ".tsx", ".js", ".jsx")) else base
            if candidate in path_set:
                result.append(candidate)
                break
    return result


def _resolve_rust(f: FileInfo, path_set: set[str]) -> list[str]:
    result: list[str] = []
    parent = str(Path(f.path).parent).replace("\\", "/")
    for imp in f.imports:
        # "use crate::module::..." or "use super::module"
        m = re.match(r'(?:crate|super)::([\w:]+)', imp)
        if not m:
            continue
        parts = m.group(1).split("::")
        candidates = [
            parent + "/" + "/".join(parts) + ".rs",
            "/".join(parts) + ".rs",
        ]
        for c in candidates:
            if c in path_set:
                result.append(c)
                break
    return result


# ---------------------------------------------------------------------------
# LLM semantic relationship discovery
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a senior software architect performing codebase relationship mapping. "
    "Given a file manifest, identify non-obvious semantic relationships between files. "
    "Focus on producer-consumer links, shared data structures, parallel implementations, "
    "and cross-language bridges. Skip relationships already obvious from direct imports. "
    "Respond ONLY with valid JSON."
)

_SCHEMA = """{
  "relationships": [
    {
      "source": "path/to/file_a.py",
      "target": "path/to/file_b.py",
      "type": "produces_for | same_pipeline | derived_from | shared_concept | cross_lang_bridge | configures",
      "description": "one sentence explaining the connection",
      "confidence": 0.0,
      "evidence": ["shared symbol or pattern that supports this"]
    }
  ]
}"""


def discover_semantic_relationships(
    files: list[FileInfo],
    api_key: str,
    model: str = "gpt-4o-mini",
    max_relationships: Optional[int] = None,
) -> list[FileRelationship]:
    """Single LLM call over the file manifest to find semantic cross-file links."""
    if max_relationships is None:
        max_relationships = len(files)

    from llm import complete_json
    manifest = _build_manifest(files)
    prompt = (
        f"File manifest:\n{manifest}\n\n"
        f"Identify up to {max_relationships} notable semantic relationships between these files.\n"
        f"Ignore trivial or obvious import chains already visible in the manifest.\n"
        f"Focus on: producer-consumer data flows, shared data structures, "
        f"parallel/redundant implementations, polyglot bridges.\n\n"
        f"Respond with JSON matching this schema:\n{_SCHEMA}"
    )

    try:
        data = complete_json(model, _SYSTEM, prompt, api_key)
    except Exception as exc:
        print(f"  Semantic relationship discovery failed: {exc}")
        return []

    path_set = {f.path for f in files}
    result: list[FileRelationship] = []
    for r in data.get("relationships", []):
        src, tgt = r.get("source", ""), r.get("target", "")
        if src in path_set and tgt in path_set and src != tgt:
            result.append(FileRelationship(
                source=src,
                target=tgt,
                rel_type=r.get("type", "same_pipeline"),
                description=r.get("description", ""),
                confidence=float(r.get("confidence", 0.7)),
                evidence=r.get("evidence", []),
            ))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_manifest(files: list[FileInfo]) -> str:
    lines: list[str] = []
    _STDLIB = {
        "__future__", "os", "sys", "re", "json", "typing", "dataclasses",
        "pathlib", "collections", "functools", "itertools", "abc", "copy",
        "io", "hashlib", "uuid", "enum", "contextlib", "inspect", "ast",
        "subprocess", "threading", "time", "datetime", "math",
    }
    for f in files:
        lines.append(f"### {f.path}  ({f.language}, {f.line_count}L)")
        if f.description:
            lines.append(f"  doc: {f.description.splitlines()[0][:150]}")
        # Only third-party + local imports
        key = []
        for imp in f.imports:
            if f.language == "Python":
                m = re.match(r'(?:from|import)\s+([\w.]+)', imp)
                if m and m.group(1).split(".")[0] not in _STDLIB:
                    key.append(m.group(1).split(".")[0])
            else:
                key.append(imp[:40])
        if key:
            seen: set[str] = set()
            deduped = [x for x in key if x not in seen and not seen.add(x)]  # type: ignore[func-returns-value]
            lines.append(f"  imports: {', '.join(deduped[:8])}")
        if f.classes:
            lines.append(f"  classes: {', '.join(c.name for c in f.classes)}")
        pub = [fn.name for fn in f.functions if not fn.name.startswith("_")]
        if pub:
            lines.append(f"  functions: {', '.join(pub[:8])}")
    return "\n".join(lines)


def group_by_target(rels: list[FileRelationship]) -> dict[str, list[FileRelationship]]:
    """Group relationships by their target file for reverse-lookup."""
    groups: dict[str, list[FileRelationship]] = {}
    for r in rels:
        groups.setdefault(r.target, []).append(r)
    return groups
