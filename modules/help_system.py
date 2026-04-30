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
    """Help topic identifiers mapping to help.supervertaler.com page paths."""

    # Home
    HOME                = ""

    # Get Started
    INSTALLATION        = "get-started/installation"
    QUICK_START         = "get-started/quick-start"
    API_KEYS            = "get-started/api-keys"
    FIRST_PROJECT       = "get-started/first-project"

    # Supervertaler for Trados (cross-reference — opens Trados help site)
    TRADOS_PLUGIN       = "https://supervertaler.gitbook.io/trados"

    # Editor & Translation
    TRANSLATION_GRID    = "editor/translation-grid"
    NAVIGATION          = "editor/navigation"
    EDITING             = "editor/editing-confirming"
    SEGMENT_STATUSES    = "editor/segment-statuses"
    KEYBOARD_SHORTCUTS  = "editor/keyboard-shortcuts"
    FIND_REPLACE        = "editor/find-replace"
    FILTERING           = "editor/filtering"
    PAGINATION          = "editor/pagination"

    # AI Translation
    AI_OVERVIEW         = "ai-translation/overview"
    AI_PROVIDERS        = "ai-translation/providers"
    AI_SINGLE_SEGMENT   = "ai-translation/single-segment"
    AI_BATCH            = "ai-translation/batch-translation"
    AI_PROMPTS          = "ai-translation/prompts"
    AI_PROMPT_MANAGER   = "ai-translation/prompt-library"
    AI_QUICKLAUNCHER    = "ai-translation/quicklauncher"
    AI_OLLAMA           = "ai-translation/ollama"

    # CAT Tool Integration
    CAT_OVERVIEW        = "cat-tools/overview"
    CAT_TRADOS          = "cat-tools/trados"
    CAT_MEMOQ           = "cat-tools/memoq"
    CAT_PHRASE          = "cat-tools/phrase"
    CAT_CAFETRAN        = "cat-tools/cafetran"

    # Translation Memory
    TM_BASICS           = "translation-memory/basics"
    TM_MANAGING         = "translation-memory/managing-tms"
    TM_IMPORTING        = "translation-memory/importing-tmx"
    TM_FUZZY            = "translation-memory/fuzzy-matching"
    TM_SUPERMEMORY      = "translation-memory/supermemory"

    # Glossaries
    GLOSSARY_BASICS     = "glossaries/basics"
    GLOSSARY_CREATING   = "glossaries/creating"
    GLOSSARY_IMPORTING  = "glossaries/importing"
    GLOSSARY_HIGHLIGHT  = "glossaries/highlighting"
    GLOSSARY_TERMLENS   = "glossaries/termlens"
    GLOSSARY_EXTRACTION = "glossaries/extraction"

    # Import & Export
    IMPORT_FORMATS      = "import-export/formats"
    IMPORT_DOCX         = "import-export/docx-import"
    IMPORT_TXT          = "import-export/txt-import"
    IMPORT_MULTI        = "import-export/multi-file"
    EXPORT              = "import-export/exporting"
    BILINGUAL_TABLES    = "import-export/bilingual-tables"

    # Superlookup
    SUPERLOOKUP         = "superlookup/overview"
    SUPERLOOKUP_TM      = "superlookup/tm-search"
    SUPERLOOKUP_GLOSS   = "superlookup/glossary-search"
    SUPERLOOKUP_MT      = "superlookup/mt"
    SUPERLOOKUP_WEB     = "superlookup/web-resources"

    # Quality Assurance
    QA_SPELLCHECK       = "qa/spellcheck"
    QA_TAGS             = "qa/tag-validation"
    QA_NT               = "qa/non-translatables"

    # Tools
    TOOL_PDF_RESCUE     = "tools/pdf-rescue"
    TOOL_TMX_EDITOR     = "tools/tmx-editor"
    TOOL_VOICE          = "tools/voice-commands"
    TOOL_IMAGE_EXTRACT  = "tools/image-extractor"

    # Settings
    SETTINGS_GENERAL    = "settings/general"
    SETTINGS_VIEW       = "settings/view"
    SETTINGS_SHORTCUTS  = "settings/shortcuts"
    SETTINGS_THEME      = "settings/theme"
    SETTINGS_FONTS      = "settings/fonts"

    # Troubleshooting
    TROUBLESHOOTING     = "troubleshooting/common-issues"


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
        # TRADOS_PLUGIN is a full URL to the separate Trados help site
        if topic.startswith("http"):
            url = topic
        else:
            url = f"{DOCS_BASE_URL}/{topic.strip('/')}"
    else:
        url = DOCS_BASE_URL
    QDesktopServices.openUrl(QUrl(url))
