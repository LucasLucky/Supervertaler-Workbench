"""
QuickTrans - Instant translation popup (GT4T-style)

A popup window that shows translations from all enabled MT engines and LLMs.
Part of the Supervertaler tool suite. Triggered by Ctrl+M (in-app) or Ctrl+Alt+Q (global).

Features:
- Shows source text at the top
- Displays numbered list of translations from MT engines and LLMs
- Press number key (1-9) or click to insert translation
- Escape to dismiss
- Translations fetched in parallel for speed
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import QKeySequence, QShortcut, QCursor, QFont
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


# Provider chip colours, keyed by internal provider code. Shared by the popup
# rows (MTSuggestionItem) and the docked panel (QuickTransPanel) so the colour
# coding stays consistent everywhere.
PROVIDER_COLORS = {
    "GT":  "#4285F4",   # Google blue
    "DL":  "#042B48",   # DeepL dark blue
    "MS":  "#00A4EF",   # Microsoft blue
    "AT":  "#FF9900",   # Amazon orange
    "MMT": "#6B4EE6",   # ModernMT purple
    "MM":  "#2ECC71",   # MyMemory green
    "CL":  "#D97706",   # Claude amber
    "GPT": "#10A37F",   # OpenAI green
    "GEM": "#4285F4",   # Gemini blue
    "OLL": "#555555",   # Ollama dark gray
    "CUS": "#9C27B0",   # Custom purple
}

# Shared style for the small icon-only header buttons in the docked panel.
_PANEL_ICON_BTN_STYLE = """
    QPushButton { border: none; background: transparent; font-size: 13px; }
    QPushButton:hover { background-color: #e0e0e0; border-radius: 4px; }
    QPushButton:focus { outline: none; }
"""


# Provider codes that are AI/LLM rather than machine-translation engines, used
# to group QuickTrans results. Everything not listed here (GT, DL, MS, AT, MMT,
# MM, and CMT custom-MT) is treated as a machine-translation engine.
_AI_PROVIDER_CODES = {"CL", "GPT", "GEM", "OLL", "CUS"}


def _is_ai_code(code: str) -> bool:
    return code in _AI_PROVIDER_CODES


@dataclass
class MTSuggestion:
    """A single MT suggestion from a provider"""
    provider_name: str  # Full name: "Google Translate", "DeepL", etc.
    provider_code: str  # Short code: "GT", "DL", etc.
    translation: str
    is_error: bool = False


class MTFetchWorker(QThread):
    """Background worker to fetch MT translations in parallel"""

    result_ready = pyqtSignal(str, str, str, bool)  # provider_name, provider_code, translation, is_error
    all_complete = pyqtSignal()

    def __init__(self, source_text: str, source_lang: str, target_lang: str,
                 providers: List[Tuple[str, str, callable]], parent=None):
        super().__init__(parent)
        self.source_text = source_text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.providers = providers  # List of (name, code, call_function)

    def run(self):
        """Fetch translations from all providers in parallel"""
        def fetch_single(provider_info):
            name, code, call_func = provider_info
            try:
                result = call_func(self.source_text, self.source_lang, self.target_lang)
                is_error = result.startswith('[') and 'error' in result.lower()
                return (name, code, result, is_error)
            except Exception as e:
                return (name, code, f"[Error: {str(e)}]", True)

        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fetch_single, p): p for p in self.providers}
            for future in as_completed(futures):
                try:
                    name, code, translation, is_error = future.result()
                    self.result_ready.emit(name, code, translation, is_error)
                except Exception as e:
                    provider = futures[future]
                    self.result_ready.emit(provider[0], provider[1], f"[Error: {str(e)}]", True)

        self.all_complete.emit()


class MTSuggestionItem(QFrame):
    """A single MT suggestion row in the popup"""

    clicked = pyqtSignal(str)  # Emits the translation text when clicked

    def __init__(self, number: int, suggestion: MTSuggestion, parent=None):
        super().__init__(parent)
        self.suggestion = suggestion
        self.number = number
        self.is_selected = False

        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Number badge (stored so the pick-number can be updated when results
        # are regrouped into MT / AI sections after all fetches complete).
        num_label = QLabel(str(number))
        self.num_label = num_label
        num_label.setFixedSize(24, 24)
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setStyleSheet("""
            QLabel {
                background-color: #ff9800;
                color: #333;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
            }
        """)
        layout.addWidget(num_label)

        # Provider name badge – full name, sized to content
        provider_label = QLabel(suggestion.provider_name)
        provider_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Color-code by provider code (internal key, not displayed)
        bg_color = PROVIDER_COLORS.get(suggestion.provider_code, "#666")
        provider_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                font-weight: bold;
                font-size: 9px;
                border-radius: 3px;
                padding: 2px 8px;
            }}
        """)
        layout.addWidget(provider_label)

        # Translation text
        text_label = QLabel(suggestion.translation)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        if suggestion.is_error:
            text_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        else:
            text_label.setStyleSheet("color: #333; font-size: 11px;")

        layout.addWidget(text_label, 1)

        self._update_style()

    def _update_style(self):
        """Update visual style based on selection state"""
        if self.is_selected:
            self.setStyleSheet("""
                MTSuggestionItem {
                    background-color: #e3f2fd;
                    border: 1px solid #2196F3;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                MTSuggestionItem {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                }
                MTSuggestionItem:hover {
                    background-color: #f5f5f5;
                    border: 1px solid #bdbdbd;
                }
            """)

    def select(self):
        """Select this item"""
        self.is_selected = True
        self._update_style()

    def deselect(self):
        """Deselect this item"""
        self.is_selected = False
        self._update_style()

    def set_number(self, number: int):
        """Update the displayed pick-number (used when results are regrouped)."""
        self.number = number
        if getattr(self, 'num_label', None) is not None:
            self.num_label.setText(str(number))

    def mousePressEvent(self, event):
        """Handle click to select this translation"""
        if event.button() == Qt.MouseButton.LeftButton and not self.suggestion.is_error:
            self.clicked.emit(self.suggestion.translation)
        super().mousePressEvent(event)


