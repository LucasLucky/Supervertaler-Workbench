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

    def __init__(self, chat_backend: ChatBackend, parent_app, parent=None):
        super().__init__(parent)
        self._backend = chat_backend
        self._parent_app = parent_app
        self._drag_pos = None

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

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(500, 350)
        self.resize(850, 520)

        self._init_ui()
        self._restore_state()

        # Global Escape shortcut — works regardless of which child has focus
        from PyQt6.QtGui import QShortcut, QKeySequence
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        esc_shortcut.activated.connect(self.hide)

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

        # Content: splitter with chat (left) + actions (right)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setChildrenCollapsible(False)

        # Chat view
        self._chat_view = ChatViewWidget(
            self._backend,
            compact=True,
            show_autoprompt=False,
        )
        if hasattr(self._parent_app, 'prompt_manager_qt'):
            self._chat_view._do_send = self._parent_app.prompt_manager_qt._context_aware_send
        self._splitter.addWidget(self._chat_view)

        # Action panel
        action_panel = self._create_action_panel()
        self._splitter.addWidget(action_panel)

        self._splitter.setSizes([520, 280])
        self._splitter.setStretchFactor(0, 1)   # chat stretches
        self._splitter.setStretchFactor(1, 0)   # actions keep size
        outer_layout.addWidget(self._splitter, 1)

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
        bar.setFixedHeight(36)
        bar.setStyleSheet("""
            QWidget {
                background-color: #3D5A80;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
            }
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        title = QLabel("Supervertaler Assistant")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 10pt; border: none;")
        layout.addWidget(title)
        layout.addStretch()

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
        tools_cat = self._make_category("\U0001F6E0 Workbench Tools", expanded=True)
        self._add_tree_action(tools_cat, "\u26A1 QuickTrans", self._on_quicktrans)
        self._add_tree_action(tools_cat, "\U0001F50D Superlookup", self._on_superlookup)

        # -- Prompt library items (grouped by folder) --
        self._populate_prompt_library_tree()

        # -- Snippets: Special Characters --
        chars_cat = self._make_category("\u2728 Special Characters")
        self._add_snippet(chars_cat, "Misc symbols", "\u25A3 \u25A0 \u25A1 \u25A2 \u25EF \u25B2 \u25B6 \u25BA \u25BC \u25C6 \u25E2 \u25E3 \u25E4 \u25E5")
        self._add_snippet(chars_cat, "Arrows", "\u2190 \u2192 \u2191 \u2193 \u27EB \u2B07 \u2B06 \u21C4 \u2194")
        self._add_snippet(chars_cat, "Primes \u2032\u2033\u2034", "\u2032 \u2033 \u2034 \u2057")
        self._add_snippet(chars_cat, "Dashes & quotes", "\u2013 \u2014 \u00AB \u00BB \u2039 \u203A \u201C \u201D \u201E \u201A")
        self._add_snippet(chars_cat, "Currency \u20AC \u00A3 \u00A5", "\u00A5 \u20AC $ \u00A2 \u00A3")
        self._add_snippet(chars_cat, "Legal \u00A9 \u00AE \u2122", "\u00A9 \u00AE @ \u2122 \u00B0 \u2030")
        self._add_snippet(chars_cat, "Maths \u00B1 \u00D7 \u00F7 \u2260", "\u00B1 \u00D7 ~ \u2248 \u00F7 \u2260 \u03C0 \u221E")
        self._add_snippet(chars_cat, "Bullets \u2022 \u25CF \u00B7", "\u2026 \u00B7 \u2022 \u25CF")
        self._add_snippet(chars_cat, "\u00EB", "\u00EB")
        self._add_snippet(chars_cat, "\u25B6", "\u25B6")

        # -- Snippets: Personal --
        personal_cat = self._make_category("\U0001F4C7 Personal Snippets")
        self._add_snippet(personal_cat, "Mobile number", "07475771720")

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

        # Use the external-mode QuickTrans (works without grid context)
        lookup_tab = self._get_lookup_tab()
        if lookup_tab and hasattr(lookup_tab, 'show_mt_quick_lookup_from_ahk'):
            self.hide()
            lookup_tab.show_mt_quick_lookup_from_ahk(text)
        elif hasattr(self._parent_app, 'show_mt_quick_popup'):
            self._parent_app.show_mt_quick_popup(text_override=text)
        else:
            self._backend.add_message("system", "\u26A0 QuickTrans not available.")

    def _on_superlookup(self):
        text = self._get_action_text()
        if not text:
            self._backend.add_message("system", "\u26A0 No text available. Type or select text first.")
            return

        self.hide()

        # Use the main window's show_superlookup path directly
        mw = self._parent_app
        lookup_tab = getattr(mw, 'lookup_tab', None)
        if lookup_tab and hasattr(lookup_tab, 'show_superlookup'):
            # Bring main window to foreground
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

            lookup_tab.show_superlookup(text)
        else:
            self._backend.add_message("system", "\u26A0 Superlookup not available.")

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
            # Reopen where the user last left it, clamped to screen bounds
            x, y = self._saved_x, self._saved_y
            screen = QApplication.screenAt(QCursor.pos())
            if screen:
                geom = screen.availableGeometry()
                x = max(geom.left(), min(x, geom.right() - self.width()))
                y = max(geom.top(), min(y, geom.bottom() - self.height()))
        else:
            # First launch — centre on the primary monitor
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                x = geom.left() + (geom.width() - self.width()) // 2
                y = geom.top() + (geom.height() - self.height()) // 2
            else:
                x = 200
                y = 200

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

    def keyPressEvent(self, event):
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
