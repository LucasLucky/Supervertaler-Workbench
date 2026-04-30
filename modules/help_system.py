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


DOCS_BASE_URL = "https://supervertaler.gitbook.io"

# Property key stored on widgets to identify their help topic
_HELP_TOPIC_PROPERTY = "_help_topic"


class Topics:
    """Help topic identifiers mapping to GitBook page paths.

    All Workbench pages live under ``workbench/`` on the unified
    Supervertaler help site (Trados pages live alongside under
    ``trados/``). The site previously used a separate domain for the
    Workbench docs; that's been retired in favour of one home for both
    products.
    """

    # Home
    HOME                = "workbench/"

    # Get Started
    INSTALLATION        = "workbench/get-started/installation"
    QUICK_START         = "workbench/get-started/quick-start"
    API_KEYS            = "workbench/get-started/api-keys"
    FIRST_PROJECT       = "workbench/get-started/first-project"

    # Supervertaler for Trados (cross-reference — opens the Trados section
    # of the same GitBook site).
    TRADOS_PLUGIN       = "trados/"

    # Editor & Translation
    TRANSLATION_GRID    = "workbench/editor/translation-grid"
    NAVIGATION          = "workbench/editor/navigation"
    EDITING             = "workbench/editor/editing-confirming"
    SEGMENT_STATUSES    = "workbench/editor/segment-statuses"
    KEYBOARD_SHORTCUTS  = "workbench/editor/keyboard-shortcuts"
    FIND_REPLACE        = "workbench/editor/find-replace"
    FILTERING           = "workbench/editor/filtering"
    PAGINATION          = "workbench/editor/pagination"

    # AI Translation
    AI_OVERVIEW         = "workbench/ai-translation/overview"
    AI_PROVIDERS        = "workbench/ai-translation/providers"
    AI_SINGLE_SEGMENT   = "workbench/ai-translation/single-segment"
    AI_BATCH            = "workbench/ai-translation/batch-translation"
    AI_PROMPTS          = "workbench/ai-translation/prompts"
    AI_PROMPT_MANAGER   = "workbench/ai-translation/prompt-library"
    AI_QUICKLAUNCHER    = "workbench/ai-translation/quicklauncher"
    AI_OLLAMA           = "workbench/ai-translation/ollama"

    # CAT Tool Integration
    CAT_OVERVIEW        = "workbench/cat-tools/overview"
    CAT_TRADOS          = "workbench/cat-tools/trados"
    CAT_MEMOQ           = "workbench/cat-tools/memoq"
    CAT_PHRASE          = "workbench/cat-tools/phrase"
    CAT_CAFETRAN        = "workbench/cat-tools/cafetran"

    # Translation Memory
    TM_BASICS           = "workbench/translation-memory/basics"
    TM_MANAGING         = "workbench/translation-memory/managing-tms"
    TM_IMPORTING        = "workbench/translation-memory/importing-tmx"
    TM_FUZZY            = "workbench/translation-memory/fuzzy-matching"
    TM_SUPERMEMORY      = "workbench/translation-memory/supermemory"

    # Glossaries
    GLOSSARY_BASICS     = "workbench/glossaries/basics"
    GLOSSARY_CREATING   = "workbench/glossaries/creating"
    GLOSSARY_IMPORTING  = "workbench/glossaries/importing"
    GLOSSARY_HIGHLIGHT  = "workbench/glossaries/highlighting"
    GLOSSARY_TERMLENS   = "workbench/glossaries/termlens"
    GLOSSARY_EXTRACTION = "workbench/glossaries/extraction"

    # Import & Export
    IMPORT_FORMATS      = "workbench/import-export/formats"
    IMPORT_DOCX         = "workbench/import-export/docx-import"
    IMPORT_TXT          = "workbench/import-export/txt-import"
    IMPORT_MULTI        = "workbench/import-export/multi-file"
    EXPORT              = "workbench/import-export/exporting"
    BILINGUAL_TABLES    = "workbench/import-export/bilingual-tables"

    # Superlookup
    SUPERLOOKUP         = "workbench/superlookup/overview"
    SUPERLOOKUP_TM      = "workbench/superlookup/tm-search"
    SUPERLOOKUP_GLOSS   = "workbench/superlookup/glossary-search"
    SUPERLOOKUP_MT      = "workbench/superlookup/mt"
    SUPERLOOKUP_WEB     = "workbench/superlookup/web-resources"

    # Quality Assurance
    QA_SPELLCHECK       = "workbench/qa/spellcheck"
    QA_TAGS             = "workbench/qa/tag-validation"
    QA_NT               = "workbench/qa/non-translatables"

    # Tools (TOOL_VOICE removed — voice/dictation is now AutoFingers in Sidekick)
    TOOL_PDF_RESCUE     = "workbench/tools/pdf-rescue"
    TOOL_TMX_EDITOR     = "workbench/tools/tmx-editor"
    TOOL_IMAGE_EXTRACT  = "workbench/tools/image-extractor"

    # Settings
    SETTINGS_GENERAL    = "workbench/settings/general"
    SETTINGS_VIEW       = "workbench/settings/view"
    SETTINGS_SHORTCUTS  = "workbench/settings/shortcuts"
    SETTINGS_THEME      = "workbench/settings/theme"
    SETTINGS_FONTS      = "workbench/settings/fonts"

    # Troubleshooting
    TROUBLESHOOTING     = "workbench/troubleshooting/common-issues"


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