class QuickTransProviderMixin:
    """Shared provider enumeration + LLM calling logic.

    Used by both the QuickTrans popup (``MTQuickPopup``) and the docked
    under-grid panel (``QuickTransPanel``). Both set ``self.parent_app`` to the
    Workbench main window, which supplies the API keys, enabled-provider
    states, MT call methods, and LLM client wiring.
    """

    def _load_mt_quick_settings(self) -> Dict[str, Any]:
        """Load MT Quick Lookup specific settings"""
        if hasattr(self.parent_app, 'load_general_settings'):
            settings = self.parent_app.load_general_settings()
            return settings.get('mt_quick_lookup', {})
        return {}

    def _get_enabled_providers(self, include_mt: bool = True,
                               include_llms: bool = True) -> List[Tuple[str, str, callable]]:
        """Get enabled providers with their call functions.

        ``include_mt`` / ``include_llms`` let callers fetch only the cheap MT
        engines or only the (paid) LLMs – the docked panel uses this to
        auto-fetch MT while keeping LLMs on-demand.
        """
        providers = []

        if not self.parent_app:
            return providers

        api_keys = {}
        enabled_providers = {}

        if hasattr(self.parent_app, 'load_api_keys'):
            api_keys = self.parent_app.load_api_keys()
        if hasattr(self.parent_app, 'load_provider_enabled_states'):
            enabled_providers = self.parent_app.load_provider_enabled_states()

        # Load MT Quick Lookup specific settings
        mt_quick_settings = self._load_mt_quick_settings()

        if include_mt:
            # Define MT providers: (display_name, code, enabled_key, api_key_name, call_method_name)
            mt_provider_defs = [
                ("Google Translate", "GT", "mt_google_translate", "google_translate", "call_google_translate"),
                ("DeepL", "DL", "mt_deepl", "deepl", "call_deepl"),
                ("Microsoft Translator", "MS", "mt_microsoft", "microsoft_translate", "call_microsoft_translate"),
                ("Amazon Translate", "AT", "mt_amazon", "amazon_translate", "call_amazon_translate"),
                ("ModernMT", "MMT", "mt_modernmt", "modernmt", "call_modernmt"),
                ("MyMemory", "MM", "mt_mymemory", None, "call_mymemory"),  # MyMemory works without key
            ]

            for name, code, enabled_key, api_key_name, method_name in mt_provider_defs:
                # Check if provider is enabled in MT Quick Lookup settings (default: use MT Settings state)
                quick_lookup_key = f"mtql_{code.lower()}"
                if not mt_quick_settings.get(quick_lookup_key, enabled_providers.get(enabled_key, True)):
                    continue

                # Check if API key is available (MyMemory doesn't require one)
                if api_key_name and not api_keys.get(api_key_name):
                    continue

                # Get the call method
                if hasattr(self.parent_app, method_name):
                    call_method = getattr(self.parent_app, method_name)

                    # Create a wrapper that handles the API key
                    api_key = api_keys.get(api_key_name) if api_key_name else None

                    def make_caller(m, k):
                        return lambda text, src, tgt: m(text, src, tgt, k)

                    providers.append((name, code, make_caller(call_method, api_key)))

            # Custom MT endpoint(s): when the master 'mtql_custom_mt' toggle is on,
            # each configured profile (with an endpoint) becomes its own MT chip.
            # Independent of the AI custom endpoint, so MT and AI can point at
            # different OpenAI-compatible services at the same time.
            if (mt_quick_settings.get('mtql_custom_mt', False)
                    and hasattr(self.parent_app, 'call_custom_mt')):
                llm_settings = (self.parent_app.load_llm_settings()
                                if hasattr(self.parent_app, 'load_llm_settings') else {})
                for profile in (llm_settings.get('custom_mt_profiles') or []):
                    if not profile.get('enabled', True):
                        continue  # profile hidden from QuickTrans by the user
                    if not (profile.get('endpoint') or '').strip():
                        continue
                    p_name = profile.get('name') or 'Custom MT'

                    def make_custom_mt_caller(prof):
                        return lambda text, src, tgt: self.parent_app.call_custom_mt(text, src, tgt, prof)

                    providers.append((p_name, "CMT", make_custom_mt_caller(profile)))

        # Add LLM providers if enabled
        if include_llms:
            self._add_llm_providers(providers, api_keys, mt_quick_settings)

        return providers

    def _add_llm_providers(self, providers: List, api_keys: Dict, mt_quick_settings: Dict):
        """Add LLM providers (Claude, OpenAI, Gemini) to the providers list"""
        # LLM provider definitions: (name, code, api_key_name, settings_key)
        llm_defs = [
            ("Claude", "CL", "claude", "mtql_claude"),
            ("OpenAI", "GPT", "openai", "mtql_openai"),
            ("Gemini", "GEM", "gemini", "mtql_gemini"),
            ("Ollama", "OLL", "ollama", "mtql_ollama"),
            ("Custom", "CUS", "custom_openai", "mtql_custom_openai"),
        ]

        for name, code, api_key_name, settings_key in llm_defs:
            # Check if LLM is enabled in MT Quick Lookup settings (default: disabled)
            if not mt_quick_settings.get(settings_key, False):
                continue

            # Check if API key is available
            if api_key_name == 'gemini':
                has_key = bool(api_keys.get('gemini') or api_keys.get('google'))
            elif api_key_name in ('ollama', 'custom_openai'):
                has_key = True  # No API key needed
            else:
                has_key = bool(api_keys.get(api_key_name))

            if not has_key:
                continue

            # Get model from settings or use default
            model_key = f"{settings_key}_model"
            model = mt_quick_settings.get(model_key, None)

            # Create LLM translation caller
            def make_llm_caller(provider_name, provider_key, provider_model):
                def call_llm(text, src_lang, tgt_lang):
                    return self._call_llm_translation(provider_key, text, src_lang, tgt_lang, provider_model)
                return call_llm

            providers.append((name, code, make_llm_caller(name, api_key_name, model)))

    def _call_llm_translation(self, provider: str, text: str, source_lang: str, target_lang: str, model: str = None) -> str:
        """Call LLM for translation"""
        try:
            from modules.llm_clients import LLMClient, load_api_keys

            if hasattr(self, 'parent_app') and self.parent_app and hasattr(self.parent_app, 'load_api_keys'):
                api_keys = self.parent_app.load_api_keys()
            else:
                api_keys = load_api_keys()

            if provider == 'gemini':
                api_key = api_keys.get('gemini') or api_keys.get('google')
            else:
                api_key = api_keys.get(provider)

            if not api_key and provider not in ('ollama', 'custom_openai'):
                return f"[Error: No API key for {provider}]"

            # Reuse main app client wiring when available (supports custom profiles/base_url)
            if hasattr(self, 'parent_app') and self.parent_app and hasattr(self.parent_app, 'create_llm_client'):
                llm_settings = self.parent_app.load_llm_settings() if hasattr(self.parent_app, 'load_llm_settings') else None
                resolved_model = model
                if not resolved_model and llm_settings:
                    resolved_model = llm_settings.get(f"{provider}_model")
                client = self.parent_app.create_llm_client(provider, resolved_model, api_keys, settings=llm_settings)
            else:
                base_url = None
                if provider == 'custom_openai':
                    api_key = api_key or 'not-needed'
                client = LLMClient(
                    api_key=api_key,
                    provider=provider,
                    model=model,
                    base_url=base_url
                )

            # Use a strict prompt that forces translation-only output
            prompt = (
                f"Translate the following text from {source_lang} to {target_lang}.\n"
                f"Output ONLY the translation, nothing else. "
                f"No explanations, no alternatives, no notes, no quotation marks.\n\n"
                f"{text}"
            )
            system_prompt = (
                "You are a translation engine. Output only the translated text. "
                "Never add explanations, alternatives, notes, or commentary. "
                "Never wrap the output in quotes. "
                "If the text is already in the target language, output it unchanged."
            )

            result = client.translate(
                text="",
                source_lang=source_lang,
                target_lang=target_lang,
                custom_prompt=prompt,
                system_prompt=system_prompt,
            )

            # Clean up result - remove quotes if present
            if result:
                result = result.strip()
                if (result.startswith('"') and result.endswith('"')) or (result.startswith("'") and result.endswith("'")):
                    result = result[1:-1]
                # Remove any "Translation:" or similar prefixes
                for prefix in ['Translation:', 'translation:', 'Result:', 'Output:']:
                    if result.startswith(prefix):
                        result = result[len(prefix):].strip()

            return result or "[No translation returned]"

        except Exception as e:
            return f"[Error: {str(e)}]"


