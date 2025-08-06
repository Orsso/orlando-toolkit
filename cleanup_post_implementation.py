#!/usr/bin/env python3
"""
Post-implementation cleanup script for merge refactor (TASK 6).

Behavior summary:
- Walk repository from project root.
- Skip venvs, caches, binaries; scan .py and .md; modify only .py.
- Remove old merge functions/uses:
  * Calls:
      merge_topics_unified(...) -> apply_depth_change(...)
      merge_topics_by_titles(...) -> REMOVE statement
      _collapse_redundant_sections(...), _ensure_content_module(...) -> REMOVE statement
  * Imports:
      Replace old imports with:
      from orlando_toolkit.core.merge import apply_depth_change, merge_topics_manually, apply_style_exclusions
- Consolidate duplicate literal implementations for preserved title fragment:
  * Detect duplicates that produce "<p><b><u>{title}</u></b></p>" (or exact literal)
  * If duplicates exist: ensure a single helper in orlando_toolkit/core/utils.py:
      def build_preserved_title_fragment(title: str) -> str:
          return f"<p><b><u>{title}</u></b></p>"
    Replace duplicates with utils.build_preserved_title_fragment(title)
- Remove dead code and unused constants related to pre-refactor merge helpers when clearly unused.
  (Only trivial, safe removals: imports/definitions of removed helpers without references.)
- Validate duplicates via textual hash of function bodies and log suspects (no auto-removal beyond above steps).
- Generate docs/cleanup_report_[YYYYmmdd_HHMMSS].md with:
  files scanned, files modified, replacements, removals, consolidations, suspected duplicates.

Idempotent and safe: running multiple times should not produce further changes.

Run: python cleanup_post_implementation.py
"""

from __future__ import annotations

import os
import re
import sys
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Tuple, Set, Optional

# -----------------------
# Configuration
# -----------------------

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
    "site-packages",
    "venv",
    ".venv",
    "env",
    ".env",
}

TEXT_EXTS_SCAN = {".py", ".md"}
EDIT_EXTS = {".py"}

# Legacy names and mappings
LEGACY_CALL_REPLACEMENTS = {
    # direct call replacements
    "merge_topics_unified": ("apply_depth_change", "replace"),
    "merge_topics_by_titles": (None, "remove_stmt"),
    "_collapse_redundant_sections": (None, "remove_stmt"),
    "_ensure_content_module": (None, "remove_stmt"),
}

# Any import mentioning old names should be replaced by this import line
NEW_IMPORT_LINE = "from orlando_toolkit.core.merge import apply_depth_change, merge_topics_manually, apply_style_exclusions"

# -----------------------
# Utilities
# -----------------------

def _is_text_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext in TEXT_EXTS_SCAN


def _is_editable_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext in EDIT_EXTS


def _should_skip_dir(dirname: str) -> bool:
    base = os.path.basename(dirname)
    return base in SKIP_DIRS


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        try:
            # fallback latin-1 if some file is odd but text-like
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception:
            return None


def _write_file_if_changed(path: str, new_content: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            old = f.read()
    except Exception:
        old = None
    if old == new_content:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _iter_files(root: str) -> List[str]:
    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune directories
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(os.path.join(dirpath, d))]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            # skip obvious binaries
            _, ext = os.path.splitext(fn)
            if ext.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".zip", ".exe", ".dll"}:
                continue
            files.append(p)
    return files


def _strip_comments_and_whitespace(code: str) -> str:
    # Minimal normalization for duplication hashing (Python only)
    # Remove comments and compress whitespace lines
    lines: List[str] = []
    for line in code.splitlines():
        ls = line.strip()
        if ls.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_function_bodies_py(content: str) -> Dict[str, str]:
    """
    Naively parse top-level def bodies for hashing.
    This is heuristic, not a full parser.
    """
    results: Dict[str, str] = {}
    pattern = re.compile(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*?\):\s*$", re.MULTILINE)
    for m in pattern.finditer(content):
        name = m.group(1)
        start = m.end()
        # Grab until next def/class at column 0
        rest = content[start:]
