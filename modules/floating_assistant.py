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

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QCursor, QKeyEvent, QFont, QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QScrollArea, QFrame, QApplication, QTreeWidget,
    QTreeWidgetItem, QAbstractItemView,
)

from modules.chat_backend import ChatBackend
from modules.chat_view_widget import ChatViewWidget
from modules.help_system import Topics as HelpTopics, set_topic as set_help_topic


class _SidekickTabPaneFilter(QObject):
    """App-level event filter: Tab jumps between the Sidekick's two panes.

    From anywhere in the **left** pane (the active tab's content), pressing
    Tab moves keyboard focus to the **right** pane's action tree (Menu).
    From the right pane, Tab moves focus back into the active left tab.

    Tab events going to text-editing widgets (QTextEdit, QPlainTextEdit,
    QLineEdit) are passed through untouched – typing 'Tab' in a chat
    input must still indent / move between fields normally.

    Only intercepts when the Sidekick window is the active window, so this
    filter doesn't bleed into Workbench's own Tab handling.
    """

    def __init__(self, sidekick):
        super().__init__(sidekick)
        self._sidekick = sidekick

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import (
            QTextEdit, QPlainTextEdit, QLineEdit, QApplication,
        )

        if event.type() != QEvent.Type.KeyPress:
            return False
        if event.key() != Qt.Key.Key_Tab and event.key() != Qt.Key.Key_Backtab:
            return False
        # Only Tab without modifiers (Shift+Tab is Backtab – also handled
        # below as the reverse direction). Ignore Ctrl+Tab – that's the
        # tab-cycling shortcut, handled separately by QShortcut.
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.AltModifier
                   | Qt.KeyboardModifier.MetaModifier):
            return False

        sk = self._sidekick
        if sk is None or not sk.isActiveWindow():
            return False

        focus = QApplication.focusWidget()
        if focus is None:
            return False
        # Pass Tab through if focus is on a real text-editing widget so
        # users can still indent / traverse form fields normally.
        if isinstance(focus, (QTextEdit, QPlainTextEdit, QLineEdit)):
            return False

        action_tree = getattr(sk, '_action_tree', None)
        if action_tree is None:
            return False

        # Determine current pane by walking up the focus widget's ancestors.
        in_action_tree = False
        w = focus
        while w is not None:
            if w is action_tree:
                in_action_tree = True
                break
            w = w.parent()

        if in_action_tree:
            # On the right pane → jump back to the left.
            sk._focus_left_pane()
        else:
            # Otherwise (left pane or anywhere else inside Sidekick) → jump
            # to the right action tree.
            sk._focus_action_tree()
        return True


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
        # Source window handle – captured when the assistant opens via global hotkey
        self._source_window = None

        # Geometry persistence
        user_data = getattr(parent_app, 'user_data_path', None)
        if user_data:
            self._state_file = Path(user_data) / "workbench" / "assistant_geometry.json"
        else:
            self._state_file = None

        # ``Tool`` window (NOT always-on-top): behaves like any other app
        # window when visible – clicking a different program brings that
        # program to the front – but the Tool style means Windows does NOT
        # allocate a taskbar slot for it. That has two consequences:
        #
        #  1. Sidekick is invisible whenever it's hidden – no taskbar icon,
        #     no Alt+Tab entry, no system tray entry. Pure summon-on-demand.
        #  2. Showing it never adds a taskbar slot, so the taskbar (and the
        #     system tray icons sharing its right edge) doesn't reflow – no
        #     visible "bounce" of the tray icons every time you press Alt+K.
        #
        # Trade-off accepted: you can't click a taskbar icon to bring
        # Sidekick back. Use Alt+K (global) or Ctrl+Q (in-app) instead.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(500, 350)
        self.resize(850, 520)

        # Window icon (taskbar / alt-tab) – canonical Sv mark, same file the
        # main Workbench window uses.
        self._apply_app_icon()

        self._init_ui()
        self._restore_state()

        # Global Escape shortcut – works regardless of which child has focus
        from PyQt6.QtGui import QShortcut, QKeySequence
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        esc_shortcut.activated.connect(self._dismiss_to_tray)

        # Ctrl+Tab / Ctrl+Shift+Tab cycle through the Sidekick's left tabs
        # (Chat → SuperLookup → Clipboard → AutoFingers → wrap). Standard
        # Qt convention; matches what users expect from any tabbed app.
        next_tab_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_sc.setContext(Qt.ShortcutContext.WindowShortcut)
        next_tab_sc.activated.connect(self._cycle_tab_forward)
        prev_tab_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_sc.setContext(Qt.ShortcutContext.WindowShortcut)
        prev_tab_sc.activated.connect(self._cycle_tab_backward)

        # Tab as pane-switcher (left tab content ↔ right action menu).
        # Implemented as an app-event filter rather than a QShortcut so we
        # can let Tab through to text-editing widgets (chat input,
        # search fields, etc.) where Tab has its normal meaning.
        from PyQt6.QtWidgets import QApplication
        self._tab_pane_switch_filter = _SidekickTabPaneFilter(self)
        QApplication.instance().installEventFilter(self._tab_pane_switch_filter)

        # Track last-focused widget in the left pane so Left/Tab from the
        # right-pane Menu can return the user to exactly where they were.
        self._last_left_pane_focus = None
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # When the user clicks Send in the chat, the LLM round-trip blocks
        # the GUI thread for several seconds. Windows' Desktop Window Manager
        # treats the frozen Tool window as "Not Responding" and creates a
        # ghost copy; once the call returns, the original is sometimes left
        # hidden or pushed behind Trados even though Qt thinks it's visible.
        # Users then have to press Alt+K again just to see the response.
        # Re-raise + re-activate the window when the LLM call finishes so
        # the response is visible without an extra summon. Idempotent if the
        # window is already on top.
        self._backend.thinking_finished.connect(self._restore_to_foreground_after_llm)

        # Sidekick Bridge server – inverse of the Trados-side bridge. Lets
        # the Trados plugin POST a QuickLauncher prompt here for Sidekick
        # to run, when the user has set their plugin preference to route
        # QuickLauncher to Workbench rather than the in-Trados Assistant.
        # See modules/sidekick_bridge_server.py for the wire format.
        self._bridge_server = None
        try:
            from modules.sidekick_bridge_server import SidekickBridgeServer
            self._bridge_server = SidekickBridgeServer(self)
            self._bridge_server.run_prompt_requested.connect(self._on_bridge_prompt_request)
            self._bridge_server.start()
            QApplication.instance().aboutToQuit.connect(self._bridge_server.stop)
        except Exception as e:
            print(f"[FloatingAssistant] Sidekick bridge server failed to start: {e}")


    def _dismiss_to_tray(self):
        """Hide Sidekick completely – Tool-style windows have no taskbar
        slot, so hiding doesn't cause a slot to be deallocated, and the
        next summon doesn't cause one to be allocated. No taskbar reflow,
        no system-tray-icon bounce. The method name is kept for symmetry
        with how it's wired up across dismiss paths (Esc, paste-and-return,
        Ctrl+Q toggle).
        """
        self.hide()

    def _on_bridge_prompt_request(self, expanded: str, display_prompt: str, prompt_name: str):
        """Handle a QuickLauncher prompt forwarded by the Trados plugin.

        Connected via Qt::QueuedConnection (cross-thread emit from the
        bridge's HTTP handler thread) so this always runs on the GUI
        thread. We:

          1. Show / raise / activate Sidekick so the user sees the chat.
          2. Switch to the Chat tab.
          3. Echo the display version of the prompt as a "user" message
             (the Trados plugin builds a redacted display version – e.g.
             "[source document — N segments]" instead of the full project
             text – so the chat doesn't get spammed with kilobytes of
             context the LLM needs but the user has already seen).
          4. Send the fully-expanded prompt to the LLM directly via
             ``ChatBackend.send_ai_request``. We bypass the chat view's
             ``_context_aware_send`` override because the Trados side has
             already done all the context substitution; running it again
             would prepend the *Workbench's* idea of the active context,
             which would be wrong for a Trados-originated prompt.

        The thinking_finished hook installed in __init__ then re-raises
        the window after the synchronous LLM call returns, in case
        Windows DWM ghosted it during the freeze.
        """
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

        try:
            if hasattr(self, '_left_tabs'):
                self._left_tabs.setCurrentIndex(0)  # Chat tab
        except Exception:
            pass

        label = f"[{prompt_name}] " if prompt_name else ""
        self._backend.add_message("user", label + (display_prompt or expanded))

        system_prompt = "You are an AI assistant. Follow the instructions precisely."
        try:
            response, metadata = self._backend.send_ai_request(expanded, system_prompt)
            if response and response.strip():
                self._backend.add_message("assistant", response, metadata=metadata)
            else:
                self._backend.add_message("system", "⚠ No response received.")
        except Exception as e:
            self._backend.add_message("system", f"⚠ Error: {e}")

    def _restore_to_foreground_after_llm(self):
        """Pull Sidekick back to the foreground after the synchronous LLM
        round-trip returns. Wired to ChatBackend.thinking_finished.

        The synchronous send_ai_request blocks the GUI thread for several
        seconds. Windows DWM treats the frozen Tool window as Not Responding
        and creates a ghost copy; once the call returns, the original is
        sometimes left hidden or pushed behind Trados even though Qt's
        isVisible() still reports True. Users see Sidekick disappear "right
        before the response arrives" and have to press Alt+K again just to
        read it. Calling show() + raise_() + activateWindow() unconditionally
        is harmless when the window is already on top, and reliably restores
        it when DWM ghosted it.

        Skipped when the user has explicitly dismissed Sidekick (isVisible()
        returns False because we hid it via _dismiss_to_tray) – the user
        clearly wanted it gone, so don't pop it back up just because a
        background response arrived.
        """
        if not self.isVisible():
            return
        self.show()
        self.raise_()
        self.activateWindow()

    def _cycle_tab_forward(self):
        """Ctrl+Tab – advance to the next Sidekick tab, wrapping at the end."""
        if not hasattr(self, '_left_tabs'):
            return
        count = self._left_tabs.count()
        if count <= 1:
            return
        idx = (self._left_tabs.currentIndex() + 1) % count
        self._left_tabs.setCurrentIndex(idx)

    def _cycle_tab_backward(self):
        """Ctrl+Shift+Tab – go to the previous Sidekick tab, wrapping."""
        if not hasattr(self, '_left_tabs'):
            return
        count = self._left_tabs.count()
        if count <= 1:
            return
        idx = (self._left_tabs.currentIndex() - 1) % count
        self._left_tabs.setCurrentIndex(idx)

    def _focus_action_tree(self):
        """Move keyboard focus to the right-pane action tree (Menu)."""
        tree = getattr(self, '_action_tree', None)
        if tree is None:
            return
        tree.setFocus(Qt.FocusReason.TabFocusReason)
        # If nothing's selected yet, land on the first row so arrow keys
        # work immediately.
        if tree.currentItem() is None and tree.topLevelItemCount() > 0:
            tree.setCurrentItem(tree.topLevelItem(0))

    def _focus_left_pane(self):
        """Move keyboard focus back into the left pane.

        Prefers whichever widget last held focus there (e.g. the clipboard
        image list, if that's where the user pressed Right from), so
        Left/Tab from the right-pane Menu returns them to the same spot
        they came from. Falls back to the active tab's main widget if no
        previous left-pane focus is remembered.
        """
        last = getattr(self, '_last_left_pane_focus', None)
        if last is not None:
            try:
                if last.isVisible() and last.isEnabled():
                    last.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except RuntimeError:
                # Widget was deleted out from under us – fall through.
                self._last_left_pane_focus = None

        if not hasattr(self, '_left_tabs'):
            return
        widget = self._left_tabs.currentWidget()
        if widget is None:
            return
        widget.setFocus(Qt.FocusReason.TabFocusReason)

    # Header styles for the focus indicator. The "active" variant has the
    # accent blue + bottom underline; the inactive variant is muted.
    _FOCUS_STYLE_ACTIVE = (
        "font-weight: bold; font-size: 10pt; color: #1976D2; "
        "border: none; border-bottom: 2px solid #1976D2; "
        "padding: 0 6px 2px 6px;"
    )
    _FOCUS_STYLE_INACTIVE = (
        "font-weight: bold; font-size: 10pt; color: #3D5A80; "
        "border: none; padding-left: 6px;"
    )

    def _on_focus_changed(self, _old, new):
        """Track the most recently focused widget in the left pane so the
        right-pane Menu can return there with Left or Tab. Also refreshes
        the visual focus indicators on region headers (Menu / Text snippets
        / Images) so the user can see at a glance which area they're in.
        """
        if new is None:
            self._refresh_focus_styles(menu_active=False)
            return
        try:
            # Skip if the new focus is outside Sidekick.
            if not self.isAncestorOf(new):
                self._refresh_focus_styles(menu_active=False)
                return
            # Skip remembering if the new focus is the action tree (or one of
            # its descendants). We want to remember LEFT-pane focus only.
            tree = getattr(self, '_action_tree', None)
            in_action_tree = False
            if tree is not None:
                w = new
                while w is not None:
                    if w is tree:
                        in_action_tree = True
                        break
                    w = w.parent()
            if not in_action_tree:
                self._last_left_pane_focus = new
            self._refresh_focus_styles(menu_active=in_action_tree, focused=new)
        except RuntimeError:
            pass

    def _refresh_focus_styles(self, *, menu_active: bool, focused=None):
        """Update header colours so the user can see which region has
        keyboard focus: the right-pane Menu (action tree), or one of the
        clipboard columns inside the active tab."""
        # Right-pane Menu header
        hdr = getattr(self, '_action_header', None)
        if hdr is not None:
            hdr.setStyleSheet(
                self._FOCUS_STYLE_ACTIVE if menu_active
                else self._FOCUS_STYLE_INACTIVE
            )
        # Forward to the clipboard widget so its column headers update too.
        cb = getattr(self, '_clipboard_widget', None)
        if cb is not None and hasattr(cb, '_refresh_focus_styles'):
            try:
                cb._refresh_focus_styles(focused)
            except Exception:
                pass

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

        # Right-click on any tab → "Open here by default"
        self._left_tabs.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._left_tabs.tabBar().customContextMenuRequested.connect(
            self._on_tabbar_context_menu
        )

        # Chat tab
        self._chat_view = ChatViewWidget(
            self._backend,
            compact=True,
            show_autoprompt=False,
        )
        if hasattr(self._parent_app, 'prompt_manager_qt'):
            self._chat_view._do_send = self._parent_app.prompt_manager_qt._context_aware_send
        self._left_tabs.addTab(self._chat_view, "\U0001F4AC Chat")

        # QuickTrans widget – constructed here (so all self._qt_* state is
        # initialised) but NOT added to _left_tabs. It's reparented into the
        # Superlookup results_tabs as a sub-tab (after Termbases) once the
        # Superlookup widget is lazy-created in _ensure_superlookup_tab().
        self._quicktrans_widget = self._create_quicktrans_tab()
        self._quicktrans_embedded_in_superlookup = False

        # Superlookup tab – deferred until first show to avoid init-order
        # issues (the main window's database/termbase managers may not be
        # fully wired when the FloatingAssistant is first constructed).
        self._superlookup_widget = None
        self._superlookup_tab_added = False

        # Clipboard tab – widget created eagerly so monitoring starts immediately,
        # but not added to _left_tabs until _ensure_superlookup_tab() runs (so
        # the tab order stays Chat → SuperLookup → Clipboard).
        self._clipboard_widget = self._create_clipboard_tab()
        set_help_topic(self._clipboard_widget, HelpTopics.CLIPBOARD)
        self._clipboard_tab_added = False

        # AutoFingers tab – voice commands + dictation. Lazy because it relies on
        # parent_app.voice_command_manager and other attrs that may not be
        # ready when the FloatingAssistant is first constructed.
        self._autofingers_widget = None
        self._autofingers_tab_added = False

        # F1 from anywhere in Sidekick that has no more specific topic → overview
        set_help_topic(self, HelpTopics.SIDEKICK)

        left_layout.addWidget(self._left_tabs)
        self._splitter.addWidget(left_panel)

        # Action panel (right)
        action_panel = self._create_action_panel()
        self._splitter.addWidget(action_panel)

        self._splitter.setSizes([520, 280])
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        outer_layout.addWidget(self._splitter, 1)

        # Context-aware info bar – shows a short tip depending on the active tab
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
        # Keep the un-scoped `QWidget { ... }` selector – scoping via object
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

        # Sv icon – canonical Workbench brand mark, native 24×24 (no scaling).
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

        # Settings (gear) – opens Workbench Settings tab
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

        self._action_header = QLabel("Menu")
        self._action_header.setStyleSheet(self._FOCUS_STYLE_INACTIVE)
        panel_layout.addWidget(self._action_header)

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
        # Left arrow on the action tree → return focus to the previous
        # left-pane widget (e.g. the clipboard image list the user came
        # from). Installed as an event filter so we can pass through to
        # Qt's default Left-collapses-tree-node behaviour when the user is
        # somewhere it would do something useful.
        self._action_tree.installEventFilter(self)

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
        # Mark as category – keep selectable for keyboard highlight
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
        """Slot for itemExpanded / itemCollapsed – update indicators."""
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

        # -- Tools --
        # QuickTrans is no longer a separate menu entry: it's the first
        # sub-tab inside SuperLookup, so clicking "SuperLookup" lands on it
        # automatically. Leaving only one entry here keeps the menu tidy.
        tools_cat = self._make_category("\U0001F6E0 Tools", expanded=True)
        self._add_tree_action(tools_cat, "\U0001F50D SuperLookup", self._on_superlookup)
        self._add_tree_action(tools_cat, "\U0001F4CB Clipboard", self._on_clipboard)
        self._add_tree_action(tools_cat, "\U0001F3A4 AutoFingers", self._on_autofingers)

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

        # 2. Get the assistant window out of the user's way (minimized so
        #    the taskbar entry stays – see _dismiss_to_tray).
        self._dismiss_to_tray()

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

    def _paste_pixmap_and_return(self, pixmap):
        """Like _paste_and_return but for an image (QPixmap).

        Most apps that accept clipboard images respond to Ctrl+V the same way
        they do for text, so the activate-source + send-paste sequence is
        identical – only the clipboard payload differs.
        """
        from PyQt6.QtCore import QTimer

        QApplication.clipboard().setPixmap(pixmap)
        self._dismiss_to_tray()

        def _do_paste():
            try:
                from modules.platform_helpers import (
                    activate_foreground_window, CrossPlatformKeySender
                )
                if self._source_window:
                    activate_foreground_window(self._source_window)

                import time
                time.sleep(0.15)

                sender = CrossPlatformKeySender()
                sender.send_paste()
            except Exception as e:
                print(f"[FloatingAssistant] Paste-pixmap-and-return error: {e}")

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
        # tab, inner sub-tab index 2 – after Termbases). Make sure Superlookup
        # is lazy-built (this also re-parents QuickTrans into its results_tabs
        # on first call), then switch the outer tab to Superlookup and the
        # inner tab to QuickTrans.
        self._ensure_superlookup_tab()

        # Outer: find Superlookup tab index (it's dynamic – Chat + possibly
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
        """Handle single-click – expand categories, run leaf actions."""
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
        populated QuickTrans sub-tab with translations already loading –
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
            # fetches immediately – matches what Ctrl+Alt+Q does, so the
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
        2: "Clipboard history – click any item to paste it; pasted items are shown in grey",
        3: "AutoFingers – voice commands and dictation; toggle Always-On to listen continuously across all apps",
    }

    def _update_info_label(self, index):
        self._info_label.setText(self._TAB_INFO.get(index, ""))

    # ------------------------------------------------------------------
    # Clipboard tab
    # ------------------------------------------------------------------

    def _create_clipboard_tab(self) -> QWidget:
        from modules.clipboard_manager_widget import ClipboardManagerWidget
        return ClipboardManagerWidget(
            self._parent_app,
            paste_text_callback=self._paste_and_return,
            paste_image_callback=self._paste_pixmap_and_return,
        )

    def _ensure_clipboard_tab(self):
        """Add the Clipboard tab to _left_tabs on first call (guarded)."""
        if self._clipboard_tab_added:
            return
        self._clipboard_tab_added = True
        self._left_tabs.addTab(self._clipboard_widget, "\U0001F4CB Clipboard")
        # Load persisted history now that db_manager is ready
        self._clipboard_widget.ensure_db_loaded()

    def _ensure_autofingers_tab(self):
        """Add the AutoFingers tab on first call (guarded). Always added last so
        the tab order stays Chat → SuperLookup → Clipboard → AutoFingers."""
        if self._autofingers_tab_added:
            return
        try:
            from modules.autofingers_tab import AutoFingersTab
            self._autofingers_widget = AutoFingersTab(self._parent_app)
            self._autofingers_tab_added = True
            self._left_tabs.addTab(self._autofingers_widget, "\U0001F3A4 AutoFingers")
        except Exception as e:
            import traceback
            traceback.print_exc()
            log = getattr(self._parent_app, 'log', None)
            if log:
                log(f"⚠ FloatingAssistant: Could not load AutoFingers tab: {e}")

    def _open_to_clipboard(self, source_window=None):
        """Open the Sidekick directly to the Clipboard tab and focus the list."""
        from PyQt6.QtCore import QTimer
        self._ensure_superlookup_tab()
        self._ensure_clipboard_tab()
        idx = self._left_tabs.indexOf(self._clipboard_widget)
        self.show_at_cursor(start_tab=idx if idx >= 0 else None,
                            source_window=source_window)
        # Defer focus so the window is fully shown before we steal it
        QTimer.singleShot(50, self._focus_clipboard_list)

    def _focus_clipboard_list(self):
        """Give keyboard focus to the clipboard's text list (the default
        column). The user can switch to the image list with Right arrow."""
        if not (hasattr(self, '_clipboard_widget') and self._clipboard_tab_added):
            return
        lst = getattr(self._clipboard_widget, '_text_list', None)
        if lst is None:
            return
        lst.setFocus()
        if lst.count() > 0 and lst.currentRow() < 0:
            lst.setCurrentRow(0)

    def _on_clipboard(self):
        """Action-panel handler: show the Clipboard tab."""
        self._open_to_clipboard()

    # ------------------------------------------------------------------
    # AutoFingers action
    # ------------------------------------------------------------------

    def _open_to_autofingers(self, source_window=None):
        """Open the Sidekick directly to the AutoFingers tab."""
        self._ensure_superlookup_tab()
        self._ensure_autofingers_tab()
        idx = self._left_tabs.indexOf(self._autofingers_widget) if self._autofingers_widget else -1
        self.show_at_cursor(start_tab=idx if idx >= 0 else None,
                            source_window=source_window)

    def _on_autofingers(self):
        """Action-panel handler: show the AutoFingers tab."""
        self._open_to_autofingers()

    # ------------------------------------------------------------------
    # Default-tab preference (right-click on tab bar)
    # ------------------------------------------------------------------

    def _on_tabbar_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        tab_idx = self._left_tabs.tabBar().tabAt(pos)
        if tab_idx < 0:
            return
        tab_name = self._left_tabs.tabText(tab_idx).strip()
        menu = QMenu(self)
        if self._default_tab == tab_idx:
            action = menu.addAction(f"✓ ‘{tab_name}’ is the default tab")
            action.setEnabled(False)
        else:
            action = menu.addAction(f"Open to ‘{tab_name}’ by default")
            action.triggered.connect(lambda: self._set_default_tab(tab_idx))
        menu.exec(self._left_tabs.tabBar().mapToGlobal(pos))

    def _set_default_tab(self, idx: int):
        self._default_tab = idx
        self._save_state()

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

        # Clipboard tab always goes after SuperLookup
        self._ensure_clipboard_tab()
        # AutoFingers tab always goes last
        self._ensure_autofingers_tab()

    # ------------------------------------------------------------------
    # Show / toggle
    # ------------------------------------------------------------------

    def show_at_cursor(self, captured_text=None, focus_actions=False,
                       source_window=None, start_tab=None):
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
            start_tab: Tab index to open on. Falls back to self._default_tab,
                       then 0 (Chat) if not set.
        """
        self._source_window = source_window

        self._ensure_superlookup_tab()
        tab_to_open = start_tab if start_tab is not None else self._default_tab
        self._left_tabs.setCurrentIndex(tab_to_open)

        # Clear the chat input unless we're opening to a non-chat tab
        if tab_to_open == 0:
            self._chat_view._chat_input.clear()
        if captured_text:
            self._chat_view.insert_text(captured_text)

        # Detect if the target tab is the clipboard tab – its list should
        # always own focus when shown, regardless of focus_actions.
        clipboard_idx = (
            self._left_tabs.indexOf(self._clipboard_widget)
            if (hasattr(self, '_clipboard_widget') and self._clipboard_tab_added)
            else -1
        )
        is_clipboard_tab = (clipboard_idx >= 0 and tab_to_open == clipboard_idx)

        # If already visible, just switch tab and bring to front.
        if self.isVisible():
            self.raise_()
            self.activateWindow()
            self._force_foreground_focus()
            if is_clipboard_tab:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, self._focus_clipboard_list)
            elif focus_actions:
                self._action_tree.setFocus()
            elif tab_to_open == 0:
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
                # Saved position is off-screen (monitor removed?) – fall
                # back to the screen under the cursor.
                screen = QApplication.screenAt(QCursor.pos()) \
                    or QApplication.primaryScreen()
        else:
            # First launch – open on the screen where the cursor currently is
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

        if is_clipboard_tab:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, self._focus_clipboard_list)
        elif focus_actions:
            self._action_tree.setFocus()
            first_leaf = self._find_first_leaf(self._action_tree.invisibleRootItem())
            if first_leaf:
                self._action_tree.setCurrentItem(first_leaf)
        elif tab_to_open == 0:
            self._chat_view.focus_input()

    def toggle(self, captured_text=None):
        """Toggle visibility (used by local Ctrl+Q).

        If the window is visible but buried behind other windows,
        bring it to the foreground instead of hiding it.
        """
        if self.isVisible():
            if self.isActiveWindow():
                self._dismiss_to_tray()
            else:
                # Visible but not in front – bring to foreground
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
        should fill that monitor – not jump back to the primary display.
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
        """Save window size, position, splitter proportions, and default tab."""
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
                'default_tab': self._default_tab,
            }
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _restore_state(self):
        """Restore saved window size, splitter proportions, position, and default tab."""
        self._has_saved_position = False
        self._default_tab = 0

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

            self._default_tab = state.get('default_tab', 0)
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
        """Handle Enter in the QuickTrans input field, and Left on the
        right-pane action tree (returns focus to the left pane)."""
        if obj is self._qt_input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # Allow newline
                self._on_qt_translate_clicked()
                return True

        # Left arrow on the action tree: jump focus back to the previous
        # left-pane widget (e.g. the clipboard image list). Only intercept
        # when Qt's default Left would do nothing useful – i.e. the
        # current item is a top-level row that's not expanded – so tree
        # navigation (collapse expanded categories, move from leaf to
        # parent) still works as normal.
        if (obj is getattr(self, '_action_tree', None)
                and event.type() == event.Type.KeyPress
                and event.key() == Qt.Key.Key_Left
                and not event.modifiers()):
            current = self._action_tree.currentItem()
            if current is None:
                # Empty tree (shouldn't happen, but be safe).
                self._focus_left_pane()
                return True
            at_top = current.parent() is None
            if at_top and not current.isExpanded():
                self._focus_left_pane()
                return True
            # Otherwise let Qt collapse / move-to-parent.

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

        Tries a plain ``SetForegroundWindow`` first – that suffices when
        the call is happening in response to a registered global hotkey
        (Windows briefly grants the receiving process foreground rights),
        and avoids the Windows shell side effect of ``AttachThreadInput``
        which on Windows 11 manifests as a visible bounce of the system
        tray icons every time Sidekick is summoned.

        Falls back to the AttachThreadInput + SetForegroundWindow trick
        only if the plain call doesn't actually move us to the foreground –
        e.g. when invoked from a context where Windows hasn't granted
        foreground permission and another app (notably Trados Studio)
        would otherwise reclaim focus.
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

            # First attempt: plain SetForegroundWindow. Quiet – no shell
            # broadcast, no tray bounce.
            user32.SetForegroundWindow(hwnd)
            if user32.GetForegroundWindow() == hwnd:
                return

            # Fallback: aggressive thread-input attachment. Only reaches
            # here when plain activation was rejected by Windows' focus-
            # stealing prevention (rare for hotkey-driven summons since
            # the hotkey grants foreground rights).
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
