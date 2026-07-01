"""Skill loader: inject reusable Azure/ADF knowledge into the agent's prompt.

This mirrors the "Skills for Fabric" idea but for THIS agent's platform (ADF) and
THIS agent's LLM. A skill is a markdown file under ``skills/`` with optional
frontmatter (name/description). At session start the loader reads every ``.md``
file and concatenates the bodies into one block that the parser appends to its
system prompt — so the model "learns" the skills as in-context instructions.

Add a new skill by dropping a ``.md`` file into ``skills/`` — no code change needed.
Skills are static knowledge (they don't execute); the deterministic builder still
does the actual ADF JSON generation.
"""

from __future__ import annotations

import functools
import os
from typing import List, Tuple

# skills/ lives at the project root (one level up from this agent/ package).
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


def _split_frontmatter(text: str) -> Tuple[str, str]:
    """Return (name, body). Strips a leading ``---`` frontmatter block and pulls out
    the ``name:`` field if present."""
    name = ""
    body = text
    if text.lstrip().startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            front, body = parts[1], parts[2]
            for line in front.splitlines():
                if line.strip().lower().startswith("name:"):
                    name = line.split(":", 1)[1].strip()
    return name, body.strip()


def list_skills(skills_dir: str = _SKILLS_DIR) -> List[str]:
    """Names of the skill files that will be loaded (for logging / the UI)."""
    if not os.path.isdir(skills_dir):
        return []
    names: List[str] = []
    for fname in sorted(os.listdir(skills_dir)):
        if fname.endswith(".md"):
            with open(os.path.join(skills_dir, fname), "r", encoding="utf-8") as fh:
                name, _ = _split_frontmatter(fh.read())
            names.append(name or fname[:-3])
    return names


@functools.lru_cache(maxsize=1)
def load_skills(skills_dir: str = _SKILLS_DIR) -> str:
    """Concatenate every skill body into one prompt-ready block. Cached so files are
    read once per process. Returns '' when there are no skills."""
    if not os.path.isdir(skills_dir):
        return ""
    blocks: List[str] = []
    for fname in sorted(os.listdir(skills_dir)):
        if not fname.endswith(".md"):
            continue
        with open(os.path.join(skills_dir, fname), "r", encoding="utf-8") as fh:
            _, body = _split_frontmatter(fh.read())
        if body:
            blocks.append(body)
    if not blocks:
        return ""
    header = (
        "# Azure / ADF Skills\n"
        "Reusable, authoritative guidance for generating Azure Data Factory artifacts. "
        "Follow these exactly; they reflect real ADF behavior.\n"
    )
    return header + "\n\n---\n\n".join(blocks)
