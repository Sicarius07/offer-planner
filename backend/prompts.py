"""Loads prompts/*.md. Each file: YAML frontmatter, then `# System` and `# User` sections.

`{{name}}` placeholders in the user section are filled at call time. The version recorded in
traces is `v<frontmatter version>-<content hash>`, so any edit to a prompt is visible in
traces and eval reports even if someone forgets to bump the number
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from backend.config import PROMPTS_DIR

_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: str

    def render(self, **variables: object) -> tuple[str, str]:
        def sub(m: re.Match) -> str:
            key = m.group(1)
            if key not in variables:
                raise KeyError(f"prompt '{self.name}' needs variable '{key}'")
            return str(variables[key])

        return _VAR.sub(sub, self.system), _VAR.sub(sub, self.user)


@lru_cache
def load(name: str) -> Prompt:
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text()
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front) or {}
    parts = re.split(r"^# (System|User)\s*$", body, flags=re.MULTILINE)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    digest = hashlib.sha256(text.encode()).hexdigest()[:7]
    return Prompt(
        name=name,
        version=f"v{meta.get('version', 0)}-{digest}",
        system=sections.get("System", ""),
        user=sections.get("User", ""),
    )
