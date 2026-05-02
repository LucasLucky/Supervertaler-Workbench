"""
Clipboard Manager Widget for Supervertaler Sidekick.

Monitors the system clipboard and maintains a persistent history of TEXT and
RASTER IMAGE clips that survives application restarts.  Items change colour
after being pasted, making it easy to track which clips have already been
used in a session.

Cross-platform: relies on QApplication.clipboard().dataChanged (Qt handles
the OS-level plumbing on Windows, macOS, and Linux/X11).
"""

import re
import hashlib

from PyQt6.QtCore import Qt, QEvent, QSize, QBuffer, QIODevice
from PyQt6.QtGui import QColor, QPixmap, QImage, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QApplication,
    QSplitter, QStackedLayout, QMenu,
)


# ---------- Item data roles ------------------------------------------------
# Stored on each QListWidgetItem.  UserRole numbering is shifted up to leave
# room for future additions without breaking older indices.

_ROLE_DB_ID    = Qt.ItemDataRole.UserRole          # int row id, or None
_ROLE_KIND     = Qt.ItemDataRole.UserRole + 1      # 'text' or 'image'
_ROLE_TEXT     = Qt.ItemDataRole.UserRole + 2      # full text (text clips only)
_ROLE_IMG      = Qt.ItemDataRole.UserRole + 3      # PNG bytes (image clips only)
_ROLE_PASTED   = Qt.ItemDataRole.UserRole + 4      # bool


