"""
termlens_popup.py
─────────────────

Borderless top-most popup that mirrors the docked TermLens panel for the
active segment. Triggered by a lone Ctrl tap (previously the numbered
"Insert term or non-translatable" list — replaced in v1.10.87 to match
the Trados plugin's TermLens popup parity).

Lifecycle
─────────
Opened via ``Supervertaler.show_term_insert_popup()``. The popup hosts a
fresh ``TermLensWidget`` configured for popup mode (zoomer / refresh
button / info label hidden, tighter margins). The wrapper layers the
keyboard cycle and auto-close behaviour on top — the chip rendering
itself is unchanged from the docked panel, so colours / synonyms /
metadata indicators / hover popups all behave identically by virtue of
running through the same ``TermBlock`` code path.

Keyboard
────────
- Right / Down / Tab          → next chip (wraps)
- Left / Up / Shift+Tab       → previous chip
- 1-9, Alt+1-9                → directly insert chip N (same numbering
                                as the docked panel's Alt-shortcut)
- Enter                       → insert currently-highlighted chip
- E                           → open editor for the highlighted chip
- I                           → toggle the sticky metadata popup
- Esc                         → close
- Anything else not in this set → close (with a carve-out for pure
                                  modifier presses so the Ctrl-release
                                  that opens the popup doesn't close it
                                  on the way in)

Auto-close
──────────
- Mouse moves > 4 px from its position when the popup appeared → close.
  Polled every 75 ms via QTimer; cheap and avoids a Win32 mouse hook.
- Focus loss (clicking outside, alt-tabbing) → close. Suppressed during
  deliberate sub-form transitions (edit dialog, sticky metadata popup)
  to keep their close-paths from racing each other.

Insertion guarantee
───────────────────
A single-flight guard prevents double-insertion when both a chip click
and a keyboard Enter race for the same target. The first to call
``_request_insert`` wins; the actual insertion happens after ``close()``
so focus is back in the editor by the time the text is typed in.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Union

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)


# Type alias for the block widgets the TermLensWidget renders. We import
# lazily inside the methods that need isinstance checks to avoid a
# circular import (termlens_widget.py is a heavy module and this popup
# is constructed late in the lifecycle).


class TermLensPopup(QFrame):
    """Floating popup that wraps a TermLensWidget for keyboard insertion.

    Caller responsibilities (typically ``Supervertaler.show_term_insert_popup``):
      - Construct with the segment's source text + termbase / NT matches.
      - Pass a ``host_widget`` argument so right-click / context menus
        and the metadata popup can resolve a sensible parent.
      - Connect ``term_inserted``, ``edit_requested`` signals before show().
      - Call ``show()`` then ``setFocus()`` — keyboard events drive everything.
    """

    # ── Signals ──────────────────────────────────────────────────────────

    # Emitted when a chip is committed (click, Enter, or 1-9 hotkey).
    # The string is the exact target_term to insert into the editor.
    term_inserted = pyqtSignal(str)

    # Emitted when the user presses E on a chip; the popup closes first
    # so the receiving edit dialog isn't covered.
    edit_requested = pyqtSignal(int, int)

    # ── Implementation ───────────────────────────────────────────────────

    def __init__(
        self,
        source_text: str,
        termbase_matches: List[dict],
        nt_matches: Optional[List[dict]] = None,
        host_widget: Optional[QWidget] = None,
        theme_manager=None,
        db_manager=None,
        log_callback: Optional[Callable[[str], None]] = None,
        font_family: str = "Segoe UI",
        font_size: int = 10,
        font_bold: bool = False,
    ):
        # Frameless Dialog: takes keyboard focus on show() (Tool doesn't
        # activate on Windows, which is why v1.10.87 had broken arrow-key
        # navigation — keystrokes went to the segment-grid behind the
        # popup instead). Dialog auto-activates and accepts focus events.
        # Popup window flag would auto-close on any outside click, which
        # we DON'T want because clicking the metadata sticky popup would
        # close us; the metadata popup uses ToolTip flags so it doesn't
        # take focus, and we close ourselves on window-deactivate instead.
        super().__init__(
            host_widget,
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # The popup itself MUST be the focus target — otherwise key
        # events bubble to whichever child happens to be focusable
        # first and our keyPressEvent never fires. StrongFocus on the
        # popup + Click focus on the inner widget keeps the popup
        # as the keyboard target while still letting chip clicks work.

        self._host_widget = host_widget
        self._theme_manager = theme_manager

        # ── State ──────────────────────────────────────────────────────
        # Index of the currently-highlighted chip (set_current(True) on
        # one block at a time). -1 = nothing highlighted (e.g. empty
        # segment).
        self._current_index = -1
        # Single-flight insert / edit guard. Both deferred until
        # closeEvent so the host receives them after focus is back.
        self._pending_insert: Optional[str] = None
        self._pending_edit: Optional[tuple] = None
        # While True, OnFocusOut won't close us (we're deliberately
        # showing a sub-form like the edit dialog or sticky popup).
        self._suppress_focus_close = False
        # Auto-close cursor baseline.
        self._initial_cursor_pos: Optional[QPoint] = None
        self._auto_close_timer: Optional[QTimer] = None

        # ── Build UI ───────────────────────────────────────────────────
        self._build_ui(
            source_text=source_text,
            termbase_matches=termbase_matches,
            nt_matches=nt_matches or [],
            db_manager=db_manager,
            log_callback=log_callback,
            font_family=font_family,
            font_size=font_size,
            font_bold=font_bold,
        )
        self._position_near_cursor()

    # ── Construction ─────────────────────────────────────────────────────

    def _build_ui(
        self,
        source_text: str,
        termbase_matches: List[dict],
        nt_matches: List[dict],
        db_manager,
        log_callback,
        font_family: str,
        font_size: int,
        font_bold: bool,
    ):
        # Defer the heavy import to method scope to avoid pulling
        # termlens_widget at module-load time.
        from modules.termlens_widget import TermLensWidget

        # Frame styling: thin grey border, white card.
        self.setStyleSheet(
            """
            TermLensPopup {
                background: white;
                border: 1px solid #BDBDBD;
                border-radius: 6px;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # Inner card surface (so the 1-px QFrame border is the only
        # outer line and the card padding is uniform).
        card = QWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 4, 6, 2)
        card_layout.setSpacing(2)
        outer.addWidget(card)

        # ── Embedded TermLens ─────────────────────────────────────────
        self._inner = TermLensWidget(
            parent=card,
            db_manager=db_manager,
            log_callback=log_callback,
            theme_manager=self._theme_manager,
        )
        self._inner.set_font_settings(
            font_family=font_family,
            font_size=font_size,
            bold=font_bold,
        )
        self._inner.set_popup_mode(True)
        self._inner.update_with_matches(
            source_text=source_text,
            termbase_matches=termbase_matches,
            nt_matches=nt_matches,
        )
        # Bubble chip clicks → our term_inserted path so the click and
        # keyboard Enter paths converge on the same insertion guard.
        self._inner.term_insert_requested.connect(self._request_insert)
        # Edit + delete bubble through to the host so the dialog opens
        # outside this popup.
        self._inner.edit_entry_requested.connect(self._on_edit_request)
        # We don't expose delete from the popup (Trados doesn't either);
        # the user can still right-click on a chip if they want to.

        card_layout.addWidget(self._inner)

        # ── Hint label ────────────────────────────────────────────────
        self._hint_label = QLabel(
            "← → cycle  ·  Enter insert  ·  1–9 insert  ·  E edit  ·  I info  ·  Esc close"
        )
        self._hint_label.setStyleSheet(
            "color: #888; font-size: 8pt; padding: 3px 6px; background: transparent;"
        )
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._hint_label)

        # ── Initial sizing ────────────────────────────────────────────
        # v1.10.89: fixed default size instead of the broken
        # _shrink_to_content from v1.10.87, which read
        # ``inner.sizeHint()`` — a near-zero value for FlowLayout-based
        # widgets — and ended up collapsing the popup to one chip wide
        # by ~600 px tall. Picking a sensible default (≈ 60 % of screen
        # width, capped) lets the FlowLayout wrap chips to 4–6 per row
        # without us trying to second-guess its preferred dimensions.
        # The inner scroll area handles any overflow on very long
        # segments.
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            sg = screen.availableGeometry()
            target_w = max(560, min(int(sg.width() * 0.55), 980))
            target_h = max(220, min(int(sg.height() * 0.40), 380))
        else:
            target_w = 760
            target_h = 320
        self.resize(target_w, target_h)

        # ── Highlight the first chip ──────────────────────────────────
        blocks = self._inner.get_term_blocks()
        if blocks:
            self._current_index = 0
            blocks[0].set_current(True)

    # ── Positioning ──────────────────────────────────────────────────────

    def _position_near_cursor(self):
        """Place the popup near the OS cursor, clamped to the screen."""
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        sg = screen.availableGeometry()

        w = self.width()
        h = self.height()
        x = cursor_pos.x() + 12
        y = cursor_pos.y() + 18
        if x + w > sg.right():
            x = sg.right() - w - 6
        if y + h > sg.bottom():
            y = cursor_pos.y() - h - 12
        x = max(sg.left() + 4, x)
        y = max(sg.top() + 4, y)
        self.move(x, y)

    # ── Cycling ──────────────────────────────────────────────────────────

    def _move_selection(self, delta: int):
        blocks = self._inner.get_term_blocks()
        n = len(blocks)
        if n == 0:
            return
        # Wrap with mod that handles negatives correctly.
        new_idx = ((self._current_index + delta) % n + n) % n
        if 0 <= self._current_index < n:
            blocks[self._current_index].set_current(False)
        self._current_index = new_idx
        blocks[self._current_index].set_current(True)
        # Scroll into view inside the inner widget's scroll area.
        if hasattr(self._inner, 'scroll') and self._inner.scroll is not None:
            self._inner.scroll.ensureWidgetVisible(blocks[self._current_index])

    # ── Insertion ────────────────────────────────────────────────────────

    def _request_insert(self, text: str):
        """Single-flight insertion. First caller wins; subsequent calls
        are no-ops. We close the popup before emitting so focus returns
        to the editor and the inserted text lands in the right place.
        """
        if not text or self._pending_insert is not None:
            return
        self._pending_insert = text
        self.close()  # triggers closeEvent → emits term_inserted

    def _insert_current(self):
        blocks = self._inner.get_term_blocks()
        if not (0 <= self._current_index < len(blocks)):
            return
        block = blocks[self._current_index]
        # Resolve insert text: TermBlock uses translations[0].target_term;
        # NTBlock inserts the source word verbatim.
        from modules.termlens_widget import TermBlock, NTBlock
        if isinstance(block, TermBlock):
            text = block.target_term or ''
        elif isinstance(block, NTBlock):
            text = block.source_text or ''
        else:
            return
        self._request_insert(text)

    def _insert_by_number(self, n: int):
        """1-based — Alt+N mirrors the docked panel's Alt-N behaviour."""
        if n < 1:
            return
        # The TermLensWidget already has the canonical insert-by-number
        # path; reuse it so the numbering stays in sync with what the
        # chip badges show. The widget's helper looks up its internal
        # shortcut_terms dict and emits term_insert_requested, which
        # routes through our _request_insert above.
        try:
            self._inner.insert_term_by_number(n)
        except Exception:
            pass

    # ── Edit / Info ──────────────────────────────────────────────────────

    def _on_edit_request(self, term_id: int, termbase_id: int):
        """Forward an edit request to the host, closing the popup first."""
        # Suppress focus-close so closing this doesn't race the edit
        # dialog opening on top.
        self._suppress_focus_close = True
        # Defer the emit until AFTER close so focus has returned to the
        # host before the modal editor opens — matches the Hide()+
        # BeginInvoke pattern used on the Trados side.
        self._pending_edit = (term_id, termbase_id)
        self.close()

    def _edit_current(self):
        blocks = self._inner.get_term_blocks()
        if not (0 <= self._current_index < len(blocks)):
            return
        block = blocks[self._current_index]
        term_id = getattr(block, 'term_id', None)
        termbase_id = getattr(block, 'termbase_id', None)
        if term_id and termbase_id:
            self._on_edit_request(term_id, termbase_id)

    def _toggle_info_for_current(self):
        """Toggle the sticky metadata popup for the highlighted chip.

        Reuses the existing TermPopup singleton from termlens_widget so
        the popup looks identical to what hovering produces. Pressing I
        again hides it.
        """
        blocks = self._inner.get_term_blocks()
        if not (0 <= self._current_index < len(blocks)):
            return
        block = blocks[self._current_index]
        from modules.termlens_widget import TermPopup, TermBlock
        if not isinstance(block, TermBlock):
            return  # NT blocks don't carry the rich metadata popup
        html = getattr(block, '_popup_html', '')
        anchor = getattr(block, 'target_container', None)
        if not html or anchor is None:
            return
        try:
            popup = TermPopup.get_instance()
        except Exception:
            return
        # If already visible, hide it (toggle behaviour).
        try:
            if popup.isVisible():
                popup.hide()
                return
        except Exception:
            pass
        # Suppress focus-close around the show so the popup gaining
        # focus doesn't close us. The TermPopup itself is meant to be
        # non-activating; the suppress is defence-in-depth.
        self._suppress_focus_close = True
        try:
            popup.show_for(anchor, html)
        finally:
            self._suppress_focus_close = False

    # ── Auto-close ──────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        # Capture the cursor baseline AFTER the popup is on-screen so
        # the first paint doesn't shift the cursor and tear us down on
        # tick #1.
        self._initial_cursor_pos = QCursor.pos()
        if self._auto_close_timer is None:
            self._auto_close_timer = QTimer(self)
            self._auto_close_timer.setInterval(75)
            self._auto_close_timer.timeout.connect(self._on_auto_close_tick)
        self._auto_close_timer.start()
        # v1.10.89 — explicit activation. Without raise_/activateWindow,
        # frameless top-level Dialog windows on Windows sometimes paint
        # without becoming the active window, leaving keyboard focus on
        # whatever was active before (typically the segment grid).
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _on_auto_close_tick(self):
        if not self.isVisible() or self._initial_cursor_pos is None:
            return
        pos = QCursor.pos()
        dx = abs(pos.x() - self._initial_cursor_pos.x())
        dy = abs(pos.y() - self._initial_cursor_pos.y())
        # 4-px tolerance matches the Trados side; below this is just
        # OS jitter when a top-most window appears.
        if dx > 4 or dy > 4:
            if self._auto_close_timer is not None:
                self._auto_close_timer.stop()
            self.close()

    def changeEvent(self, event):
        # v1.10.89 — close on WINDOW deactivate (focus moves to another
        # top-level window) rather than on FOCUS out (which fires every
        # time a child widget gains/loses focus inside the popup,
        # closing us prematurely whenever the user pressed any key).
        # The TermPopup metadata popup uses ToolTip window flags so
        # showing it doesn't deactivate us — that path is safe.
        super().changeEvent(event)
        try:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.ActivationChange:
                if not self.isActiveWindow() and not self._suppress_focus_close:
                    QTimer.singleShot(0, self.close)
        except Exception:
            pass

    # ── Lifecycle ────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Stop auto-close timer regardless of how we got here.
        if self._auto_close_timer is not None:
            self._auto_close_timer.stop()
            self._auto_close_timer = None
        # Hide the metadata sticky popup if it's still visible.
        try:
            from modules.termlens_widget import TermPopup
            popup = TermPopup.get_instance()
            if popup.isVisible():
                popup.hide()
        except Exception:
            pass
        # Fire pending insert, if any.
        if self._pending_insert is not None:
            text = self._pending_insert
            self._pending_insert = None
            try:
                self.term_inserted.emit(text)
            except Exception:
                pass
        # Fire pending edit, if any (defer the emit by one event-loop
        # tick so this popup's window has fully torn down before the
        # modal editor takes the stage).
        if self._pending_edit is not None:
            term_id, termbase_id = self._pending_edit
            self._pending_edit = None
            QTimer.singleShot(0, lambda: self.edit_requested.emit(term_id, termbase_id))
        super().closeEvent(event)

    # ── Keyboard ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()

        # 1-9 inserts directly (bare or with Alt modifier — matches the
        # docked panel's Alt+N shortcut so muscle memory carries over).
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            self._insert_by_number(key - Qt.Key.Key_0)
            event.accept()
            return

        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._move_selection(+1)
            event.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._move_selection(-1)
            event.accept()
            return
        if key == Qt.Key.Key_Backtab:  # Shift+Tab
            self._move_selection(-1)
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._insert_current()
            event.accept()
            return

        if key == Qt.Key.Key_E and mods == Qt.KeyboardModifier.NoModifier:
            self._edit_current()
            event.accept()
            return

        if key == Qt.Key.Key_I and mods == Qt.KeyboardModifier.NoModifier:
            self._toggle_info_for_current()
            event.accept()
            return

        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return

        # Pure modifier presses (Ctrl/Shift/Alt alone) shouldn't close
        # the popup — otherwise the Ctrl-RELEASE that opens us would
        # close us immediately. Anything else = "user is doing something
        # else", close.
        if key not in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
            Qt.Key.Key_CapsLock,
            Qt.Key.Key_NumLock,
            Qt.Key.Key_ScrollLock,
        ):
            self.close()
            event.accept()
            return

        super().keyPressEvent(event)
