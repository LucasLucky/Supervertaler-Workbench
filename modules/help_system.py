"""
Context-sensitive help system for Supervertaler.

Opens the relevant documentation page when the user presses F1
or uses the Help > Context Help menu action.

Usage:
    from modules.help_system import Topics, install, set_topic, open_help

    # Install the event filter on the main window (call once at startup):
    install(main_window)

    # Tag any widget with a help topic:
    set_topic(my_widget, Topics.GLOSSARY_TERMLENS)

    # Open help for a specific topic programmatically:
    open_help(Topics.AI_BATCH)
"""

from PyQt6.QtCore import QObject, QEvent, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication


DOCS_BASE_URL = "https://help.supervertaler.com"

# Property key stored on widgets to identify their help topic
_HELP_TOPIC_PROPERTY = "_help_topic"


class Topics:
    """Help topic identifiers, each holding a path appended to ``DOCS_BASE_URL``.

    The unified help site at https://help.supervertaler.com (Astro
    Starlight on Cloudflare Pages, sources from the Supervertaler-Help
    repo) uses **folder-based URLs**: every page's URL mirrors its
    on-disk path under ``workbench/`` or ``trados/``. README.md files
    map to the folder root. Trailing slashes are canonical (Astro
    issues 301s from the slashless form, so omitting one still works
    but adds a hop).

    Workbench pages all live under ``workbench/``; Trados pages live
    under ``trados/``. There are no GitBook-style collision suffixes
    (``-1``) because the folder prefix already disambiguates.

    Authoritative URL map: ``src/generated/sidebar.js`` in the
    Supervertaler-Help repo. Regenerate that file with
    ``python _migrate/generate_sidebar.py`` after editing SUMMARY.md
    and the entries here line up 1:1 with the ``link`` fields there.
    """

    # Home of the unified help site (product chooser landing).
    HOME                = ""

    # Workbench landing page.
    WORKBENCH_HOME      = "workbench/"

    # Get Started (Workbench)
    INSTALLATION        = "workbench/get-started/installation/"
    QUICK_START         = "workbench/get-started/quick-start/"
    API_KEYS            = "workbench/get-started/api-keys/"
    FIRST_PROJECT       = "workbench/get-started/first-project/"

    # Supervertaler for Trados landing page.
    TRADOS_PLUGIN       = "trados/"

    # Editor & Translation
    TRANSLATION_GRID    = "workbench/editor/translation-grid/"
    NAVIGATION          = "workbench/editor/navigation/"
    EDITING             = "workbench/editor/editing-confirming/"
    SEGMENT_STATUSES    = "workbench/editor/segment-statuses/"
    KEYBOARD_SHORTCUTS  = "workbench/editor/keyboard-shortcuts/"
    FIND_REPLACE        = "workbench/editor/find-replace/"
    FILTERING           = "workbench/editor/filtering/"
    PAGINATION          = "workbench/editor/pagination/"

    # AI Translation
    AI_OVERVIEW         = "workbench/ai-translation/overview/"
    AI_PROVIDERS        = "workbench/ai-translation/providers/"
    AI_SINGLE_SEGMENT   = "workbench/ai-translation/single-segment/"
    AI_BATCH            = "workbench/ai-translation/batch-translation/"
    AI_PROMPTS          = "workbench/ai-translation/prompts/"
    AI_PROMPT_MANAGER   = "workbench/ai-translation/prompt-library/"
    AI_AUTOPROMPT       = "workbench/ai-translation/autoprompt/"
    AI_OLLAMA           = "workbench/ai-translation/ollama/"

    # CAT Tool Integration (folder is workbench/cat-tools/ on disk)
    CAT_OVERVIEW        = "workbench/cat-tools/overview/"
    CAT_TRADOS          = "workbench/cat-tools/trados/"
    CAT_MEMOQ           = "workbench/cat-tools/memoq/"
    CAT_PHRASE          = "workbench/cat-tools/phrase/"
    CAT_CAFETRAN        = "workbench/cat-tools/cafetran/"

    # Translation Memory
    TM_BASICS           = "workbench/translation-memory/basics/"
    TM_MANAGING         = "workbench/translation-memory/managing-tms/"
    TM_IMPORTING        = "workbench/translation-memory/importing-tmx/"
    TM_TRADOS_SDLTM     = "workbench/translation-memory/trados-sdltm/"
    TM_FUZZY            = "workbench/translation-memory/fuzzy-matching/"
    # TM_SUPERMEMORY removed in v1.10.23: Supermemory is no longer a
    # Workbench feature. The functional code was stubbed out back in
    # v1.9.105 (search_supermemory returns 0); v1.10.23 deletes the
    # corresponding help page and all stale references in the help
    # repo. (Supermemory continues to live in Supervertaler for Trados
    # as a paid Assistant feature — see the trados/ai-assistant/
    # super-memory/ docs there.)

    # Glossaries
    GLOSSARY_BASICS     = "workbench/glossaries/basics/"
    GLOSSARY_CREATING   = "workbench/glossaries/creating/"
    GLOSSARY_IMPORTING  = "workbench/glossaries/importing/"
    GLOSSARY_HIGHLIGHT  = "workbench/glossaries/highlighting/"
    GLOSSARY_TERMLENS   = "workbench/glossaries/termlens/"
    GLOSSARY_EXTRACTION = "workbench/glossaries/extraction/"

    # Import & Export (folder is workbench/import-export/ on disk)
    IMPORT_FORMATS      = "workbench/import-export/formats/"
    IMPORT_DOCX         = "workbench/import-export/docx-import/"
    IMPORT_TXT          = "workbench/import-export/txt-import/"
    IMPORT_MULTI        = "workbench/import-export/multi-file/"
    EXPORT              = "workbench/import-export/exporting/"
    BILINGUAL_TABLES    = "workbench/import-export/bilingual-tables/"

    # Superlookup
    SUPERLOOKUP         = "workbench/superlookup/overview/"
    SUPERLOOKUP_TM      = "workbench/superlookup/tm-search/"
    SUPERLOOKUP_GLOSS   = "workbench/superlookup/glossary-search/"
    SUPERLOOKUP_MT      = "workbench/superlookup/mt/"
    SUPERLOOKUP_WEB     = "workbench/superlookup/web-resources/"

    # Quality Assurance (folder is workbench/qa/ on disk)
    QA_SPELLCHECK       = "workbench/qa/spellcheck/"
    QA_TAGS             = "workbench/qa/tag-validation/"
    QA_NT               = "workbench/qa/non-translatables/"

    # Companion Tabs — file paths in the help repo are still under
    # workbench/sidekick/ for backlink stability (the section was
    # renamed in SUMMARY.md from "Sidekick" to "Companion Tabs", but
    # files weren't moved). The Astro site uses folder-based URLs,
    # so the URL stays at /workbench/sidekick/*.
    SIDEKICK            = "workbench/sidekick/overview/"
    TRADOS_AWARE_CHAT   = "workbench/sidekick/trados-aware-chat/"
    VOICE               = "workbench/sidekick/voice/"
    CLIPBOARD           = "workbench/sidekick/clipboard/"
    # QuickTrans Popup. Lives at workbench/sidekick/quicktrans-popup.md
    # in the help repo since v1.10.22 (was workbench/ai-translation/
    # before). AI_QUICKLAUNCHER alias kept for any external code that
    # imports the old name (no in-tree call-sites; defensive only).
    QUICKTRANS_POPUP    = "workbench/sidekick/quicktrans-popup/"
    AI_QUICKTRANS_POPUP = QUICKTRANS_POPUP   # v1.10.21 alias
    AI_QUICKLAUNCHER    = QUICKTRANS_POPUP   # pre-v1.10.21 alias

    # Tools (TOOL_VOICE removed – voice/dictation is the Voice tab in Sidekick)
    TOOL_PDF_RESCUE     = "workbench/tools/pdf-rescue/"
    TOOL_TMX_EDITOR     = "workbench/tools/tmx-editor/"
    TOOL_IMAGE_EXTRACT  = "workbench/tools/image-extractor/"

    # Settings
    SETTINGS_GENERAL    = "workbench/settings/general/"
    SETTINGS_VIEW       = "workbench/settings/view/"
    SETTINGS_SHORTCUTS  = "workbench/settings/shortcuts/"
    SETTINGS_THEME      = "workbench/settings/theme/"
    SETTINGS_FONTS      = "workbench/settings/fonts/"

    # Troubleshooting
    TROUBLESHOOTING     = "workbench/troubleshooting/common-issues/"