class MTQuickPopup(QuickTransProviderMixin, QDialog):
    """
    GT4T-style popup showing MT suggestions from all enabled providers

    Usage:
        popup = MTQuickPopup(parent_app, source_text, source_lang, target_lang)
        popup.translation_selected.connect(on_translation_selected)
        popup.show()
    """

    translation_selected = pyqtSignal(str)  # Emitted when user selects a translation

    def __init__(self, parent_app, source_text: str, source_lang: str = None,
                 target_lang: str = None, parent=None, external_mode: bool = False):
        super().__init__(parent)
        self.parent_app = parent_app
        self.source_text = source_text
        self.source_lang = source_lang or getattr(parent_app, 'source_language', 'en')
        self.target_lang = target_lang or getattr(parent_app, 'target_language', 'nl')
        self._external_mode = external_mode  # True when invoked from global hotkey

        self.suggestions: List[MTSuggestion] = []
        self.suggestion_items: List[MTSuggestionItem] = []
        self.selected_index = -1
        self.worker = None

        self.setup_ui()
        self.setup_shortcuts()
        self.start_fetching()

    def setup_ui(self):
        """Setup the popup UI"""
        self.setWindowTitle("⚡ Supervertaler QuickTrans")
        if self._external_mode:
            # External mode (global hotkey): use Tool window type so the
            # Supervertaler taskbar icon doesn't flash when the popup appears.
            # Tool windows don't get their own taskbar entry and don't activate
            # the parent application.
            self.setWindowFlags(
                Qt.WindowType.Tool |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            # In-app mode: standard dialog with title bar for resize/move support
            self.setWindowFlags(
                Qt.WindowType.Dialog |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.WindowStaysOnTopHint
            )

        # Set size - allow resizing
        self.setMinimumWidth(450)
        self.setMinimumHeight(200)

        # Restore saved size and position or use defaults
        settings = QSettings("Supervertaler", "MTQuickPopup")
        saved_width = settings.value("width", 650, type=int)
        saved_height = settings.value("height", 400, type=int)
        self.resize(saved_width, saved_height)

        # Check if we have a saved position
        self._has_saved_position = settings.contains("x") and settings.contains("y")
        if self._has_saved_position:
            saved_x = settings.value("x", 0, type=int)
            saved_y = settings.value("y", 0, type=int)
            self.move(saved_x, saved_y)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(0)

        # Container with styling
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(8)

        # Header with title and settings button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)

        title_label = QLabel("⚡ Supervertaler QuickTrans")
        title_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #333;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Shared style for icon-only header buttons. Reused for both
        # the SuperLookup hand-off button and the settings cog so they
        # visually line up.
        _icon_btn_style = """
            QPushButton {
                border: none;
                background: transparent;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 4px;
            }
            QPushButton:focus {
                outline: none;
            }
        """

        # "Run in SuperLookup" hand-off button (v1.10.12, label
        # extended in v1.10.13). When a user runs QuickTrans on a
        # phrase and then thinks "I'd actually like to look this up
        # in my TMs / termbases / web resources too", this button
        # takes them there in one click: closes the popup and opens
        # Workbench's SuperLookup top tab with the same query
        # pre-filled and the search auto-fired. Same plumbing as
        # Ctrl+Alt+L. Icon-plus-label rather than icon-only because
        # the bare 🔍 next to ⚙ wasn't self-explanatory enough –
        # users couldn't tell at a glance what it did.
        superlookup_btn = QPushButton("🔍 Run in SuperLookup")
        superlookup_btn.setFixedHeight(24)
        superlookup_btn.setToolTip("Run this query in SuperLookup")
        superlookup_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 11px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 4px;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        superlookup_btn.clicked.connect(self._send_to_superlookup)
        header_layout.addWidget(superlookup_btn)

        # Settings button
        settings_btn = QPushButton("⚙️")
        settings_btn.setFixedSize(24, 24)
        settings_btn.setToolTip("Configure QuickTrans providers")
        settings_btn.setStyleSheet(_icon_btn_style)
        settings_btn.clicked.connect(self._open_settings)
        header_layout.addWidget(settings_btn)

        container_layout.addLayout(header_layout)

        # Source text display
        source_frame = QFrame()
        source_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(8, 6, 8, 6)

        source_header = QLabel("Source:")
        source_header.setStyleSheet("font-size: 9px; color: #666; font-weight: bold;")
        source_layout.addWidget(source_header)

        source_text_label = QLabel(self.source_text)
        source_text_label.setWordWrap(True)
        source_text_label.setStyleSheet("font-size: 11px; color: #333;")
        source_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_layout.addWidget(source_text_label)

        container_layout.addWidget(source_frame)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #e0e0e0;")
        sep.setFixedHeight(1)
        container_layout.addWidget(sep)

        # Suggestions scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.suggestions_container = QWidget()
        self.suggestions_layout = QVBoxLayout(self.suggestions_container)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestions_layout.setSpacing(4)

        # Loading indicator
        self.loading_label = QLabel("⏳ Fetching translations...")
        self.loading_label.setStyleSheet("color: #666; font-size: 11px; padding: 20px;")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.suggestions_layout.addWidget(self.loading_label)

        self.suggestions_layout.addStretch()

        scroll.setWidget(self.suggestions_container)
        container_layout.addWidget(scroll, 1)

        # Footer with hint
        hint = QLabel("Press 1-9 to insert • ↑↓ to navigate • Enter to insert selected • Esc to close")
        hint.setStyleSheet("font-size: 9px; color: #999; padding-top: 4px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(hint)

        main_layout.addWidget(container)

        # Position popup near cursor
        self._position_near_cursor()

    def _position_near_cursor(self):
        """Position the popup near the cursor (only if no saved position)"""
        # Skip if we restored a saved position
        if getattr(self, '_has_saved_position', False):
            # Verify saved position is still on a valid screen
            screen = QApplication.screenAt(self.pos())
            if screen:
                return  # Saved position is valid, use it

        # Position near cursor
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if screen:
            screen_geo = screen.availableGeometry()

            # Try to position popup below and to the right of cursor
            x = cursor_pos.x() + 10
            y = cursor_pos.y() + 10

            # Ensure popup stays on screen
            if x + self.width() > screen_geo.right():
                x = cursor_pos.x() - self.width() - 10
            if y + self.height() > screen_geo.bottom():
                y = cursor_pos.y() - self.height() - 10

            # Clamp to screen bounds
            x = max(screen_geo.left(), min(x, screen_geo.right() - self.width()))
            y = max(screen_geo.top(), min(y, screen_geo.bottom() - self.height()))

            self.move(x, y)

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Number keys 1-9 for quick selection
        for i in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(i)), self)
            shortcut.activated.connect(lambda idx=i: self._select_by_number(idx))

        # Navigation
        QShortcut(QKeySequence(Qt.Key.Key_Up), self).activated.connect(self._navigate_up)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self).activated.connect(self._navigate_down)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self._insert_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self._insert_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.close)

    def _make_section_header(self, text: str) -> QLabel:
        """A lightweight group-header label ('Machine translation' / 'AI / LLM')."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "QLabel { color: #888; font-size: 8pt; font-weight: bold; "
            "border: none; padding: 6px 2px 1px 2px; }"
        )
        return lbl

    def start_fetching(self):
        """Start fetching translations from all enabled providers"""
        providers = self._get_enabled_providers()

        if not providers:
            self.loading_label.setText("⚠️ No MT providers configured. Check Settings → MT Settings.")
            return

        # Pre-create group headers: Machine translation (top), AI / LLM (below).
        # Results stream in arrival order but are routed into the right section in
        # _on_result_ready; _on_all_complete then renumbers top-to-bottom.
        self._mt_header = None
        self._ai_header = None
        if any(not _is_ai_code(c) for _, c, _ in providers):
            self._mt_header = self._make_section_header("⚡  Machine translation")
            self.suggestions_layout.insertWidget(self.suggestions_layout.count() - 1, self._mt_header)
        if any(_is_ai_code(c) for _, c, _ in providers):
            self._ai_header = self._make_section_header("\U0001F916  AI / LLM")
            self.suggestions_layout.insertWidget(self.suggestions_layout.count() - 1, self._ai_header)

        self.worker = MTFetchWorker(
            self.source_text,
            self.source_lang,
            self.target_lang,
            providers,
            self
        )
        self.worker.result_ready.connect(self._on_result_ready)
        self.worker.all_complete.connect(self._on_all_complete)
        self.worker.start()

    def _send_to_superlookup(self):
        """Close the popup and open Workbench's SuperLookup tab with
        the current QuickTrans query pre-filled.

        Wired to the 🔍 button in the popup header. Same plumbing as
        the Ctrl+Alt+L global hotkey – `open_workbench_to_superlookup`
        on the main window does the lazy-tab ensure, foreground
        hammer chain, text seeding, and deferred search-button click.

        Deferred via QTimer.singleShot(0) for the same reason as
        `_open_settings`: the popup's close() events need a Qt
        event-loop turn to fully unwind before the foreground
        transition starts, otherwise the hammer chain can race
        against still-queued popup destruction events and leave
        Workbench painted behind the source app.
        """
        query = (self.source_text or "").strip()
        if not query:
            return
        if not (self.parent_app and hasattr(self.parent_app, 'open_workbench_to_superlookup')):
            return
        self.close()
        try:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(
                0,
                lambda: self.parent_app.open_workbench_to_superlookup(query),
            )
        except Exception:
            # Synchronous fallback – the v1.10.9 hammer chain inside
            # open_workbench_to_superlookup is robust enough to win
            # the foreground race most of the time without the defer.
            self.parent_app.open_workbench_to_superlookup(query)

    def _open_settings(self):
        """Open Workbench Settings → ⚡ QuickTrans.

        v1.10.11: defer the parent-app call via QTimer.singleShot(0)
        so the popup's close() has a Qt event-loop turn to fully
        unwind before _bring_workbench_forward() fires. Without the
        defer, the foreground-grab hammer chain races against the
        popup-destruction events still queued in our own process,
        which can leave Workbench painted behind whichever app
        actually owns the OS-level foreground (typically Trados,
        since QuickTrans is most often summoned from there).
        """
        if self.parent_app and hasattr(self.parent_app, 'open_mt_quick_lookup_settings'):
            self.close()  # Close popup first (sync, but events queue)
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(
                    0, self.parent_app.open_mt_quick_lookup_settings
                )
            except Exception:
                # If QTimer import fails (extremely unlikely), fall
                # back to the synchronous path – the v1.10.11 hammer
                # chain inside open_mt_quick_lookup_settings is
                # robust enough to win the foreground race most of
                # the time even without the defer.
                self.parent_app.open_mt_quick_lookup_settings()

    def _on_result_ready(self, provider_name: str, provider_code: str, translation: str, is_error: bool):
        """Handle a single MT result"""
        # Hide loading label on first result
        if self.loading_label.isVisible():
            self.loading_label.hide()

        # Create suggestion
        suggestion = MTSuggestion(
            provider_name=provider_name,
            provider_code=provider_code,
            translation=translation,
            is_error=is_error
        )
        self.suggestions.append(suggestion)

        # Create and add item widget
        item = MTSuggestionItem(len(self.suggestions), suggestion)
        item.clicked.connect(self._on_item_clicked)
        self.suggestion_items.append(item)

        # Route into the right group: MT rows go above the AI / LLM header so MT
        # stays grouped at the top; AI rows (and the no-grouping case) go before
        # the trailing stretch.
        ai_header = getattr(self, '_ai_header', None)
        if (not _is_ai_code(provider_code)
                and ai_header is not None
                and self.suggestions_layout.indexOf(ai_header) >= 0):
            idx = self.suggestions_layout.indexOf(ai_header)
        else:
            idx = self.suggestions_layout.count() - 1
        self.suggestions_layout.insertWidget(idx, item)

        # Auto-select first non-error result (corrected after regrouping).
        if self.selected_index == -1 and not is_error:
            self._select_index(len(self.suggestion_items) - 1)

    def _on_all_complete(self):
        """Handle completion of all MT fetches"""
        if not self.suggestions:
            self.loading_label.setText("⚠️ No translations available.")
            self.loading_label.show()
            return
        # Results streamed in arrival order; renumber them top-to-bottom so the
        # pick-numbers (1-9) match the grouped MT-then-AI visual order.
        self._renumber_grouped()
        # Don't call adjustSize() - it shrinks the window and loses user's preferred size

    def _renumber_grouped(self):
        """Walk the (already grouped) layout top to bottom, assign sequential
        pick-numbers, and rebuild the parallel lists so number-key selection and
        index-based selection stay correct."""
        new_suggestions = []
        new_items = []
        n = 0
        for i in range(self.suggestions_layout.count()):
            w = self.suggestions_layout.itemAt(i).widget()
            if isinstance(w, MTSuggestionItem):
                n += 1
                w.set_number(n)
                w.deselect()
                new_items.append(w)
                new_suggestions.append(w.suggestion)
        self.suggestions = new_suggestions
        self.suggestion_items = new_items
        # Re-select the first non-error row in the new order.
        self.selected_index = -1
        for idx, it in enumerate(new_items):
            if not it.suggestion.is_error:
                self._select_index(idx)
                break

    def _on_item_clicked(self, translation: str):
        """Handle click on a suggestion item"""
        self.translation_selected.emit(translation)
        self.close()

    def _select_by_number(self, number: int):
        """Select suggestion by number (1-based)"""
        idx = number - 1
        if 0 <= idx < len(self.suggestion_items):
            suggestion = self.suggestions[idx]
            if not suggestion.is_error:
                self.translation_selected.emit(suggestion.translation)
                self.close()

    def _select_index(self, index: int):
        """Select suggestion by index"""
        # Deselect previous
        if 0 <= self.selected_index < len(self.suggestion_items):
            self.suggestion_items[self.selected_index].deselect()

        # Select new (skip errors)
        if 0 <= index < len(self.suggestion_items):
            self.selected_index = index
            self.suggestion_items[index].select()
            # Ensure visible
            self.suggestion_items[index].setFocus()

    def _navigate_up(self):
        """Navigate to previous suggestion"""
        if not self.suggestion_items:
            return

        new_idx = self.selected_index - 1
        while new_idx >= 0:
            if not self.suggestions[new_idx].is_error:
                self._select_index(new_idx)
                return
            new_idx -= 1

    def _navigate_down(self):
        """Navigate to next suggestion"""
        if not self.suggestion_items:
            return

        new_idx = self.selected_index + 1
        while new_idx < len(self.suggestions):
            if not self.suggestions[new_idx].is_error:
                self._select_index(new_idx)
                return
            new_idx += 1

    def _insert_selected(self):
        """Insert the currently selected suggestion"""
        if 0 <= self.selected_index < len(self.suggestions):
            suggestion = self.suggestions[self.selected_index]
            if not suggestion.is_error:
                self.translation_selected.emit(suggestion.translation)
                self.close()

    def closeEvent(self, event):
        """Clean up worker on close and save window size and position"""
        # Save window size and position for next time
        settings = QSettings("Supervertaler", "MTQuickPopup")
        settings.setValue("width", self.width())
        settings.setValue("height", self.height())
        settings.setValue("x", self.x())
        settings.setValue("y", self.y())

        # Clean up worker
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(1000)
        super().closeEvent(event)


class QuickTransPanel(QuickTransProviderMixin, QWidget):
    """Docked QuickTrans panel for the under-grid tab area.

    A trimmed, always-on version of the QuickTrans popup. It auto-fetches the
    cheap/free MT engines (Google, MyMemory, Microsoft, ...) for the current
    segment's source text whenever the panel is visible. LLM providers
    (Claude, OpenAI, Gemini, ...) are NOT auto-fetched – each gets an
    on-demand "Fetch" button so paid AI calls only happen when the user asks.
    Clicking any result row inserts it into the current target cell.

    The host wires it up by:
        panel = QuickTransPanel(main_window)
        panel.translation_selected.connect(insert_fn)
        # on every segment change:
        panel.request_update(source_text, source_lang, target_lang)
    """

    translation_selected = pyqtSignal(str)

    def __init__(self, parent_app, parent=None):
        super().__init__(parent)
        self.parent_app = parent_app
        self.source_lang = getattr(parent_app, 'source_language', 'en')
        self.target_lang = getattr(parent_app, 'target_language', 'nl')

        self._pending: Optional[Tuple[str, str, str]] = None  # (source, src, tgt)
        self._last_fetched: Optional[str] = None              # source actually fetched
        self._fetch_token: int = 0          # bumped each fetch; stale workers are ignored
        self._workers: List[MTFetchWorker] = []   # keep refs so threads aren't GC'd mid-run
        self.suggestions: List[MTSuggestion] = []

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_fetch)

        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(4)

        # Header: just the action buttons, right-aligned. No title label –
        # the tab is already named "QuickTrans".
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addStretch()

        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("Re-fetch translations for the current segment")
        self._refresh_btn.setStyleSheet(_PANEL_ICON_BTN_STYLE)
        self._refresh_btn.clicked.connect(self._force_refresh)
        header.addWidget(self._refresh_btn)

        settings_btn = QPushButton("⚙️")
        settings_btn.setFixedSize(22, 22)
        settings_btn.setToolTip("Configure QuickTrans providers")
        settings_btn.setStyleSheet(_PANEL_ICON_BTN_STYLE)
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        outer.addLayout(header)

        # Persistent status / placeholder line. Lives in the OUTER layout, not
        # inside results_layout – _clear_results() wipes the results layout, so
        # keeping the label out of it avoids deleting the very widget we reuse.
        self.status_label = QLabel("Select a segment to see translations.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #888; font-size: 9pt; padding: 6px;")
        outer.addWidget(self.status_label)

        # Scrollable list of result rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.results_layout = QVBoxLayout(container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(4)
        self.results_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def _open_settings(self):
        if self.parent_app and hasattr(self.parent_app, 'open_mt_quick_lookup_settings'):
            self.parent_app.open_mt_quick_lookup_settings()

    # ── update lifecycle ────────────────────────────────────────────────
    def request_update(self, source_text: str, source_lang: str = None, target_lang: str = None):
        """Called by the host on every segment change. Stores the pending
        segment and (if the panel is visible) schedules a debounced fetch."""
        source_text = (source_text or "").strip()
        if source_lang:
            self.source_lang = source_lang
        if target_lang:
            self.target_lang = target_lang
        self._pending = (source_text, self.source_lang, self.target_lang)
        if self.isVisible() and source_text and source_text != self._last_fetched:
            self._debounce.start()

    def showEvent(self, event):
        """When the tab becomes visible, fetch the pending segment (the
        panel doesn't fetch while hidden, to avoid needless MT calls)."""
        super().showEvent(event)
        if self._pending and self._pending[0] and self._pending[0] != self._last_fetched:
            self._debounce.start()

    def _force_refresh(self):
        """Manual ↻: re-fetch the current segment even if unchanged."""
        self._last_fetched = None
        if self._pending and self._pending[0]:
            self._do_fetch()

    # ── rendering ───────────────────────────────────────────────────────
    def _make_section_header(self, text: str) -> QLabel:
        """A lightweight group-header label ('Machine translation' / 'AI / LLM')."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "QLabel { color: #888; font-size: 8pt; font-weight: bold; "
            "border: none; padding: 6px 2px 1px 2px; }"
        )
        return lbl

    def _clear_results(self):
        # Remove every widget except the trailing stretch (last item).
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.suggestions = []
        # Section-header anchors are recreated per fetch (see _do_fetch).
        self._mt_header = None
        self._ai_header = None

    def _do_fetch(self):
        if not self._pending:
            return
        source_text, src, tgt = self._pending
        if not source_text:
            return
        self._last_fetched = source_text
        self._clear_results()

        # Bump the token so any still-running worker from a previous segment
        # has its (late) results ignored rather than appended to this one.
        self._fetch_token += 1
        token = self._fetch_token

        mt_providers = self._get_enabled_providers(include_mt=True, include_llms=False)
        llm_providers = self._get_enabled_providers(include_mt=False, include_llms=True)

        if not mt_providers and not llm_providers:
            self.status_label.setText("⚠️ No QuickTrans providers enabled. Click ⚙ to configure.")
            self._show_status()
            return

        # Group headers: Machine translation first, then AI / LLM. MT rows are
        # inserted above the AI header; LLM rows below it (see _append_result and
        # _add_llm_button). A header is only shown if its section has providers.
        self._mt_header = None
        self._ai_header = None
        if mt_providers:
            self._mt_header = self._make_section_header("⚡  Machine translation")
            self.results_layout.insertWidget(self.results_layout.count() - 1, self._mt_header)
        if llm_providers:
            self._ai_header = self._make_section_header("\U0001F916  AI / LLM  ·  billed per use")
            self.results_layout.insertWidget(self.results_layout.count() - 1, self._ai_header)

        # Auto-fetch the cheap MT engines.
        if mt_providers:
            self.status_label.setText("Fetching…")
            self._show_status()
            self._start_worker(source_text, src, tgt, mt_providers,
                               on_ready=self._on_mt_result, token=token,
                               on_complete=self._on_mt_complete)
        else:
            self._hide_status()

        # LLMs: on-demand buttons only (no automatic, billable calls).
        for name, code, call_func in llm_providers:
            self._add_llm_button(name, code, call_func, source_text, src, tgt)

    def _start_worker(self, source_text, src, tgt, providers, on_ready, token, on_complete=None):
        """Start an MTFetchWorker, tracking it so it isn't GC'd mid-run and
        dropping its results if a newer fetch has superseded this one."""
        worker = MTFetchWorker(source_text, src, tgt, providers)
        self._workers.append(worker)

        def _ready(pn, pc, tr, err, _tok=token):
            if _tok == self._fetch_token:
                on_ready(pn, pc, tr, err)

        def _done(_w=worker, _tok=token):
            if on_complete is not None and _tok == self._fetch_token:
                on_complete()
            if _w in self._workers:
                self._workers.remove(_w)

        worker.result_ready.connect(_ready)
        worker.all_complete.connect(_done)
        worker.start()
        return worker

    def _show_status(self):
        self.status_label.show()

    def _hide_status(self):
        self.status_label.hide()

    def _on_mt_result(self, provider_name, provider_code, translation, is_error):
        self._hide_status()
        self._append_result(provider_name, provider_code, translation, is_error)

    def _on_mt_complete(self):
        # If nothing rendered at all (no MT rows AND no LLM buttons – only the
        # trailing stretch remains), surface a friendly message.
        if not self.suggestions and self.results_layout.count() <= 1:
            self.status_label.setText("No translations available.")
            self._show_status()

    def _append_result(self, name, code, translation, is_error) -> 'MTSuggestionItem':
        suggestion = MTSuggestion(name, code, translation, is_error)
        self.suggestions.append(suggestion)
        item = MTSuggestionItem(len(self.suggestions), suggestion)
        item.clicked.connect(self._on_item_clicked)
        # MT rows live above the AI / LLM header so MT stays grouped at the top;
        # fall back to before the trailing stretch when there is no AI section.
        ai_header = getattr(self, '_ai_header', None)
        if ai_header is not None and self.results_layout.indexOf(ai_header) >= 0:
            idx = self.results_layout.indexOf(ai_header)
        else:
            idx = self.results_layout.count() - 1
        self.results_layout.insertWidget(idx, item)
        return item

    def _add_llm_button(self, name, code, call_func, source_text, src, tgt):
        """Add an on-demand 'Fetch' row for an LLM provider."""
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background: #fafafa; border: 1px dashed #cfcfcf; border-radius: 4px; }"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)

        chip = QLabel(name)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = PROVIDER_COLORS.get(code, "#666")
        chip.setStyleSheet(
            f"QLabel {{ background-color: {bg}; color: white; font-weight: bold; "
            f"font-size: 9px; border-radius: 3px; padding: 2px 8px; }}"
        )
        h.addWidget(chip)

        hint = QLabel("AI – click to fetch")
        hint.setStyleSheet("color: #999; font-size: 9pt; border: none;")
        h.addWidget(hint)
        h.addStretch()

        btn = QPushButton("Fetch")
        btn.setFixedHeight(22)
        btn.setToolTip(f"Fetch an AI translation from {name} (makes one API call)")
        h.addWidget(btn)

        self.results_layout.insertWidget(self.results_layout.count() - 1, row)

        def on_click():
            btn.setEnabled(False)
            btn.setText("…")
            worker = MTFetchWorker(source_text, src, tgt, [(name, code, call_func)])
            self._workers.append(worker)

            def on_ready(pn, pc, tr, err):
                idx = self.results_layout.indexOf(row)
                if idx < 0:
                    idx = self.results_layout.count() - 1
                suggestion = MTSuggestion(pn, pc, tr, err)
                self.suggestions.append(suggestion)
                item = MTSuggestionItem(len(self.suggestions), suggestion)
                item.clicked.connect(self._on_item_clicked)
                self.results_layout.insertWidget(idx, item)
                row.setParent(None)
                row.deleteLater()

            def on_done(_w=worker):
                if _w in self._workers:
                    self._workers.remove(_w)

            worker.result_ready.connect(on_ready)
            worker.all_complete.connect(on_done)
            worker.start()

        btn.clicked.connect(on_click)

    def _on_item_clicked(self, translation: str):
        self.translation_selected.emit(translation)

    def insert_match_by_number(self, number: int) -> bool:
        """Insert the Nth currently-displayed QuickTrans result into the target.

        N is 1-based and matches the pick-number shown on each row. Returns True
        if a (non-error) result existed and was emitted for insertion, else False
        so the caller can fall back to another panel.
        """
        idx = number - 1
        if 0 <= idx < len(self.suggestions):
            s = self.suggestions[idx]
            if not s.is_error and s.translation:
                self.translation_selected.emit(s.translation)
                return True
        return False

    def closeEvent(self, event):
        # Let any in-flight workers finish so QThreads aren't destroyed while
        # running. They're short (one HTTP round-trip) and stale results are
        # already ignored via the fetch token.
        for w in list(self._workers):
            if w.isRunning():
                w.wait(1000)
        super().closeEvent(event)
