#!/usr/bin/env python3
"""
=============================================================================
MODULE: Snippet Library
=============================================================================
File-backed snippet storage for the Workbench Sidekick "Special Characters"
and "Personal Snippets" menus.

Each snippet is a single `.md` file under `<user_data>/snippet_library/`.
File body (after optional YAML-ish front matter delimited by `---`) is the
payload inserted at the cursor when the snippet is clicked. Folder structure
maps to tree categories: a file at

    snippet_library/Special Characters/Arrows.md

appears under "Special Characters" in the Sidekick menu.

The format intentionally mirrors the prompt library's `.md` convention
(`type: prompt` → `type: snippet`) so the two can be unified behind a
single "Library" editor later without a data migration.

Default snippets are defined in `DEFAULT_SNIPPETS` and written to disk on
first launch if missing. Users can edit, delete, or add their own .md files
freely – defaults are re-seeded only when absent, never overwriting edits.

Author: Michael Beijer (Claude-assisted)
=============================================================================
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple
import re


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """Split optional YAML-ish front matter from body. Returns (meta, body)."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, text[m.end():]


class SnippetLibrary:
    """Load snippets from a directory tree. Mirrors UnifiedPromptLibrary's pattern."""

    def __init__(self, library_dir: Optional[str] = None, log_callback=None):
        self.library_dir = Path(library_dir) if library_dir else None
        self.log = log_callback or (lambda _msg: None)
        self.snippets: List[Dict] = []  # [{label, body, category, path}]

        if self.library_dir:
            try:
                self.library_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.log(f"[SnippetLibrary] Cannot create {self.library_dir}: {e}")

    def load_all(self) -> int:
        """Walk the library directory and populate self.snippets. Returns count."""
        self.snippets = []
        if not self.library_dir or not self.library_dir.exists():
            return 0

        for md in sorted(self.library_dir.rglob("*.md")):
            if md.name.startswith('.'):
                continue
            try:
                raw = md.read_text(encoding='utf-8')
                meta, body = _split_front_matter(raw)
                rel = md.relative_to(self.library_dir)
                parts = list(rel.parts)
                # Folder(s) above the file form the category.
                # For now we only use the top-level folder for tree grouping;
                # deeper nesting can be wired up later without changing the file format.
                category = parts[0] if len(parts) > 1 else ""
                label = meta.get('name') or md.stem
                self.snippets.append({
                    'label': label,
                    'body': body.rstrip("\n"),
                    'category': category,
                    'path': md,
                })
            except Exception as e:
                self.log(f"[SnippetLibrary] Skip {md.name}: {e}")

        return len(self.snippets)

    def ensure_defaults(self, default_defs: List[Dict]) -> int:
        """Write any missing default snippet files. Idempotent. Returns files created."""
        if not self.library_dir:
            return 0

        created = 0
        for defn in default_defs:
            category = defn.get('category', '')
            folder = self.library_dir / category if category else self.library_dir
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.log(f"[SnippetLibrary] Cannot create folder {folder}: {e}")
                continue

            # Filename comes from the explicit `filename` field if given, falling
            # back to a sanitised version of `name`. This lets the display label
            # (front-matter `name:`, shown in the Sidekick tree) carry unicode
            # glyphs while the on-disk filename stays ASCII-safe and predictable.
            raw_filename = defn.get('filename') or defn.get('name') or 'snippet'
            filename = self._safe_filename(raw_filename) + '.md'
            filepath = folder / filename

            if not filepath.exists():
                try:
                    self._write_default(filepath, defn)
                    created += 1
                except Exception as e:
                    self.log(f"[SnippetLibrary] Cannot write {filepath}: {e}")

        return created

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Strip characters that are invalid in Windows filenames."""
        invalid = '<>:"/\\|?*'
        cleaned = ''.join(c if c not in invalid else '_' for c in name).strip().strip('.')
        return cleaned or "snippet"

    @staticmethod
    def _write_default(filepath: Path, defn: Dict):
        """Write a single default snippet definition to a .md file."""
        lines = [
            '---',
            'type: snippet',
            f'name: "{defn["name"]}"',
        ]
        if defn.get('category'):
            lines.append(f'category: "{defn["category"]}"')
        lines.append('default: true')
        lines.append('read_only: true')
        lines.append('---')
        lines.append('')
        lines.append(defn.get('body', ''))
        filepath.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------
# Default snippets
#
# Migrated from the hardcoded entries in modules/floating_assistant.py as of
# v1.9.386. ASCII-safe filenames; display labels come from the `name:`
# front-matter field so decorative unicode glyphs can be added freely.
#
# The "Personal Snippets" category ships with a single placeholder so the
# category appears in the menu, explaining how to add entries. The previous
# hardcoded "Mobile number" entry containing a real phone number has been
# removed entirely.
# ---------------------------------------------------------------------------

DEFAULT_SNIPPETS: List[Dict] = [
    # -- Special Characters --
    #
    # Each entry has three fields:
    #   `filename` – the on-disk .md file stem (ASCII-safe, stable across OSes)
    #   `name`     – the display label shown in the Sidekick menu (free to use
    #                unicode glyphs so you can see at a glance what you're
    #                about to insert)
    #   `body`     – the actual text inserted at the cursor on click
    #
    # Users can edit any of these freely in the generated .md files; we never
    # overwrite once a file exists. If you want the old plain-word labels
    # back, just change the `name:` line in the front matter.
    {"category": "Special Characters", "filename": "Misc symbols",
     "name": "\u25A3 \u25A0 \u25EF \u25B6 \u25C6",
     "body": "\u25A3 \u25A0 \u25A1 \u25A2 \u25EF \u25B2 \u25B6 \u25BA \u25BC \u25C6 \u25E2 \u25E3 \u25E4 \u25E5"},
    {"category": "Special Characters", "filename": "Arrows",
     "name": "\u2190 \u2192 \u2191 \u2193 \u21C4 \u2194",
     "body": "\u2190 \u2192 \u2191 \u2193 \u27EB \u2B07 \u2B06 \u21C4 \u2194"},
    {"category": "Special Characters", "filename": "Primes",
     "name": "\u2032 \u2033 \u2034",
     "body": "\u2032 \u2033 \u2034 \u2057"},
    {"category": "Special Characters", "filename": "Dashes and quotes",
     "name": "\u2013 \u2014 \u00AB \u00BB \u201C \u201D",
     "body": "\u2013 \u2014 \u00AB \u00BB \u2039 \u203A \u201C \u201D \u201E \u201A"},
    {"category": "Special Characters", "filename": "Currency",
     "name": "\u20AC \u00A3 $ \u00A5 \u00A2",
     "body": "\u00A5 \u20AC $ \u00A2 \u00A3"},
    {"category": "Special Characters", "filename": "Legal symbols",
     "name": "\u00A9 \u00AE \u2122 \u00B0 \u2030",
     "body": "\u00A9 \u00AE @ \u2122 \u00B0 \u2030"},
    {"category": "Special Characters", "filename": "Maths symbols",
     "name": "\u00B1 \u00D7 \u00F7 \u2260 \u03C0 \u221E",
     "body": "\u00B1 \u00D7 ~ \u2248 \u00F7 \u2260 \u03C0 \u221E"},
    {"category": "Special Characters", "filename": "Bullets",
     "name": "\u2022 \u25CF \u00B7 \u2026",
     "body": "\u2026 \u00B7 \u2022 \u25CF"},

    # -- Personal Snippets --
    # Placeholder so the category appears in the menu with guidance for
    # first-time users. Shipping an example here is intentional; it should
    # NOT contain anything personal or sensitive.
    {"category": "Personal Snippets", "filename": "Example snippet",
     "name": "Example snippet",
     "body": "This is a sample snippet. Edit this file or add new .md files "
             "under snippet_library/Personal Snippets/ to build your own "
             "library of reusable text."},
]