class ClipboardManagerWidget(QWidget):
    """
    Persistent clipboard history panel, intended as a tab inside FloatingAssistant.

    Two callbacks are wired by the parent (FloatingAssistant):

      paste_text_callback(text: str)
          Called when the user clicks a TEXT item.  The callback is expected
          to put the text on the clipboard, hide the Sidekick, and send Ctrl+V
          to the source window.

      paste_image_callback(pixmap: QPixmap)
          Called when the user clicks an IMAGE item.  Same contract but for
          a raster image.

    Pasted state is persisted to the shared SQLite database so it survives
    restarts.  The db is accessed lazily via ``ensure_db_loaded()``, which
    FloatingAssistant calls once the database is ready.
    """

    # Independent caps per kind so a flood of images can't push your text
    # history out, and vice versa.
    MAX_TEXT_ITEMS  = 200
    MAX_IMAGE_ITEMS = 50

    _COLOUR_NORMAL = QColor("#1E1E1E")
    _COLOUR_PASTED = QColor("#AAAAAA")
    _BG_PASTED     = QColor("#F8F8F8")
    _BG_NORMAL     = QColor(Qt.GlobalColor.white)

    _THUMB_SIZE = QSize(48, 48)   # icon size shown in the list

    def __init__(self, parent_app, paste_text_callback=None,
                 paste_image_callback=None, parent=None):
        super().__init__(parent)
        self._parent_app           = parent_app
        self._paste_text_callback  = paste_text_callback
        self._paste_image_callback = paste_image_callback
        self._suppress_next        = False   # True while we set the clipboard ourselves
        self._db_loaded            = False
        self._last_image_hash      = None    # for dedup of identical re-copies

        self._init_ui()
        self._start_monitoring()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    _LIST_STYLESHEET = """
        QListWidget {
            border: 1px solid #E0E0E0; border-radius: 4px;
            background: white; font-size: 9pt; outline: none;
        }
        QListWidget::item {
            padding: 5px 8px; border-bottom: 1px solid #E4E4E4;
        }
        QListWidget::item:selected {
            background-color: #E8F4FD; color: #1E1E1E;
        }
        QListWidget::item:hover {
            background-color: #F5F9FF;
        }
    """

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header: title + Clear button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._count_label = QLabel("Clipboard History")
        self._count_label.setStyleSheet(
            "font-weight: bold; font-size: 9pt; color: #3D5A80; border: none;"
        )
        header.addWidget(self._count_label)
        header.addStretch()

        clear_btn = QPushButton("Clear all")
        clear_btn.setStyleSheet("""
            QPushButton {
                color: #888; background: transparent;
                border: 1px solid #DDD; border-radius: 3px;
                padding: 2px 8px; font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #FFF0F0;
                border-color: #E57373; color: #C62828;
            }
        """)
        clear_btn.setToolTip("Remove all clipboard history (cannot be undone)")
        clear_btn.clicked.connect(self._clear_all)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        # Two-column split: text on the left, images on the right.
        # 60/40 default favouring text (more numerous, shorter rows);
        # QSplitter so users can rebalance to taste.
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setChildrenCollapsible(False)

        self._text_list = self._make_list_widget()
        self._text_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self._text_list))
        self._text_empty = self._make_empty_label(
            "No text snippets yet –\ncopy any text to start.")
        self._text_header = QLabel("📝 Text snippets")
        text_col = self._make_column(
            self._text_header, self._text_list, self._text_empty)
        self._splitter.addWidget(text_col)

        self._image_list = self._make_list_widget()
        self._image_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._image_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self._image_list))
        self._image_empty = self._make_empty_label(
            "No images yet –\ncopy any image to start.")
        self._image_header = QLabel("🖼 Images")
        image_col = self._make_column(
            self._image_header, self._image_list, self._image_empty)
        self._splitter.addWidget(image_col)

        self._splitter.setStretchFactor(0, 6)
        self._splitter.setStretchFactor(1, 4)
        self._splitter.setSizes([600, 400])

        layout.addWidget(self._splitter, 1)

        # Reflect counts in the per-column headers.
        self._update_column_headers()

        # Footer hint
        hint = QLabel(
            "Click to paste  •  Right-click or Delete key to remove  •  "
            "Pasted items shown in grey  •  ← / → switches columns")
        hint.setStyleSheet(
            "color: #999; font-size: 7pt; padding: 2px 4px; border: none;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    # -- column / list construction helpers -----------------------------

    def _make_list_widget(self):
        lst = QListWidget()
        lst.setStyleSheet(self._LIST_STYLESHEET)
        lst.setIconSize(self._THUMB_SIZE)
        lst.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setWordWrap(False)
        lst.itemActivated.connect(self._on_item_activated)
        lst.itemClicked.connect(self._on_item_activated)
        lst.installEventFilter(self)
        return lst

    @staticmethod
    def _make_empty_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "color: #999; font-size: 8pt; padding: 20px;"
            " font-style: italic; background: white;"
            " border: 1px solid #E0E0E0; border-radius: 4px;"
        )
        return lbl

    _COL_HEADER_INACTIVE = (
        "font-weight: bold; font-size: 8pt; color: #555;"
        " padding: 2px 4px; border: none;"
    )
    _COL_HEADER_ACTIVE = (
        "font-weight: bold; font-size: 8pt; color: #1976D2;"
        " padding: 2px 4px; border: none;"
        " border-bottom: 2px solid #1976D2;"
    )

    def _make_column(self, header_label: QLabel,
                      list_widget: QListWidget,
                      empty_label: QLabel) -> QWidget:
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)

        header_label.setStyleSheet(self._COL_HEADER_INACTIVE)
        cl.addWidget(header_label)

        # Stack so list and placeholder share the same area, and only
        # one is ever visible.
        stack_widget = QWidget()
        stack = QStackedLayout(stack_widget)
        stack.addWidget(list_widget)   # index 0
        stack.addWidget(empty_label)   # index 1
        list_widget._sv_stack = stack  # so _update_empty_state can switch
        cl.addWidget(stack_widget, 1)
        return container

    def _update_empty_state(self, list_widget: QListWidget):
        stack = getattr(list_widget, '_sv_stack', None)
        if stack is None:
            return
        stack.setCurrentIndex(0 if list_widget.count() > 0 else 1)

    # ------------------------------------------------------------------
    # Focus & keyboard handling
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        # Default focus is the text list – that's where most clips live.
        self._text_list.setFocus()
        # Always highlight the latest entry (row 0) on show, not just when
        # there's no selection. The latest clip is what users overwhelmingly
        # want to paste when they open the manager – preserving a stale
        # selection from a previous session means an extra arrow-up keystroke
        # in the common case.
        if self._text_list.count() > 0:
            self._text_list.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)
        if obj is self._text_list:
            return self._handle_list_key(self._text_list, event,
                                          right_neighbour=self._image_list,
                                          left_neighbour=None)
        if obj is self._image_list:
            return self._handle_list_key(self._image_list, event,
                                          right_neighbour=None,
                                          left_neighbour=self._text_list)
        return super().eventFilter(obj, event)

    def _handle_list_key(self, list_widget, event, *,
                         right_neighbour, left_neighbour):
        """Custom key behaviour for either column.

        - Enter / Return  → paste the selected item
        - Right           → focus right_neighbour (other list, or right-pane
                            Menu if at the rightmost column)
        - Left            → focus left_neighbour (other list, or no-op at
                            the leftmost column)
        """
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = list_widget.currentItem()
            if item:
                self._on_item_activated(item)
            return True

        if key == Qt.Key.Key_Delete:
            item = list_widget.currentItem()
            if item:
                self._delete_item(item, list_widget)
            return True

        if key == Qt.Key.Key_Right:
            if right_neighbour is not None:
                self._focus_list(right_neighbour)
            else:
                # Past the rightmost column → jump to Sidekick's right-pane
                # action tree, matching the Tab-pane-jump convention.
                self._focus_sidekick_action_tree()
            return True

        if key == Qt.Key.Key_Left:
            if left_neighbour is not None:
                self._focus_list(left_neighbour)
                return True
            # Already on the leftmost column – Left is a no-op (per design).
            return False

        return False

    def _focus_list(self, list_widget: QListWidget):
        list_widget.setFocus(Qt.FocusReason.OtherFocusReason)
        if list_widget.count() > 0 and list_widget.currentRow() < 0:
            list_widget.setCurrentRow(0)

    def _focus_sidekick_action_tree(self):
        """If embedded in Sidekick, jump focus to the right-pane action tree."""
        try:
            fa = getattr(self._parent_app, '_floating_assistant', None)
            if fa is not None and hasattr(fa, '_focus_action_tree'):
                fa._focus_action_tree()
        except Exception:
            pass

    def _refresh_focus_styles(self, focused=None):
        """Highlight the column header whose list currently has focus
        (or contains the focused widget). Called by Sidekick's
        focus-change handler so users see at a glance which clipboard
        column they're in."""
        text_active = (focused is self._text_list)
        image_active = (focused is self._image_list)
        self._text_header.setStyleSheet(
            self._COL_HEADER_ACTIVE if text_active else self._COL_HEADER_INACTIVE
        )
        self._image_header.setStyleSheet(
            self._COL_HEADER_ACTIVE if image_active else self._COL_HEADER_INACTIVE
        )

    # ------------------------------------------------------------------
    # Clipboard monitoring
    # ------------------------------------------------------------------

    def _start_monitoring(self):
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

    def _on_clipboard_changed(self):
        if self._suppress_next:
            self._suppress_next = False
            return

        clip = QApplication.clipboard()
        mime = clip.mimeData()

        # Prefer images: many "copy from screenshot tool" actions put both an
        # image and a text representation (e.g. file path) on the clipboard;
        # the image is the more specialised payload.
        if mime is not None and mime.hasImage():
            image = clip.image()
            if not image.isNull():
                self._handle_new_image(image)
                return

        text = clip.text()
        if text and text.strip():
            self._handle_new_text(text)

    def _handle_new_text(self, text: str):
        # Skip if identical to the most recent TEXT item (avoid duplicate on re-copy)
        top = self._top_text_item()
        if top is not None and top.data(_ROLE_TEXT) == text:
            return
        self._add_text_clip(text, item_id=None, pasted=False, save_to_db=True)

    def _handle_new_image(self, qimage: QImage):
        png_bytes = self._encode_png(qimage)
        if not png_bytes:
            return
        digest = hashlib.sha1(png_bytes).digest()

        # Skip if the most-recent image is byte-identical
        top = self._top_image_item()
        if top is not None and self._last_image_hash == digest:
            return
        self._last_image_hash = digest

        label = f"🖼 Image {qimage.width()}×{qimage.height()} ({self._fmt_size(len(png_bytes))})"
        self._add_image_clip(label, png_bytes, item_id=None,
                             pasted=False, save_to_db=True)

    @staticmethod
    def _encode_png(qimage: QImage) -> bytes:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimage.save(buf, "PNG")
        data = bytes(buf.data())
        buf.close()
        return data

    @staticmethod
    def _fmt_size(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.0f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    # ------------------------------------------------------------------
    # List management – TEXT
    # ------------------------------------------------------------------

    def _add_text_clip(self, text: str, *, item_id=None,
                       pasted: bool = False, save_to_db: bool = False):
        item = QListWidgetItem(self._format_display(text))
        item.setData(_ROLE_DB_ID, item_id)
        item.setData(_ROLE_KIND, 'text')
        item.setData(_ROLE_TEXT, text)
        item.setData(_ROLE_IMG,  None)
        item.setData(_ROLE_PASTED, pasted)
        item.setToolTip(text[:500] if len(text) > 500 else text)
        self._apply_style(item, pasted)
        self._text_list.insertItem(0, item)

        if save_to_db:
            db = self._get_db()
            if db:
                new_id = db.add_clipboard_item(text, self.MAX_TEXT_ITEMS,
                                               self.MAX_IMAGE_ITEMS)
                item.setData(_ROLE_DB_ID, new_id)

        self._trim_list(self._text_list, self.MAX_TEXT_ITEMS)
        self._update_empty_state(self._text_list)
        self._update_count()

    # ------------------------------------------------------------------
    # List management – IMAGE
    # ------------------------------------------------------------------

    def _add_image_clip(self, label: str, png_bytes: bytes, *,
                        item_id=None, pasted: bool = False,
                        save_to_db: bool = False):
        item = QListWidgetItem(label)
        item.setData(_ROLE_DB_ID, item_id)
        item.setData(_ROLE_KIND, 'image')
        item.setData(_ROLE_TEXT, None)
        item.setData(_ROLE_IMG,  png_bytes)
        item.setData(_ROLE_PASTED, pasted)

        thumb = self._make_thumbnail(png_bytes)
        if thumb is not None:
            item.setIcon(QIcon(thumb))

        item.setToolTip(label)
        self._apply_style(item, pasted)
        self._image_list.insertItem(0, item)

        if save_to_db:
            db = self._get_db()
            if db:
                new_id = db.add_clipboard_image(label, png_bytes,
                                                self.MAX_IMAGE_ITEMS)
                item.setData(_ROLE_DB_ID, new_id)

        self._trim_list(self._image_list, self.MAX_IMAGE_ITEMS)
        self._update_empty_state(self._image_list)
        self._update_count()

    def _make_thumbnail(self, png_bytes: bytes):
        pixmap = QPixmap()
        if not pixmap.loadFromData(png_bytes, "PNG"):
            return None
        return pixmap.scaled(
            self._THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # ------------------------------------------------------------------
    # Styling / display helpers
    # ------------------------------------------------------------------

    def _apply_style(self, item: QListWidgetItem, pasted: bool):
        if pasted:
            item.setForeground(self._COLOUR_PASTED)
            item.setBackground(self._BG_PASTED)
        else:
            item.setForeground(self._COLOUR_NORMAL)
            item.setBackground(self._BG_NORMAL)

    @staticmethod
    def _format_display(text: str, max_len: int = 120) -> str:
        display = re.sub(r'\s+', ' ', text).strip()
        if len(display) > max_len:
            return display[:max_len] + "…"
        return display

    # ------------------------------------------------------------------
    # Activation (paste)
    # ------------------------------------------------------------------

    def _on_item_activated(self, item: QListWidgetItem):
        kind = item.data(_ROLE_KIND)
        if kind == 'text':
            text = item.data(_ROLE_TEXT)
            if not text:
                return
            self._mark_pasted(item)
            self._suppress_next = True
            if self._paste_text_callback:
                self._paste_text_callback(text)

        elif kind == 'image':
            png = item.data(_ROLE_IMG)
            if not png:
                # Fall back to lazy DB fetch (e.g. after a future memory-light load)
                db = self._get_db()
                item_id = item.data(_ROLE_DB_ID)
                if db and item_id is not None:
                    png = db.get_clipboard_image_data(item_id)
            if not png:
                return
            pixmap = QPixmap()
            if not pixmap.loadFromData(png, "PNG"):
                return
            self._mark_pasted(item)
            self._suppress_next = True
            if self._paste_image_callback:
                self._paste_image_callback(pixmap)

    def _mark_pasted(self, item: QListWidgetItem):
        item.setData(_ROLE_PASTED, True)
        self._apply_style(item, True)
        item_id = item.data(_ROLE_DB_ID)
        if item_id is not None:
            db = self._get_db()
            if db:
                db.mark_clipboard_item_pasted(item_id)

    # ------------------------------------------------------------------
    # Context menu & item deletion
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos, list_widget: QListWidget):
        item = list_widget.itemAt(pos)
        menu = QMenu(self)
        act_delete = None
        if item is not None:
            act_delete = menu.addAction("🗑 Delete")
            menu.addSeparator()
        act_clear = menu.addAction("Clear all")
        action = menu.exec(list_widget.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == act_delete and item is not None:
            self._delete_item(item, list_widget)
        elif action == act_clear:
            self._clear_all()

    def _delete_item(self, item: QListWidgetItem, list_widget: QListWidget):
        """Remove a single clip from the list and from the database."""
        row = list_widget.row(item)
        list_widget.takeItem(row)
        item_id = item.data(_ROLE_DB_ID)
        if item_id is not None:
            db = self._get_db()
            if db:
                db.delete_clipboard_item(item_id)
        self._update_empty_state(list_widget)
        self._update_count()

    # ------------------------------------------------------------------
    # Trimming, clearing, count
    # ------------------------------------------------------------------

    def _trim_list(self, list_widget: QListWidget, max_items: int):
        """Remove the oldest items in ``list_widget`` beyond ``max_items``."""
        while list_widget.count() > max_items:
            list_widget.takeItem(list_widget.count() - 1)

    def _clear_all(self):
        self._text_list.clear()
        self._image_list.clear()
        self._last_image_hash = None
        db = self._get_db()
        if db:
            db.clear_clipboard_history()
        self._update_empty_state(self._text_list)
        self._update_empty_state(self._image_list)
        self._update_count()

    def _top_text_item(self):
        return self._text_list.item(0) if self._text_list.count() > 0 else None

    def _top_image_item(self):
        return self._image_list.item(0) if self._image_list.count() > 0 else None

    def _update_count(self):
        text_n = self._text_list.count()
        image_n = self._image_list.count()
        total = text_n + image_n
        self._count_label.setText(
            f"Clipboard History ({total})" if total else "Clipboard History"
        )
        self._update_column_headers(text_n, image_n)

    def _update_column_headers(self, text_n=None, image_n=None):
        if text_n is None:
            text_n = self._text_list.count()
        if image_n is None:
            image_n = self._image_list.count()
        self._text_header.setText(
            f"📝 Text snippets ({text_n})" if text_n else "📝 Text snippets")
        self._image_header.setText(
            f"🖼 Images ({image_n})" if image_n else "🖼 Images")

    # ------------------------------------------------------------------
    # DB loading – called lazily once db_manager is ready
    # ------------------------------------------------------------------

    def ensure_db_loaded(self):
        if self._db_loaded:
            return
        self._db_loaded = True

        db = self._get_db()
        if not db:
            return
        try:
            # Pull both kinds; per-kind caps are enforced separately on the
            # widget side so the DB query just needs to be generous enough
            # to cover both budgets.
            limit = self.MAX_TEXT_ITEMS + self.MAX_IMAGE_ITEMS
            items = db.get_clipboard_items(limit)
            # DB returns newest-first.  insertItem(0, …) puts each new item at
            # the top, so iterate oldest-first to leave newest at row 0.
            for row in reversed(items):
                kind = row.get('kind') or 'text'
                if kind == 'image':
                    self._add_image_clip(
                        row.get('text') or "🖼 Image",
                        row['image_data'] or b"",
                        item_id=row['id'],
                        pasted=bool(row['pasted']),
                        save_to_db=False,
                    )
                else:
                    self._add_text_clip(
                        row.get('text') or "",
                        item_id=row['id'],
                        pasted=bool(row['pasted']),
                        save_to_db=False,
                    )
            self._update_count()
        except Exception as e:
            print(f"[ClipboardManager] Failed to load history from db: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_db(self):
        return getattr(self._parent_app, 'db_manager', None)