class _HelpEventFilter(QObject):
    """
    Application-level event filter that intercepts F1 key presses
    and opens the relevant documentation page.

    Walks up the widget tree from the focused widget, looking for
    a widget tagged with a help topic via set_topic(). If found,
    opens that page; otherwise opens the docs home.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_F1:
            topic = self._resolve_topic(QApplication.focusWidget())
            open_help(topic)
            return True  # consumed
        return False

    @staticmethod
    def _resolve_topic(widget):
        """Walk up the widget tree to find the nearest help topic."""
        w = widget
        while w is not None:
            topic = w.property(_HELP_TOPIC_PROPERTY)
            if topic:
                return topic
            w = w.parent()
        return None  # falls back to docs home


# Module-level singleton
_event_filter = None


def install(main_window):
    """Install the help event filter on the application. Call once at startup."""
    global _event_filter
    if _event_filter is None:
        _event_filter = _HelpEventFilter()
        QApplication.instance().installEventFilter(_event_filter)


def set_topic(widget, topic: str):
    """Tag a widget with a help topic path (relative to DOCS_BASE_URL)."""
    widget.setProperty(_HELP_TOPIC_PROPERTY, topic)


def open_help(topic: str = None):
    """Open the documentation page for the given topic."""
    if topic:
        # Defensive: any consumer that hands us a full URL (legacy
        # behaviour from when the Trados site was separate) is passed
        # through unchanged.
        if topic.startswith("http"):
            url = topic
        else:
            # lstrip only — preserve trailing slashes from the Topics
            # constants so Astro serves the page directly instead of
            # issuing a 301 redirect to the slash-terminated form.
            url = f"{DOCS_BASE_URL}/{topic.lstrip('/')}"
    else:
        url = DOCS_BASE_URL
    QDesktopServices.openUrl(QUrl(url))
