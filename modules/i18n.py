"""
Supervertaler Workbench internationalisation (i18n) support.

Added in v1.10.207 as the MVP infrastructure for translating the UI into
other languages. The MVP scope is deliberately narrow: menu bar, toolbar,
Settings tabs, and primary dialog buttons – enough to give a translated
build the "speaks your language" feel without committing to a multi-week
pass over every string in the codebase. Body text, log messages, and
non-primary tooltips remain in English for v1.

# Why a custom QTranslator instead of plain Qt + lrelease

The standard Qt workflow is:
    1. Wrap user-facing strings in ``self.tr("...")``
    2. Extract with ``pylupdate6`` → ``.ts`` (Qt Linguist XML)
    3. Translate in Qt Linguist
    4. Compile with ``lrelease`` → ``.qm`` (binary, fast load)
    5. ``QTranslator.load(qm_path)`` at startup

We ship PyQt6 which includes ``pylupdate6`` but NOT ``lrelease`` (that
binary lives in Qt's Linguist tooling, separate package). Adding a build-
time dependency on ``pyside6-essentials`` or the Qt SDK just to compile
``.qm`` files would bloat the build environment for marginal benefit –
the speed difference between ``.qm`` and ``.ts`` is microseconds for our
string count.

So this module ships a ``TsTranslator`` (subclass of ``QTranslator``) that
reads ``.ts`` XML directly at startup. Everything downstream still works
exactly as Qt expects: ``self.tr()`` calls go through ``QCoreApplication``'s
installed translators, ``changeEvent(LanguageChange)`` fires correctly,
contexts work the standard way (class name of the calling QObject).

End-to-end workflow for translators:
    1. Open the ``.ts`` for their locale in Qt Linguist (free download)
    2. Translate strings, mark as "finished" (green tick)
    3. PR the updated ``.ts`` back
    4. Workbench loads it directly on next launch in that locale

No build step required on the translator's machine or ours.

# Locale handling

Locales follow Qt's `language[_TERRITORY]` form:
    - ``en``       – English (default, no translation file needed)
    - ``zh_CN``    – Simplified Chinese
    - ``zh_TW``    – Traditional Chinese
    - ``pl``       – Polish

The active locale is read from the General settings dict; ``"system"``
falls back to ``QLocale.system().name()``. A missing ``.ts`` file is not
an error – ``self.tr()`` just returns the source string (English).

A restart is required after changing the language. This is a deliberate
MVP simplification: live re-translation requires every widget to handle
``changeEvent(QEvent.LanguageChange)`` correctly, which is a non-trivial
audit on a 60k-line hand-coded UI. The Settings panel surfaces a notice
when the language is changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from PyQt6.QtCore import QLocale, QTranslator


# Locales we explicitly know about. Used by the Settings dropdown so
# users see human-readable names rather than ISO codes.  The MVP ships
# infrastructure only; the ``.ts`` files for any locale beyond ``en`` are
# added as translators contribute them (issue #178: Chinese, #190: Polish).
SUPPORTED_LOCALES: list[tuple[str, str]] = [
    ("en",    "English"),
    ("zh_CN", "中文 (简体) — Simplified Chinese"),
    ("zh_TW", "中文 (繁體) — Traditional Chinese"),
    ("pl",    "Polski — Polish"),
    ("de",    "Deutsch — German"),
    ("fr",    "Français — French"),
    ("es",    "Español — Spanish"),
    ("nl",    "Nederlands — Dutch"),
    ("ja",    "日本語 — Japanese"),
    ("ko",    "한국어 — Korean"),
    ("ru",    "Русский — Russian"),
]


def translations_dir() -> Path:
    """Resolve the translations folder regardless of how Workbench is invoked.

    Looks in two places (in order):
        1. ``<repo_root>/translations`` for source-tree runs
        2. ``<exe_dir>/translations`` for PyInstaller bundles

    Returns the first folder that exists.  Falls back to the source-tree
    path even when the folder is missing so callers can ``mkdir`` against
    it without further branching.
    """
    # Source-tree path: this file is at modules/i18n.py, so parent.parent is repo root
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / "translations"
    if candidate.exists():
        return candidate

    # PyInstaller frozen-exe path: try alongside the exe
    import sys
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bundled = exe_dir / "translations"
        if bundled.exists():
            return bundled

    # Default – may not exist yet
    return candidate


class TsTranslator(QTranslator):
    """A ``QTranslator`` that reads Qt Linguist ``.ts`` XML directly.

    Subclasses ``QTranslator`` so Qt's standard ``self.tr(...)`` plumbing
    routes lookups through ``translate()`` exactly as it would for a
    binary ``.qm`` file – no special API the rest of the codebase needs
    to know about.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Keyed by (context, source, disambiguation_or_None).  ``disambiguation``
        # is the optional second argument to ``tr()`` used when the same English
        # source needs different translations in different places.
        self._entries: dict[tuple[str, str, Optional[str]], str] = {}
        self._loaded_locale: Optional[str] = None
        self._loaded_path: Optional[Path] = None

    # ─── Loading ──────────────────────────────────────────────────────

    def load_ts_file(self, ts_path: Path) -> bool:
        """Load a single ``.ts`` file. Returns True on success.

        Skips entries marked ``type="unfinished"`` so partially-translated
        strings show the English source rather than a half-translated mess.
        Also skips entries where the translation element is missing or empty.
        """
        self._entries.clear()
        try:
            tree = ET.parse(str(ts_path))
        except (ET.ParseError, OSError):
            return False

        root = tree.getroot()
        for context_elem in root.findall("context"):
            ctx_name = (context_elem.findtext("name") or "").strip()
            for msg in context_elem.findall("message"):
                source = msg.findtext("source")
                if not source:
                    continue
                translation_elem = msg.find("translation")
                if translation_elem is None:
                    continue
                # Unfinished translations: fall through to English.
                if translation_elem.get("type") == "unfinished":
                    continue
                translated = (translation_elem.text or "").strip()
                if not translated:
                    continue
                disambiguation = msg.findtext("comment") or None
                self._entries[(ctx_name, source, disambiguation)] = translated

        self._loaded_path = ts_path
        return True

    def load_locale(self, locale_code: str) -> bool:
        """Load the ``.ts`` file matching ``locale_code`` from translations/.

        Returns True if a translation file was found and loaded with at
        least one finished entry. False on missing file, parse error, or
        zero finished entries – the caller can then skip installing this
        translator entirely so Qt's ``tr()`` short-circuits to the source.
        """
        if not locale_code or locale_code.lower() == "en":
            # English is the source language – no translation file needed.
            self._loaded_locale = "en"
            return False

        ts_path = translations_dir() / f"supervertaler_{locale_code}.ts"
        if not ts_path.exists():
            return False

        if not self.load_ts_file(ts_path):
            return False

        if not self._entries:
            return False

        self._loaded_locale = locale_code
        return True

    # ─── QTranslator overrides ────────────────────────────────────────

    def translate(  # type: ignore[override]
        self,
        context: str,
        source_text: str,
        disambiguation: Optional[str] = None,
        n: int = -1,
    ) -> str:
        """Look up a translation. Empty string = "no translation, use source".

        Qt's contract: returning an empty string tells the next translator
        in the chain (or the source itself) to take over. We return the
        translation when found, "" otherwise.
        """
        # Most specific first: (ctx, src, disambig)
        if disambiguation:
            value = self._entries.get((context, source_text, disambiguation))
            if value:
                return value
        # Then context-only
        value = self._entries.get((context, source_text, None))
        if value:
            return value
        # Then any-context fallback (handles strings translated under a
        # different context than the caller's class – e.g. menu items that
        # appear in helper functions).  Cheap because dict scan is on at
        # most a few hundred entries for the MVP.
        for (ctx, src, disambig), trans in self._entries.items():
            if src == source_text and disambig == disambiguation:
                return trans
        # Not found – Qt falls back to the source string.
        return ""

    def isEmpty(self) -> bool:  # type: ignore[override]
        return not self._entries

    # ─── Introspection ─────────────────────────────────────────────────

    @property
    def loaded_locale(self) -> Optional[str]:
        """The locale code that was successfully loaded, or None."""
        return self._loaded_locale

    @property
    def loaded_path(self) -> Optional[Path]:
        """The .ts file path that was loaded, or None."""
        return self._loaded_path

    def entry_count(self) -> int:
        """Number of finished translation entries currently loaded."""
        return len(self._entries)


# ─── Module-level helpers ──────────────────────────────────────────────


def resolve_locale(setting_value: Optional[str]) -> str:
    """Resolve the user-configured locale setting to an active locale code.

    ``setting_value`` comes from the General settings dict (or env override).
    Special values:
        - ``None`` or ``""``  → fall back to ``"system"``
        - ``"system"``        → use ``QLocale.system().name()``
        - ``"en"``            → English (no translation file loaded)
        - any other string    → used as-is (e.g. ``"zh_CN"``)
    """
    if not setting_value or setting_value.lower() == "system":
        try:
            return QLocale.system().name() or "en"
        except Exception:
            return "en"
    return setting_value


def install_translator_for_locale(
    app, locale_code: str
) -> Optional[TsTranslator]:
    """Convenience: build a TsTranslator, try to load, install on app if found.

    Returns the installed translator on success, None when the requested
    locale has no .ts file or the file is empty/broken. Caller can log the
    outcome and proceed – English is the safe fallback in every branch.
    """
    if not locale_code or locale_code.lower() == "en":
        return None

    translator = TsTranslator()
    if not translator.load_locale(locale_code):
        return None

    app.installTranslator(translator)
    return translator
