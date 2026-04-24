"""
Floating Assistant for Supervertaler
=======================================

A persistent floating window that replaces the QMenu-based QuickLauncher.
Contains a chat view (sharing the same ChatBackend) on the left and
a keyboard-navigable action panel on the right.

Activated by:
- Ctrl+Q (local, inside Supervertaler)
- Ctrl+Alt+Q (global, from any application)

When launched from the global hotkey the action panel receives focus
so the user can immediately navigate with arrow keys and press Enter.
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QKeyEvent, QFont, QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QScrollArea, QFrame, QApplication, QTreeWidget,
    QTreeWidgetItem, QAbstractItemView,
)

from modules.chat_backend import ChatBackend
from modules.chat_view_widget import ChatViewWidget


class FloatingAssistant(QWidget):
    """
    Floating window with chat + keyboard-navigable action panel.
    """

    def __init__(self, chat_backend: ChatBackend, parent_app, parent=None,
                 superlookup_class=None):
        super().__init__(parent)
        self._backend = chat_backend
        self._parent_app = parent_app
        self._superlookup_class = superlookup_class
        self._drag_pos = None
        self._is_maximised = False
        self._pre_max_geometry = None

        # Action data: list of callbacks
        self._action_items = []
        # Source window handle — captured when the assistant opens via global hotkey
        self._source_window = None

        # Geometry persistence
        user_data = getattr(parent_app, 'user_data_path', None)
        if user_data:
            self._state_file = Path(user_data) / "workbench" / "assistant_geometry.json"
        else:
            self._state_file = None

        # Regular top-level window (NOT always-on-top) — behaves like any
        # other app window: clicking a different program brings that
        # program to the front. The assistant can be brought back via
        # Ctrl+Shift+A, Ctrl+Q, or by clicking its taskbar icon.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(500, 350)
        self.resize(850, 520)

        # Window icon (taskbar / alt-tab) — canonical Sv mark, same file the
        # main Workbench window uses.
        self._apply_app_icon()

        self._init_ui()
        self._restore_state()

        # Global Escape shortcut — works regardless of which child has focus
        from PyQt6.QtGui import QShortcut, QKeySequence
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        esc_shortcut.activated.connect(self.hide)

    # ------------------------------------------------------------------
    # Branding helpers
    # ------------------------------------------------------------------

    def _resource_path(self, *parts) -> Path:
        """Resolve a repo-relative resource path. Works in dev and under PyInstaller.

        Mirrors Supervertaler.py's ``get_resource_path`` but is inlined here to
        avoid a circular import (Supervertaler.py imports from modules/, not
        the other way round).
        """
        import sys
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = Path(sys._MEIPASS)
        else:
            # modules/floating_assistant.py → .../Supervertaler/
            base_path = Path(__file__).resolve().parent.parent
        return base_path.joinpath(*parts)

    def _apply_app_icon(self):
        """Set the window icon (taskbar, alt-tab) to the canonical Sv mark."""
        try:
            from PyQt6.QtGui import QIcon
            icon_path = self._resource_path("assets", "icon.ico")
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception as e:
            print(f"FloatingAssistant: Could not set window icon: {e}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Outer frame for border
        outer = QFrame()
        outer.setObjectName("floatingOuter")
        outer.setStyleSheet("""
            QFrame#floatingOuter {
                background-color: #F5F7FA;
                border: 1px solid #B0B8C4;
                border-radius: 8px;
            }
        """)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(1, 1, 1, 1)
        outer_layout.setSpacing(0)

        # Title bar
        title_bar = self._create_title_bar()
        outer_layout.addWidget(title_bar)

        # Content: splitter with left panel (tabs) + right panel (actions)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setChildrenCollapsible(False)

        # Left panel: tabbed Chat + QuickTrans
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Tab bar for Chat / QuickTrans
        from PyQt6.QtWidgets import QTabWidget
        self._left_tabs = QTabWidget()
        self._left_tabs.setStyleSheet("""
            QTabBar::tab {
                padding: 6px 16px; font-size: 9pt;
            }
            QTabBar::tab:selected {
                font-weight: bold;
                border-bottom: 2px solid #3D5A80;
            }
        """)
        self._left_tabs.tabBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Chat tab
        self._chat_view = ChatViewWidget(
            self._backend,
            compact=True,
            show_autoprompt=False,
        )
        if hasattr(self._parent_app, 'prompt_manager_qt'):
            self._chat_view._do_send = self._parent_app.prompt_manager_qt._context_aware_send
        self._left_tabs.addTab(self._chat_view, "\U0001F4AC Chat")

        # QuickTrans widget — constructed here (so all self._qt_* state is
        # initialised) but NOT added to _left_tabs. It's reparented into the
        # Superlookup results_tabs as a sub-tab (after Termbases) once the
        # Superlookup widget is lazy-created in _ensure_superlookup_tab().
        self._quicktrans_widget = self._create_quicktrans_tab()
        self._quicktrans_embedded_in_superlookup = False

        # Superlookup tab — deferred until first show to avoid init-order
        # issues (the main window's database/termbase managers may not be
        # fully wired when the FloatingAssistant is first constructed).
        self._superlookup_widget = None
        self._superlookup_tab_added = False

        left_layout.addWidget(self._left_tabs)
        self._splitter.addWidget(left_panel)

        # Action panel (right)
        action_panel = self._create_action_panel()
        self._splitter.addWidget(action_panel)

        self._splitter.setSizes([520, 280])
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        outer_layout.addWidget(self._splitter, 1)

        # Context-aware info bar — shows a short tip depending on the active tab
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            "color: #888; font-size: 8pt; padding: 2px 8px; border: none;")
        self._info_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._info_label.setFixedHeight(18)
        outer_layout.addWidget(self._info_label)
        self._left_tabs.currentChanged.connect(self._update_info_label)
        self._update_info_label(0)

        # Resize grip (bottom-right corner)
        grip_bar = QWidget()
        grip_bar.setFixedHeight(6)
        grip_bar.setStyleSheet("background: transparent;")
        grip_bar.setCursor(Qt.CursorShape.SizeFDiagCursor)
        grip_bar.mousePressEvent = self._grip_press
        grip_bar.mouseMoveEvent = self._grip_move
        outer_layout.addWidget(grip_bar)

        main_layout.addWidget(outer)

    def _create_title_bar(self) -> QWidget:
        bar = QWidget()
        # 40px with explicit 8px top/bottom layout margins leaves a clean 24px
        # content band for the 24×24 Sv icon and 24×24 window buttons.
        bar.setFixedHeight(40)
        # Keep the un-scoped `QWidget { ... }` selector — scoping via object
        # name stops Qt from enabling styled background painting on a plain
        # QWidget, which made the bar lose its navy fill in an earlier pass.
        # The descendant-cascading is harmless since children (buttons, icon
        # label) supply their own background/border styling.
        bar.setStyleSheet("""
            QWidget {
                background-color: #3D5A80;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
            }
        """)

        layout = QHBoxLayout(bar)
        # 8px top/bottom margins guarantee the vertical centring of 24×24
        # content regardless of per-widget alignment flags.
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        # Sv icon — canonical Workbench brand mark, native 24×24 (no scaling).
        # The explicit stylesheet override is required: the bar's unscoped
        # `QWidget { background-color; border-top-*-radius }` rule otherwise
        # cascades down to this QLabel, and a border-radius on a QLabel triggers
        # Qt's styled-background painter which introduces a subtle rendering
        # offset (most visibly: the bottom edge of the pixmap looks clipped).
        sv_icon_label = QLabel()
        sv_icon_label.setStyleSheet(
            "QLabel { background: transparent; border: none; "
            "border-radius: 0; padding: 0; margin: 0; }"
        )
        sv_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv_icon_label.setContentsMargins(0, 0, 0, 0)
        sv_icon_path = self._resource_path("assets", "icon_24.png")
        if sv_icon_path.exists():
            from PyQt6.QtGui import QPixmap
            sv_icon_label.setPixmap(QPixmap(str(sv_icon_path)))
        sv_icon_label.setFixedSize(24, 24)
        layout.addWidget(sv_icon_label)

        title = QLabel("Supervertaler Sidekick")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 10pt; border: none;")
        layout.addWidget(title)
        layout.addStretch()

        # Settings (gear) — opens Workbench Settings tab
        settings_btn = QPushButton("\u2699")  # ⚙
        settings_btn.setFixedSize(24, 24)
        settings_btn.setToolTip("Open Supervertaler Workbench settings")
        settings_btn.setStyleSheet("""
            QPushButton {
                color: white; background: transparent;
                border: none; font-size: 14pt;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); border-radius: 4px; }
        """)
        settings_btn.clicked.connect(self._open_workbench_settings)
        layout.addWidget(settings_btn)

        # Minimise
        min_btn = QPushButton("\u2013")
        min_btn.setFixedSize(24, 24)
        min_btn.setStyleSheet("""
            QPushButton {
                color: white; background: transparent;
                border: none; font-size: 14pt; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); border-radius: 4px; }
        """)
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        # Maximise / Restore
        self._max_btn = QPushButton("\u25A1")  # □
        self._max_btn.setFixedSize(24, 24)
        self._max_btn.setStyleSheet("""
            QPushButton {
                color: white; background: transparent;
                border: none; font-size: 12pt; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); border-radius: 4px; }
        """)
        self._max_btn.clicked.connect(self._toggle_maximise)
        layout.addWidget(self._max_btn)

        # Close
        close_btn = QPushButton("\u00D7")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                color: white; background: transparent;
                border: none; font-size: 16pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #E53935; border-radius: 4px; }
        """)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        # Dragging
        bar.mousePressEvent = self._title_mouse_press
        bar.mouseMoveEvent = self._title_mouse_move

        return bar

    # ------------------------------------------------------------------
    # Action panel (expandable tree menu)
    # ------------------------------------------------------------------

    _CATEGORY_STYLE = "font-weight: bold; color: #3D5A80;"
    _LEAF_ICON = "\u2022"  # •

    def _create_action_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(200)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 8, 4, 4)
        panel_layout.setSpacing(4)

        header = QLabel("Menu")
        header.setStyleSheet(
            "font-weight: bold; font-size: 10pt; color: #3D5A80; "
            "border: none; padding-left: 6px;"
        )
        panel_layout.addWidget(header)

        # QTreeWidget for expandable categories + keyboard navigation
        self._action_tree = QTreeWidget()
        self._action_tree.setHeaderHidden(True)
        self._action_tree.setRootIsDecorated(True)
        self._action_tree.setAnimated(True)
        self._action_tree.setIndentation(16)
        self._action_tree.setStyleSheet("""
            QTreeWidget {
                border: none; background: transparent;
                font-size: 9pt; outline: none;
            }
            QTreeWidget::item {
                padding: 4px 6px; border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #D6E4F0; color: #1E1E1E;
            }
            QTreeWidget::item:hover {
                background-color: #FFFFFF;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: none;
                border-image: none;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                image: none;
                border-image: none;
            }
        """)
        self._action_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._action_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._action_tree.itemActivated.connect(self._on_tree_activated)
        self._action_tree.itemClicked.connect(self._on_tree_clicked)

        self._populate_actions()

        panel_layout.addWidget(self._action_tree, 1)
        return panel

    # Sentinel value to mark category nodes (no callback)
    _CATEGORY_SENTINEL = "__category__"

    def _make_category(self, label: str, expanded: bool = False) -> QTreeWidgetItem:
        """Create a bold category node with expand indicator.

        Categories are selectable (so arrow-key navigation highlights them)
        but activating them toggles expand/collapse instead of running a callback.
        """
        bold_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        cat_color = QBrush(QColor("#3D5A80"))
        cat = QTreeWidgetItem([label])
        cat.setFont(0, bold_font)
        cat.setForeground(0, cat_color)
        # Mark as category — keep selectable for keyboard highlight
        cat.setData(0, Qt.ItemDataRole.UserRole, self._CATEGORY_SENTINEL)
        self._action_tree.addTopLevelItem(cat)
        cat.setExpanded(expanded)
        return cat

    def _update_expand_indicators(self):
        """Update ▶/▼ indicators on all category nodes."""
        root = self._action_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.childCount() > 0:
                text = item.text(0)
                # Strip existing indicator
                for prefix in ("\u25B6 ", "\u25BC "):
                    if text.startswith(prefix):
                        text = text[2:]
                        break
                indicator = "\u25BC " if item.isExpanded() else "\u25B6 "
                item.setText(0, indicator + text)

    def _on_tree_expanded_collapsed(self, _item):
        """Slot for itemExpanded / itemCollapsed — update indicators."""
        self._update_expand_indicators()

    def _populate_actions(self):
        """Build the expandable tree menu."""
        self._action_tree.clear()
        self._action_items.clear()

        # Connect expand/collapse signals for indicator updates
        try:
            self._action_tree.itemExpanded.disconnect(self._on_tree_expanded_collapsed)
            self._action_tree.itemCollapsed.disconnect(self._on_tree_expanded_collapsed)
        except (TypeError, RuntimeError):
            pass
        self._action_tree.itemExpanded.connect(self._on_tree_expanded_collapsed)
        self._action_tree.itemCollapsed.connect(self._on_tree_expanded_collapsed)

        # -- Workbench Tools --
        # QuickTrans is no longer a separate menu entry: it's the first
        # sub-tab inside SuperLookup, so clicking "SuperLookup" lands on it
        # automatically. Leaving only one entry here keeps the menu tidy.
        tools_cat = self._make_category("\U0001F6E0 Workbench Tools", expanded=True)
        self._add_tree_action(tools_cat, "\U0001F50D SuperLookup", self._on_superlookup)

        # -- Prompt library items (grouped by folder) --
        self._populate_prompt_library_tree()

        # -- Snippets (file-backed, user-editable) --
        # Replaces the pre-v1.9.387 hardcoded Special Characters / Personal
        # Snippets entries. Reads .md files from <user_data>/snippet_library/
        # and groups them into tree categories by top-level folder name.
        self._populate_snippet_library_tree()

        # -- Text Conversions --
        text_cat = self._make_category("\U0001F524 Text Conversions")
        self._add_tree_action(text_cat, "Uppercase", lambda: self._text_convert(str.upper))
        self._add_tree_action(text_cat, "Lowercase", lambda: self._text_convert(str.lower))
        self._add_tree_action(text_cat, "Title Case", lambda: self._text_convert(str.title))
        self._add_tree_action(text_cat, "Sentence case", lambda: self._text_convert(self._to_sentence_case))
        self._add_tree_action(text_cat, "Single curly quotes: \u2018Example\u2019", lambda: self._text_wrap("\u2018", "\u2019"))
        self._add_tree_action(text_cat, "Double curly quotes: \u201CExample\u201D", lambda: self._text_wrap("\u201C", "\u201D"))
        self._add_tree_action(text_cat, "Round brackets: (Example)", lambda: self._text_wrap("(", ")"))
        self._add_tree_action(text_cat, "Square brackets: [Example]", lambda: self._text_wrap("[", "]"))
        self._add_tree_action(text_cat, "Remove soft hyphens (U+00AD)", lambda: self._text_convert(lambda s: s.replace("\u00AD", "")))
        self._add_tree_action(text_cat, "Double quotes \u2192 single quotes", lambda: self._text_convert(lambda s: s.replace('"', "'")))
        self._add_tree_action(text_cat, "Make <b>bold</b>", lambda: self._text_wrap("<b>", "</b>"))

        # Set initial expand indicators
        self._update_expand_indicators()

    def _populate_snippet_library_tree(self):
        """Add file-backed snippets to the Sidekick tree.

        Reads .md snippet files from ``<user_data>/snippet_library/`` via the
        :class:`SnippetLibrary` loader. Top-level folders become tree categories
        (Special Characters, Personal Snippets, plus any user-created folders).
        Defaults are seeded on first run; existing files are never overwritten.
        """
        try:
            from modules.snippet_library import SnippetLibrary, DEFAULT_SNIPPETS

            user_data_path = getattr(self._parent_app, 'user_data_path', None)
            if not user_data_path:
                return

            library_dir = Path(user_data_path) / "snippet_library"
            lib = SnippetLibrary(library_dir=str(library_dir))
            lib.ensure_defaults(DEFAULT_SNIPPETS)
            lib.load_all()

            if not lib.snippets:
                return

            # Group by top-level category (folder name). Files placed directly
            # in the library root fall back to a generic "Snippets" bucket.
            from collections import defaultdict
            by_category = defaultdict(list)
            for snip in lib.snippets:
                cat = snip['category'] or "Snippets"
                by_category[cat].append(snip)

            # Category icons for the known defaults. Any other folder the user
            # creates gets the generic folder glyph.
            category_icons = {
                "Special Characters": "\u2728",        # ✨
                "Personal Snippets": "\U0001F4C7",     # 📇
            }
            default_icon = "\U0001F4C1"                # 📁

            for cat_name in sorted(by_category.keys(), key=str.lower):
                icon = category_icons.get(cat_name, default_icon)
                cat_item = self._make_category(f"{icon} {cat_name}")
                for snip in sorted(by_category[cat_name], key=lambda s: s['label'].lower()):
                    self._add_snippet(cat_item, snip['label'], snip['body'])

        except Exception as e:
            print(f"FloatingAssistant: Error populating snippets: {e}")

    def _populate_prompt_library_tree(self):
        """Add prompt library items grouped by their folder structure."""
        try:
            pm = getattr(self._parent_app, 'prompt_manager_qt', None)
            if not pm:
                return
            lib = getattr(pm, 'library', None)
            if not lib or not hasattr(lib, 'get_quicklauncher_grid_prompts'):
                return

            items = lib.get_quicklauncher_grid_prompts() or []
            if not items:
                return

            from collections import defaultdict
            folders = defaultdict(list)
            for rel_path, label in items:
                parts = rel_path.replace('\\', '/').split('/')
                if len(parts) > 1:
                    folder = parts[0]
                else:
                    folder = "Prompts"
                display = label or parts[-1].replace('.md', '')
                folders[folder].append((rel_path, display))

            prompts_cat = self._make_category("\U0001F4DD Prompts", expanded=True)

            for folder, folder_items in sorted(folders.items()):
                if len(folders) == 1 and folder == "Prompts":
                    parent = prompts_cat
                else:
                    sub_cat = QTreeWidgetItem([f"\U0001F4C1 {folder}"])
                    sub_cat.setData(0, Qt.ItemDataRole.UserRole, self._CATEGORY_SENTINEL)
                    prompts_cat.addChild(sub_cat)
                    parent = sub_cat

                for rel_path, display in sorted(folder_items, key=lambda x: x[1].lower()):
                    self._add_tree_action(
                        parent,
                        f"{self._LEAF_ICON} {display}",
                        lambda checked=False, p=rel_path: self._on_prompt_action(p),
                    )

        except Exception as e:
            print(f"FloatingAssistant: Error populating prompts: {e}")

    def _add_tree_action(self, parent: QTreeWidgetItem, text: str, callback):
        """Add a leaf action item under a parent category."""
        item = QTreeWidgetItem([text])
        idx = len(self._action_items)
        item.setData(0, Qt.ItemDataRole.UserRole, idx)
        parent.addChild(item)
        self._action_items.append(callback)

    def _add_snippet(self, parent: QTreeWidgetItem, label: str, text: str):
        """Add a snippet item that copies text to clipboard when clicked."""
        self._add_tree_action(
            parent,
            label,
            lambda t=text: self._insert_snippet(t),
        )

    def _insert_snippet(self, text: str):
        """Direct action: put snippet on clipboard, hide, return to source, paste."""
        self._paste_and_return(text)

    # ------------------------------------------------------------------
    # Text conversions
    # ------------------------------------------------------------------

    def _text_convert(self, fn):
        """Direct action: transform clipboard text, hide, return to source, paste."""
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            return
        result = fn(text)
        self._paste_and_return(result)

    def _text_wrap(self, prefix: str, suffix: str):
        """Direct action: wrap clipboard text, hide, return to source, paste."""
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            return
        result = prefix + text + suffix
        self._paste_and_return(result)

    def _paste_and_return(self, text: str):
        """Put text on clipboard, hide the assistant, return to source app, paste.

        This is the core "direct action" flow for snippets and text conversions:
        the user selects text, presses the global hotkey, picks an action,
        and the result replaces their selection seamlessly.
        """
        from PyQt6.QtCore import QTimer

        # 1. Put result on clipboard
        QApplication.clipboard().setText(text)

        # 2. Hide the assistant window
        self.hide()

        # 3. After a short delay, activate the source window and send Ctrl+V
        def _do_paste():
            try:
                from modules.platform_helpers import (
                    activate_foreground_window, CrossPlatformKeySender
                )
                if self._source_window:
                    activate_foreground_window(self._source_window)

                import time
                time.sleep(0.15)  # Let the OS finish the window switch

                sender = CrossPlatformKeySender()
                sender.send_paste()
            except Exception as e:
                print(f"[FloatingAssistant] Paste-and-return error: {e}")

        QTimer.singleShot(100, _do_paste)

    @staticmethod
    def _to_sentence_case(text: str) -> str:
        """Convert text to sentence case (capitalise first letter after sentence boundaries)."""
        import re
        # Lowercase everything first
        result = text.lower()
        # Capitalise after sentence-ending punctuation + whitespace, or at the start
        result = re.sub(
            r'(?:^|[.!?]\s+)([a-z])',
            lambda m: m.group(0)[:-1] + m.group(1).upper(),
            result,
        )
        # Ensure the very first character is capitalised
        if result:
            result = result[0].upper() + result[1:]
        return result

    # ------------------------------------------------------------------
    # QuickTrans tab
    # ------------------------------------------------------------------

    # Provider code → icon filename (in assets/providers/)
    _PROVIDER_ICONS = {
        "GT":  "google",
        "DL":  "deepl",
        "MS":  "microsoft",
        "AT":  "amazon",
        "MMT": "modernmt",
        "MM":  "mymemory",
        # LLM providers (matched by name)
    }
    _PROVIDER_NAME_TO_ICON = {
        "openai": "openai", "claude": "claude", "gemini": "gemini",
        "mistral": "mistral", "ollama": "ollama", "openrouter": "openrouter",
        "custom": "openrouter",
    }

    def _create_quicktrans_tab(self) -> QWidget:
        """Create an embedded QuickTrans panel (compact GT4T style)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Source text (compact, one line if possible)
        self._qt_source_label = QLabel("Select text and press Ctrl+Alt+Q to translate.")
        self._qt_source_label.setWordWrap(True)
        self._qt_source_label.setStyleSheet(
            "color: #C0392B; font-size: 9pt; padding: 6px 8px; "
            "background-color: #FEF9E7; border: 1px solid #F0E68C; "
            "border-radius: 4px;"
        )
        layout.addWidget(self._qt_source_label)

        # Results list (keyboard-navigable)
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        self._qt_list = QListWidget()
        self._qt_list.setStyleSheet("""
            QListWidget {
                border: none; background: transparent;
                font-size: 9pt; outline: none;
            }
            QListWidget::item {
                padding: 3px 6px; border-bottom: 1px solid #F0F0F0;
            }
            QListWidget::item:selected {
                background-color: #E8F4FD; color: #1E1E1E;
            }
            QListWidget::item:hover {
                background-color: #F5F5F5;
            }
        """)
        self._qt_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._qt_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._qt_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._qt_list.itemActivated.connect(self._on_qt_item_activated)
        self._qt_list.itemClicked.connect(self._on_qt_item_activated)
        layout.addWidget(self._qt_list, 1)

        # Hint bar
        hint = QLabel("1\u20139 to insert \u2022 \u2191\u2193 Enter to select \u2022 Click to copy")
        hint.setStyleSheet("color: #999; font-size: 7pt; padding: 2px 6px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # Input area
        from PyQt6.QtWidgets import QPlainTextEdit
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(5, 5, 5, 5)
        input_layout.setSpacing(4)

        self._qt_input = QPlainTextEdit()
        self._qt_input.setMaximumHeight(60)
        self._qt_input.setPlaceholderText("Type or paste text to translate\u2026")
        self._qt_input.setStyleSheet("""
            QPlainTextEdit {
                border: none; font-size: 10pt;
                color: #1a1a1a; background-color: white;
                padding: 4px;
            }
        """)
        # Enter to translate (Shift+Enter for newline)
        self._qt_input.installEventFilter(self)
        input_layout.addWidget(self._qt_input)

        # Bottom row: Translate button
        qt_bottom = QHBoxLayout()
        qt_bottom.setContentsMargins(0, 0, 0, 0)
        qt_bottom.addStretch()

        translate_btn = QPushButton("Translate")
        translate_btn.setStyleSheet("""
            QPushButton {
                background-color: #E67E22; color: white;
                font-weight: bold; padding: 8px 20px;
                border-radius: 5px; border: none;
            }
            QPushButton:hover { background-color: #D35400; }
            QPushButton:pressed { background-color: #BA4A00; }
        """)
        translate_btn.clicked.connect(self._on_qt_translate_clicked)
        qt_bottom.addWidget(translate_btn)

        input_layout.addLayout(qt_bottom)
        layout.addWidget(input_frame)

        # State
        self._qt_suggestions = []
        self._qt_popup_ref = None

        return tab

    def _on_qt_translate_clicked(self):
        """Translate text from the QuickTrans input field."""
        text = self._qt_input.toPlainText().strip()
        if text:
            self._run_quicktrans(text)

    def _run_quicktrans(self, text: str):
        """Fetch translations from all enabled providers and display results."""
        if not text:
            return

        # QuickTrans now lives as a sub-tab of Superlookup (outer Superlookup
        # tab, inner sub-tab index 2 — after Termbases). Make sure Superlookup
        # is lazy-built (this also re-parents QuickTrans into its results_tabs
        # on first call), then switch the outer tab to Superlookup and the
        # inner tab to QuickTrans.
        self._ensure_superlookup_tab()

        # Outer: find Superlookup tab index (it's dynamic — Chat + possibly
        # Superlookup, so don't hard-code a number).
        outer_superlookup_idx = self._left_tabs.indexOf(self._superlookup_widget) \
            if self._superlookup_widget is not None else -1
        if outer_superlookup_idx >= 0:
            self._left_tabs.setCurrentIndex(outer_superlookup_idx)

        # Inner: find QuickTrans inside the Superlookup results_tabs.
        try:
            rtabs = getattr(self._superlookup_widget, 'results_tabs', None)
            if rtabs is not None:
                qt_inner_idx = rtabs.indexOf(self._quicktrans_widget)
                if qt_inner_idx >= 0:
                    rtabs.setCurrentIndex(qt_inner_idx)
        except Exception:
            pass

        # Update source display
        self._qt_source_label.setText(text)
        self._qt_source_label.setStyleSheet(
            "color: #C0392B; font-size: 9pt; padding: 6px 8px; "
            "background-color: #FEF9E7; border: 1px solid #F0E68C; "
            "border-radius: 4px;"
        )

        # Clear previous results
        self._qt_suggestions.clear()
        self._qt_list.clear()

        # Use MTFetchWorker directly with providers from the main app
        try:
            from modules.quicktrans import MTFetchWorker, MTQuickPopup

            app = self._parent_app

            # Get languages
            source_lang = getattr(app, 'source_language', 'English')
            target_lang = getattr(app, 'target_language', 'Dutch')
            if hasattr(app, 'current_project') and app.current_project:
                source_lang = getattr(app.current_project, 'source_lang', source_lang) or source_lang
                target_lang = getattr(app.current_project, 'target_lang', target_lang) or target_lang

            # Get providers via a hidden popup (it auto-starts fetching, but we
            # hide it immediately and also connect to our own result handlers)
            popup = MTQuickPopup(
                parent_app=app,
                source_text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                parent=None,
                external_mode=True,
            )
            popup.hide()

            # Connect our handlers to the already-running worker
            if popup.worker:
                popup.worker.result_ready.connect(self._on_qt_result)
                popup.worker.all_complete.connect(self._on_qt_complete)
                popup.worker.all_complete.connect(lambda: popup.close())
            else:
                self._qt_status_label.setText(
                    "No providers configured.\nGo to Settings \u2192 QuickTrans."
                )

            # Keep reference to prevent GC
            self._qt_popup_ref = popup

        except Exception as e:
            self._qt_status_label.setText(f"\u26A0 Error: {e}")
            import traceback
            traceback.print_exc()

    def _get_provider_icon(self, provider_code: str, provider_name: str):
        """Resolve a provider icon (QIcon) from assets/providers/."""
        from PyQt6.QtGui import QIcon, QPixmap
        import os

        # Try by code first, then by name
        icon_name = self._PROVIDER_ICONS.get(provider_code)
        if not icon_name:
            name_lower = provider_name.lower()
            for key, val in self._PROVIDER_NAME_TO_ICON.items():
                if key in name_lower:
                    icon_name = val
                    break

        if icon_name:
            # Try relative to the app directory
            for base in [os.path.dirname(os.path.dirname(__file__)), '.']:
                path = os.path.join(base, 'assets', 'providers', f'{icon_name}.png')
                if os.path.exists(path):
                    return QIcon(path)

        return QIcon()  # Empty icon fallback

    def _on_qt_result(self, provider_name: str, provider_code: str, translation: str, is_error: bool):
        """Handle a single translation result arriving (compact GT4T style with icons)."""
        from PyQt6.QtWidgets import QListWidgetItem
        from PyQt6.QtCore import QSize

        idx = len(self._qt_suggestions) + 1
        self._qt_suggestions.append((provider_name, translation, is_error))

        # Compact format: "1  translation text"
        if is_error:
            display = f"{idx}  \u26A0 {translation}"
        else:
            short = translation[:200] + ("\u2026" if len(translation) > 200 else "")
            display = f"{idx}  {short}"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, translation)
        item.setToolTip(f"{provider_name}: {translation}")

        # Set provider icon
        icon = self._get_provider_icon(provider_code, provider_name)
        if not icon.isNull():
            item.setIcon(icon)
            self._qt_list.setIconSize(QSize(16, 16))

        if is_error:
            item.setForeground(QBrush(QColor("#c0392b")))
        self._qt_list.addItem(item)

        # Auto-select first result
        if idx == 1:
            self._qt_list.setCurrentRow(0)

    def _on_qt_complete(self):
        """All translations fetched."""
        if not self._qt_suggestions:
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem("No translations received.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._qt_list.addItem(item)

        # Focus the list for keyboard navigation
        self._qt_list.setFocus()

    def _on_qt_item_activated(self, item):
        """Handle Enter or click on a QuickTrans result."""
        translation = item.data(Qt.ItemDataRole.UserRole)
        if translation:
            self._paste_and_return(translation)

    def _copy_qt_result(self, text: str):
        """Copy a QuickTrans result to clipboard."""
        QApplication.clipboard().setText(text)

    def _on_tree_activated(self, item: QTreeWidgetItem, column: int):
        """Called when user presses Enter or double-clicks a tree item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data == self._CATEGORY_SENTINEL or item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
            return
        if isinstance(data, int) and 0 <= data < len(self._action_items):
            self._action_items[data]()

    def _on_tree_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle single-click — expand categories, run leaf actions."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data == self._CATEGORY_SENTINEL or item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
            return
        if isinstance(data, int) and 0 <= data < len(self._action_items):
            self._action_items[data]()

    def refresh_actions(self):
        """Rebuild the action tree (call after prompt library changes)."""
        self._populate_actions()

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _get_action_text(self) -> str:
        """Get text for an action: chat input first, then clipboard."""
        text = self._chat_view.get_input_text()
        if not text:
            text = (QApplication.clipboard().text() or "").strip()
        return text

    def _get_lookup_tab(self):
        """Find the SuperlookupTab instance (lives on main window)."""
        mw = self._parent_app
        return getattr(mw, 'lookup_tab', None)

    def _on_quicktrans(self):
        text = self._get_action_text()
        if not text:
            self._backend.add_message("system", "\u26A0 No text available. Type or select text first.")
            return
        self._run_quicktrans(text)

    def _on_superlookup(self):
        text = self._get_action_text()
        self.show_superlookup(text)

    def show_superlookup(self, text=None):
        """Show the assistant, switch to the SuperLookup tab, and optionally search.

        When text is supplied, we also auto-fire QuickTrans for the same text
        (via _run_quicktrans, which switches to the QuickTrans sub-tab and
        kicks off the MT fetch). That means clicking the SuperLookup action
        in the right-hand menu with text selected lands the user on a
        populated QuickTrans sub-tab with translations already loading —
        no need to click the Translate button separately.
        """
        self._ensure_superlookup_tab()

        if self._superlookup_widget is None:
            self._backend.add_message("system", "\u26A0 SuperLookup not available.")
            return

        # Ensure the window is visible and in the foreground
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self._force_foreground_focus()

        # Switch to the SuperLookup tab
        self._left_tabs.setCurrentWidget(self._superlookup_widget)

        # Populate search field and trigger search if text provided
        if text and hasattr(self._superlookup_widget, 'source_text'):
            self._superlookup_widget.source_text.setEditText(text)
            self._sync_text_to_quicktrans(text)
            if hasattr(self._superlookup_widget, 'perform_lookup'):
                self._superlookup_widget.perform_lookup()
            # Auto-fire QuickTrans as well. _run_quicktrans switches the
            # SuperLookup sub-tab to QuickTrans and starts the provider
            # fetches immediately — matches what Ctrl+Alt+Q does, so the
            # user doesn't have to click "Translate" after navigating here.
            self._run_quicktrans(text)

    def _sync_superlookup_to_quicktrans(self):
        """Called when the Superlookup search button is clicked manually."""
        if self._superlookup_widget and hasattr(self._superlookup_widget, 'source_text'):
            text = self._superlookup_widget.source_text.currentText().strip()
            if text:
                self._sync_text_to_quicktrans(text)

    def _sync_text_to_quicktrans(self, text):
        """Pre-fill the QuickTrans input field so the user can switch tabs
        and click Translate to run the same query with MT/AI engines."""
        if text and hasattr(self, '_qt_input'):
            self._qt_input.setPlainText(text)

    def _on_prompt_action(self, rel_path: str):
        """Run a prompt from the library using the chat input text as context."""
        input_text = self._chat_view.get_input_text()
        if not input_text:
            # Try clipboard
            clipboard = QApplication.clipboard()
            input_text = (clipboard.text() or "").strip()

        if not input_text:
            self._backend.add_message(
                "system",
                "\u26A0 No text available. Type or paste text in the input field first.",
            )
            return

        # Build the prompt from the template
        try:
            pm = getattr(self._parent_app, 'prompt_manager_qt', None)
            if not pm:
                return
            lib = getattr(pm, 'library', None)
            if not lib:
                return

            prompt_data = lib.prompts.get(rel_path)
            if not prompt_data:
                self._backend.add_message("system", f"\u26A0 Prompt not found: {rel_path}")
                return

            prompt_content = (prompt_data.get('content') or "").strip()
            if not prompt_content:
                self._backend.add_message("system", "\u26A0 Prompt content is empty.")
                return

            # Get languages from project if available
            source_lang = "English"
            target_lang = "Dutch"
            if hasattr(self._parent_app, 'current_project') and self._parent_app.current_project:
                source_lang = getattr(self._parent_app.current_project, 'source_lang', source_lang) or source_lang
                target_lang = getattr(self._parent_app.current_project, 'target_lang', target_lang) or target_lang

            # Replace placeholders
            prompt_content = prompt_content.replace("{{SOURCE_LANGUAGE}}", source_lang)
            prompt_content = prompt_content.replace("{{TARGET_LANGUAGE}}", target_lang)
            prompt_content = prompt_content.replace("{{SOURCE_TEXT}}", input_text)
            prompt_content = prompt_content.replace("{{TARGET_TEXT}}", "")
            prompt_content = prompt_content.replace("{{SELECTION}}", input_text)

            # If prompt doesn't contain the input text via placeholders, append it
            original_content = prompt_data.get('content', '')
            if "{{SOURCE_TEXT}}" not in original_content and "{{SELECTION}}" not in original_content:
                prompt_content += f"\n\nText:\n{input_text}"

            # Show the user message
            prompt_name = prompt_data.get('name', rel_path)
            self._backend.add_message("user", f"[{prompt_name}] {input_text}")
            self._chat_view._chat_input.clear()

            # Send through the backend
            system_prompt = "You are an AI assistant. Follow the instructions precisely."
            response, metadata = self._backend.send_ai_request(prompt_content, system_prompt)

            if response and response.strip():
                self._backend.add_message("assistant", response, metadata=metadata)
            else:
                self._backend.add_message("system", "\u26A0 No response received.")

        except Exception as e:
            self._backend.add_message("system", f"\u26A0 Error: {e}")

    # ------------------------------------------------------------------
    # Context-aware info bar
    # ------------------------------------------------------------------

    # Outer tab info bar. QuickTrans is the first sub-tab of SuperLookup
    # (opens automatically when the SuperLookup outer tab is clicked), with
    # TMs/Termbases/Web Resources/Settings as the remaining sub-tabs.
    _TAB_INFO = {
        0: "AI chat assistant – ask questions, get translations, save answers to your memory bank",
        1: "SuperLookup – QuickTrans (Ctrl+Alt+Q), TMs, termbases (Ctrl+Alt+L), and web resources in one place",
    }

    def _update_info_label(self, index):
        self._info_label.setText(self._TAB_INFO.get(index, ""))

    # ------------------------------------------------------------------
    # Lazy Superlookup tab init
    # ------------------------------------------------------------------

    def _ensure_superlookup_tab(self):
        """Lazily create the Superlookup tab on first show.

        Deferred because the main window's database and termbase managers
        may not be fully wired when the FloatingAssistant is first
        constructed during create_main_layout().

        Also re-parents the pre-built QuickTrans widget into Superlookup's
        internal results_tabs at index 2 (after Termbases) so QuickTrans
        lives as a Superlookup sub-tab rather than a top-level outer tab.
        """
        if self._superlookup_tab_added or self._superlookup_class is None:
            return
        self._superlookup_tab_added = True
        try:
            user_data = getattr(self._parent_app, 'user_data_path', None)
            self._superlookup_widget = self._superlookup_class(
                self._parent_app, user_data_path=user_data)
            self._superlookup_widget.set_compact_mode(True)
            self._left_tabs.addTab(
                self._superlookup_widget, "\U0001F50D SuperLookup")
            # Sync search text to QuickTrans whenever a Superlookup search runs
            if hasattr(self._superlookup_widget, 'search_btn'):
                self._superlookup_widget.search_btn.clicked.connect(
                    self._sync_superlookup_to_quicktrans)

            # Re-parent QuickTrans into SuperLookup's results_tabs at index 0,
            # so the sub-tab order becomes:
            #   0 QuickTrans | 1 TMs | 2 Termbases | 3 Web Resources | 4 SuperLookup Settings
            # QuickTrans is first because that's where users most often want
            # to land when pressing Ctrl+Alt+Q or clicking the SuperLookup tab.
            try:
                rtabs = getattr(self._superlookup_widget, 'results_tabs', None)
                if rtabs is not None and not self._quicktrans_embedded_in_superlookup:
                    rtabs.insertTab(0, self._quicktrans_widget, "\u26A1 QuickTrans")
                    # Select QuickTrans by default so opening the SuperLookup
                    # outer tab lands on it automatically.
                    rtabs.setCurrentIndex(0)
                    self._quicktrans_embedded_in_superlookup = True
            except Exception as e:
                print(f"[FloatingAssistant] Could not embed QuickTrans into SuperLookup: {e}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            log = getattr(self._parent_app, 'log', None)
            if log:
                log(f"\u26A0 FloatingAssistant: Could not load Superlookup tab: {e}")

    # ------------------------------------------------------------------
    # Show / toggle
    # ------------------------------------------------------------------

    def show_at_cursor(self, captured_text=None, focus_actions=False,
                       source_window=None):
        """
        Show the floating assistant.

        Positioning logic:
        - If the user has previously repositioned the window, reopen there.
        - Otherwise, centre on the primary monitor.

        Args:
            captured_text: Text to insert into the chat input.
            focus_actions: If True, focus the action tree for keyboard navigation.
            source_window: Handle of the window that was active before the hotkey
                           (used to return focus after direct actions).
        """
        self._source_window = source_window

        # Always start on the Chat tab (QuickTrans tab is only
        # selected explicitly by _run_quicktrans)
        self._ensure_superlookup_tab()
        self._left_tabs.setCurrentIndex(0)

        # Always start with a clean input field
        self._chat_view._chat_input.clear()
        if captured_text:
            self._chat_view.insert_text(captured_text)

        # If already visible, just bring to front
        if self.isVisible():
            self.raise_()
            self.activateWindow()
            self._force_foreground_focus()
            if focus_actions:
                self._action_tree.setFocus()
            else:
                self._chat_view.focus_input()
            return

        if self._has_saved_position:
            # Reopen where the user last left it.
            x, y = self._saved_x, self._saved_y
            # Pick the screen the saved position belongs to (if any), so
            # a window saved on monitor 2 reopens on monitor 2.
            from PyQt6.QtCore import QPoint
            screen = QApplication.screenAt(QPoint(x + self.width() // 2,
                                                  y + self.height() // 2))
            if screen is None:
                # Saved position is off-screen (monitor removed?) — fall
                # back to the screen under the cursor.
                screen = QApplication.screenAt(QCursor.pos()) \
                    or QApplication.primaryScreen()
        else:
            # First launch — open on the screen where the cursor currently is
            # (user's active monitor), not necessarily the primary.
            screen = QApplication.screenAt(QCursor.pos()) \
                or QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                x = geom.left() + (geom.width() - self.width()) // 2
                y = geom.top() + (geom.height() - self.height()) // 2
            else:
                x = 200
                y = 200

        # Always clamp to the chosen screen so the window is fully visible,
        # even if the saved geometry is larger than the screen or extends
        # past its edges.
        if screen:
            geom = screen.availableGeometry()
            # If the window is wider/taller than the screen, shrink it.
            w = min(self.width(), geom.width())
            h = min(self.height(), geom.height())
            if w != self.width() or h != self.height():
                self.resize(w, h)
            x = max(geom.left(), min(x, geom.right() - w))
            y = max(geom.top(), min(y, geom.bottom() - h))

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

        # Force OS-level foreground focus (needed for apps like Trados Studio
        # that aggressively reclaim keyboard focus)
        self._force_foreground_focus()

        if focus_actions:
            self._action_tree.setFocus()
            first_leaf = self._find_first_leaf(self._action_tree.invisibleRootItem())
            if first_leaf:
                self._action_tree.setCurrentItem(first_leaf)
        else:
            self._chat_view.focus_input()

    def toggle(self, captured_text=None):
        """Toggle visibility (used by local Ctrl+Q).

        If the window is visible but buried behind other windows,
        bring it to the foreground instead of hiding it.
        """
        if self.isVisible():
            if self.isActiveWindow():
                self.hide()
            else:
                # Visible but not in front — bring to foreground
                self.raise_()
                self.activateWindow()
        else:
            self.show_at_cursor(captured_text)

    # ------------------------------------------------------------------
    # Dragging (title bar)
    # ------------------------------------------------------------------

    def _open_workbench_settings(self):
        """Bring the main Workbench window to the foreground and switch to
        its Settings tab. The floating assistant stays open so the user
        can reference it while adjusting settings."""
        mw = self._parent_app
        if not mw:
            return
        try:
            if mw.isMinimized():
                mw.showNormal()
            mw.show()
            mw.raise_()
            mw.activateWindow()

            import sys
            if sys.platform == 'win32':
                try:
                    import ctypes
                    hwnd = int(mw.winId())
                    fg = ctypes.windll.user32.GetForegroundWindow()
                    fg_thread = ctypes.windll.user32.GetWindowThreadProcessId(fg, None)
                    our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                    if fg_thread != our_thread:
                        ctypes.windll.user32.AttachThreadInput(fg_thread, our_thread, True)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        ctypes.windll.user32.AttachThreadInput(fg_thread, our_thread, False)
                    else:
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass

            # Switch to the Settings tab (index 4)
            if hasattr(mw, 'main_tabs'):
                mw.main_tabs.setCurrentIndex(4)
        except Exception as e:
            log = getattr(mw, 'log', None)
            if log:
                log(f"\u26A0 Could not open Workbench settings: {e}")

    def _toggle_maximise(self):
        """Toggle between maximised (fills screen) and normal size.

        Uses the window's OWN current screen, not the primary one. If you
        dragged the assistant to a secondary monitor and press Maximise, it
        should fill that monitor — not jump back to the primary display.
        """
        if self._is_maximised:
            # Restore to saved geometry
            if self._pre_max_geometry:
                self.setGeometry(self._pre_max_geometry)
            self._is_maximised = False
            self._max_btn.setText("\u25A1")  # □
        else:
            # Save current geometry and fill the available area of the
            # screen this window is currently on. self.screen() (Qt6) is
            # monitor-aware; if it's somehow unavailable fall back to the
            # screen under the window centre, then finally to primaryScreen.
            self._pre_max_geometry = self.geometry()
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                center = self.frameGeometry().center()
                screen = QApplication.screenAt(center) or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                self.setGeometry(avail)
            self._is_maximised = True
            self._max_btn.setText("\u2750")  # ❐

    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _title_mouse_move(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Resize grip (bottom-right)
    # ------------------------------------------------------------------

    def _grip_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._resize_start = event.globalPosition().toPoint()
            self._resize_orig_size = self.size()

    def _grip_move(self, event):
        if hasattr(self, '_resize_start') and self._resize_start and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start
            new_w = max(self.minimumWidth(), self._resize_orig_size.width() + delta.x())
            new_h = max(self.minimumHeight(), self._resize_orig_size.height() + delta.y())
            self.resize(new_w, new_h)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self):
        """Save window size, position, and splitter proportions."""
        # Remember position for this session too
        self._saved_x = self.x()
        self._saved_y = self.y()
        self._has_saved_position = True

        if not self._state_file:
            return
        try:
            state = {
                'width': self.width(),
                'height': self.height(),
                'x': self.x(),
                'y': self.y(),
                'splitter': self._splitter.sizes(),
            }
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _restore_state(self):
        """Restore saved window size, splitter proportions, and position."""
        self._has_saved_position = False

        if not self._state_file or not self._state_file.exists():
            return
        try:
            with open(self._state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            w = state.get('width', 850)
            h = state.get('height', 520)
            self.resize(max(self.minimumWidth(), w), max(self.minimumHeight(), h))

            splitter_sizes = state.get('splitter')
            if splitter_sizes and len(splitter_sizes) == 2:
                self._splitter.setSizes(splitter_sizes)

            # Restore position if the user previously moved the window
            if 'x' in state and 'y' in state:
                self._saved_x = state['x']
                self._saved_y = state['y']
                self._has_saved_position = True
        except Exception:
            pass

    def hideEvent(self, event):
        """Save state and clear input whenever the window is hidden."""
        self._save_state()
        self._chat_view._chat_input.clear()
        super().hideEvent(event)

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Handle Enter in the QuickTrans input field."""
        if obj is self._qt_input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # Allow newline
                self._on_qt_translate_clicked()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Number keys 1-9: select QuickTrans result. QuickTrans is now a
        # sub-tab of Superlookup, so "active" means outer=Superlookup AND
        # inner=QuickTrans (we look up both by widget, not by index, so the
        # check survives future tab reorderings).
        qt_active = False
        if self._superlookup_widget is not None:
            outer_idx = self._left_tabs.indexOf(self._superlookup_widget)
            if outer_idx >= 0 and self._left_tabs.currentIndex() == outer_idx:
                rtabs = getattr(self._superlookup_widget, 'results_tabs', None)
                if rtabs is not None:
                    inner_idx = rtabs.indexOf(self._quicktrans_widget)
                    if inner_idx >= 0 and rtabs.currentIndex() == inner_idx:
                        qt_active = True

        if qt_active:
            key = event.key()
            if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
                idx = key - Qt.Key.Key_1
                if 0 <= idx < self._qt_list.count():
                    item = self._qt_list.item(idx)
                    if item and item.data(Qt.ItemDataRole.UserRole):
                        self._on_qt_item_activated(item)
                        return

        # Tab switches focus between chat input and action tree
        if event.key() == Qt.Key.Key_Tab:
            if self._action_tree.hasFocus():
                self._chat_view.focus_input()
            else:
                self._action_tree.setFocus()
                if not self._action_tree.currentItem():
                    first_leaf = self._find_first_leaf(self._action_tree.invisibleRootItem())
                    if first_leaf:
                        self._action_tree.setCurrentItem(first_leaf)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _force_foreground_focus(self):
        """Force OS-level keyboard focus to this window.

        Uses the Windows AttachThreadInput + SetForegroundWindow trick.
        Necessary because some applications (notably Trados Studio)
        aggressively reclaim keyboard focus after losing it.
        """
        import sys
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = int(self.winId())
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd == hwnd:
                return  # Already foreground

            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
            our_thread = kernel32.GetCurrentThreadId()

            attached = False
            if fg_thread != our_thread:
                attached = user32.AttachThreadInput(fg_thread, our_thread, True)

            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

            if attached:
                user32.AttachThreadInput(fg_thread, our_thread, False)
        except Exception:
            pass

    @staticmethod
    def _find_first_leaf(parent: QTreeWidgetItem):
        """Find the first selectable leaf item in the tree."""
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.childCount() == 0 and (child.flags() & Qt.ItemFlag.ItemIsSelectable):
                return child
            leaf = FloatingAssistant._find_first_leaf(child)
            if leaf:
                return leaf
        return None
