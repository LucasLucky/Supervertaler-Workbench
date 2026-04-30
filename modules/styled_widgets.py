"""Shared styled widgets used across Supervertaler.

Currently a single class – :class:`CheckmarkCheckBox` – that previously
existed as nine near-identical copies scattered through the codebase.
Designed to grow into the home for any other custom-styled widget that
needs to be reused in three or more places.

If you tweak the look of one of these widgets, the change applies
everywhere automatically. Don't paste local copies back into other files.
"""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QCheckBox, QStyleOptionButton


class CheckmarkCheckBox(QCheckBox):
    """Standard Supervertaler styled checkbox.

    16×16 rounded indicator, white background unchecked, green fill
    (Material 500 / hover 600) when checked, with a manually-painted
    white checkmark so the visual is consistent across platforms (Qt's
    default checkmark glyph differs between Windows / macOS / Linux
    styles and at small sizes can render too thin or be cut off).
    """

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setEnabled(True)
        self.setStyleSheet("""
            QCheckBox {
                font-size: 9pt;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #999;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border-color: #4CAF50;
            }
            QCheckBox::indicator:hover {
                border-color: #666;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #45a049;
                border-color: #45a049;
            }
        """)

    def paintEvent(self, event):
        """Draw a white checkmark on top of the indicator when checked."""
        super().paintEvent(event)
        if not self.isChecked():
            return

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        indicator_rect = self.style().subElementRect(
            self.style().SubElement.SE_CheckBoxIndicator, opt, self
        )
        if not indicator_rect.isValid():
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen_width = max(
                2.0,
                min(indicator_rect.width(), indicator_rect.height()) * 0.12,
            )
            painter.setPen(QPen(
                QColor(255, 255, 255), pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            painter.setBrush(QColor(255, 255, 255))

            x = indicator_rect.x()
            y = indicator_rect.y()
            w = indicator_rect.width()
            h = indicator_rect.height()

            # 15% padding so the checkmark sits comfortably inside
            # the indicator square at small sizes.
            padding = min(w, h) * 0.15
            x += padding
            y += padding
            w -= padding * 2
            h -= padding * 2

            # Two-segment checkmark – start lower-left, dip to bottom,
            # rise to upper-right.
            check_x1 = x + w * 0.10
            check_y1 = y + h * 0.50
            check_x2 = x + w * 0.35
            check_y2 = y + h * 0.70
            check_x3 = x + w * 0.90
            check_y3 = y + h * 0.25

            painter.drawLine(QPointF(check_x2, check_y2), QPointF(check_x3, check_y3))
            painter.drawLine(QPointF(check_x1, check_y1), QPointF(check_x2, check_y2))
        finally:
            painter.end()
