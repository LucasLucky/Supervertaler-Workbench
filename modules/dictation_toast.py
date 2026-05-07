"""
dictation_toast.py – minimal frameless toast widget for dictation feedback.

Replaces the earlier QApplication.beep() approach which was unreliable
(many users have system sound muted) and harsh on Windows. The toast
sits at the top-right of the active screen, shows "🎤 Listening…", and
fades in on construction. The caller must call ``dismiss()`` when the
dictation finishes – there is intentionally no auto-timeout, because
push-to-talk recordings are arbitrarily long.

Usage from the main window::

    from modules.dictation_toast import show_dictation_toast
    self._dictation_toast = show_dictation_toast(self)
    # ... later, when recording ends:
    self._dictation_toast.dismiss()

The widget is owned by Qt; the caller only needs to keep a reference so
``dismiss()`` is reachable. Safe to call ``dismiss()`` more than once.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QColor, QPalette, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QGraphicsDropShadowEffect, QApplication,
)


class DictationToast(QWidget):
    """
    Frameless, semi-transparent popup that floats top-right of the active
    screen and shows a single status line. Used to indicate that dictation
    has started after a Ctrl+Shift+Space push-to-talk hotkey was received.
    """

    _MARGIN_X = 24       # pixels from the right edge of the screen
    _MARGIN_Y = 56       # pixels from the top of the screen (clear of the menu bar / titlebar)
    _MIN_WIDTH = 240
    _HEIGHT = 56
    _FADE_MS = 180       # in/out fade duration

    def __init__(self, parent_for_screen=None, text: str = "🎤  Listening…"):
        # No parent so the widget is independent of the main window's
        # focus/visibility – we want the toast to show even when the user
        # is in another app.
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # ---- Visual ----
        self._panel = QWidget(self)
        self._panel.setObjectName("toastPanel")
        self._panel.setStyleSheet(
            "#toastPanel {"
            "  background-color: rgba(36, 36, 36, 235);"
            "  border-radius: 10px;"
            "}"
        )

        self._label = QLabel(text, self._panel)
        self._label.setStyleSheet("color: white;")
        font = QFont("Segoe UI", 11)
        font.setWeight(QFont.Weight.Medium)
        self._label.setFont(font)

        layout = QHBoxLayout(self._panel)
        layout.setContentsMargins(16, 10, 18, 10)
        layout.addWidget(self._label)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._panel)

        # Soft shadow under the panel
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 120))
        self._panel.setGraphicsEffect(shadow)

        # Size + position before showing
        self.resize(max(self._MIN_WIDTH, self._panel.sizeHint().width() + 8), self._HEIGHT)
        self._reposition(parent_for_screen)

        # Fade-in
        self.setWindowOpacity(0.0)
        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(self._FADE_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._dismissed = False

    # ---- Public API ----

    def show_with_fade(self):
        self.show()
        self.raise_()
        self._fade_in.start()

    def update_text(self, text: str):
        """Swap the displayed text in-place (e.g. 'Listening…' → 'Transcribing…')."""
        self._label.setText(text)

    def dismiss(self):
        """Fade out and close. Idempotent."""
        if self._dismissed:
            return
        self._dismissed = True
        try:
            self._fade_in.stop()
        except Exception:
            pass
        try:
            anim = QPropertyAnimation(self, b"windowOpacity", self)
            anim.setDuration(self._FADE_MS)
            anim.setStartValue(self.windowOpacity())
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            anim.finished.connect(self.close)
            # Keep a ref so it isn't garbage-collected mid-animation
            self._fade_out = anim
            anim.start()
        except Exception:
            self.close()

    # ---- Internal ----

    def _reposition(self, parent_for_screen):
        """Place the toast at top-right of the screen the parent window is on,
        falling back to the primary screen."""
        screen = None
        try:
            if parent_for_screen is not None:
                handle = getattr(parent_for_screen, 'screen', None)
                if callable(handle):
                    screen = handle()
        except Exception:
            screen = None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = avail.right() - self.width() - self._MARGIN_X
        y = avail.top() + self._MARGIN_Y
        self.move(QPoint(x, y))


def show_dictation_toast(parent_window=None, text: str = "🎤  Listening…") -> DictationToast:
    """Convenience entry point used by Supervertaler.py:start_voice_dictation."""
    toast = DictationToast(parent_for_screen=parent_window, text=text)
    toast.show_with_fade()
    return toast
