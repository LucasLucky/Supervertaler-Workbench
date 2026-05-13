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

from pathlib import Path

from PyQt6.QtCore import Qt, QEvent, QSize, QBuffer, QIODevice
from PyQt6.QtGui import QColor, QPixmap, QImage, QIcon, QBrush, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QListView, QAbstractItemView, QApplication,
    QSplitter, QStackedLayout, QMenu, QTreeWidget, QTreeWidgetItem,
)

from modules.styled_widgets import HelpButton
from modules.help_system import Topics as HelpTopics
from modules.ui_scale import scaled_pt


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
        # Source-window handle captured when the user arrived via a
        # global hotkey (Ctrl+Alt+C). Snippet / conversion activations
        # use this to paste-and-return: clipboard set → Workbench
        # hidden → source window refocused → Ctrl+V sent. ``None``
        # means "no source" – the user navigated to this tab manually,
        # so we just set the clipboard and stay in Workbench.
        self._source_window = None

        self._init_ui()
        self._start_monitoring()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    # Property (not class constant) so it picks up the current global UI
    # font scale at the moment the clipboard widget is constructed.
    @property
    def _LIST_STYLESHEET(self) -> str:
        return f"""
            QListWidget {{
                border: 1px solid #E0E0E0; border-radius: 4px;
                background: white; font-size: {scaled_pt(9):.1f}pt; outline: none;
            }}
            QListWidget::item {{
                padding: 5px 8px; border-bottom: 1px solid #E4E4E4;
            }}
            QListWidget::item:selected {{
                background-color: #E8F4FD; color: #1E1E1E;
            }}
            QListWidget::item:hover {{
                background-color: #F5F9FF;
            }}
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
            f"font-weight: bold; font-size: {scaled_pt(9):.1f}pt; color: #3D5A80; border: none;"
        )
        header.addWidget(self._count_label)
        header.addStretch()

        clear_btn = QPushButton("Clear all")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                color: #888; background: transparent;
                border: 1px solid #DDD; border-radius: 3px;
                padding: 2px 8px; font-size: {scaled_pt(8):.1f}pt;
            }}
            QPushButton:hover {{
                background-color: #FFF0F0;
                border-color: #E57373; color: #C62828;
            }}
        """)
        clear_btn.setToolTip("Remove all clipboard history (cannot be undone)")
        clear_btn.clicked.connect(self._clear_all)
        header.addWidget(clear_btn)
        header.addWidget(HelpButton(HelpTopics.CLIPBOARD,
                                    tooltip="Open Clipboard help"))
        layout.addLayout(header)

        # Three-column split (v1.10.2, Phase 3 of issue #199):
        #   1. Text clipboard history (left)
        #   2. Image clipboard history (middle)
        #   3. Menu – Snippets / Special Characters / Text Conversions /
        #      QuickLauncher Prompts (right) – previously Sidekick's
        #      right-pane action tree, now folded in as a third column
        #      so the Workbench Clipboard tab matches the keyboard-
        #      navigable feel users had in Sidekick.
        # QSplitter so users can rebalance to taste.
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setChildrenCollapsible(False)

        self._text_list = self._make_list_widget(row_height_hint=24)
        self._text_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._text_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self._text_list))
        self._text_empty = self._make_empty_label(
            "No text snippets yet –\ncopy any text to start.")
        self._text_header = QLabel("📝 Text snippets")
        text_col = self._make_column(
            self._text_header, self._text_list, self._text_empty)
        self._splitter.addWidget(text_col)

        self._image_list = self._make_list_widget(
            row_height_hint=self._THUMB_SIZE.height() + 10)
        self._image_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._image_list.customContextMenuRequested.connect(
            lambda pos: self._on_context_menu(pos, self._image_list))
        self._image_empty = self._make_empty_label(
            "No images yet –\ncopy any image to start.")
        self._image_header = QLabel("🖼 Images")
        image_col = self._make_column(
            self._image_header, self._image_list, self._image_empty)
        self._splitter.addWidget(image_col)

        # Third column: action menu (snippets, characters, conversions,
        # prompts). Built lazily by _build_action_tree(); always added
        # to the splitter so the layout reserves space even if the
        # tree's content takes a moment to populate.
        self._action_items = []  # Callbacks, indexed by QTreeWidgetItem UserRole
        action_col_container = QWidget()
        action_col_layout = QVBoxLayout(action_col_container)
        action_col_layout.setContentsMargins(0, 0, 0, 0)
        action_col_layout.setSpacing(4)
        self._action_header = QLabel("📑 Menu")
        self._action_header.setStyleSheet(
            "color: #555; padding: 2px 6px; border: none; "
            f"font-size: {scaled_pt(8.5):.1f}pt; font-weight: bold;"
        )
        action_col_layout.addWidget(self._action_header)
        self._action_tree = self._build_action_tree()
        action_col_layout.addWidget(self._action_tree, 1)
        self._splitter.addWidget(action_col_container)

        self._splitter.setStretchFactor(0, 5)
        self._splitter.setStretchFactor(1, 3)
        self._splitter.setStretchFactor(2, 4)
        self._splitter.setSizes([500, 300, 400])

        layout.addWidget(self._splitter, 1)

        # Reflect counts in the per-column headers.
        self._update_column_headers()

        # Footer hint
        hint = QLabel(
            "Click to paste  •  Right-click or Delete key to remove  •  "
            "Pasted items shown in grey  •  ← / → switches columns  •  "
            "Up / Down navigates within a column")
        hint.setStyleSheet(
            f"color: #999; font-size: {scaled_pt(7):.1f}pt; padding: 2px 4px; border: none;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    # -- column / list construction helpers -----------------------------

    def _make_list_widget(self, row_height_hint: int = 24):
        lst = QListWidget()
        lst.setStyleSheet(self._LIST_STYLESHEET)
        lst.setIconSize(self._THUMB_SIZE)
        lst.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # ScrollPerPixel + a singleStep tuned to one row height. ScrollPerItem
        # made mouse-wheel and precision-trackpad scrolling feel "stuck" on
        # Windows because sub-row deltas were dropped rather than accumulated.
        # ScrollPerPixel handles those deltas smoothly. Arrow-key navigation
        # still feels row-wise because Qt's scroll-into-view on QListWidget
        # isn't animated – it scrolls just enough pixels to make the new
        # current row visible, in one step.
        lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lst.verticalScrollBar().setSingleStep(row_height_hint)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setWordWrap(False)
        # Tell Qt every row has the same height (single-line text items, or
        # all 48x48-icon image items). Lets Qt cache item geometry and skip
        # measure-each-row passes during paint and scroll. Safe because the
        # widget enforces setWordWrap(False) above and image-list items are
        # all sized to the icon dimensions.
        lst.setUniformItemSizes(True)
        # Batched layout dramatically reduces work when the user holds an
        # arrow key – Qt processes layout in chunks instead of per-row.
        lst.setLayoutMode(QListView.LayoutMode.Batched)
        lst.setBatchSize(50)
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
            f"color: #999; font-size: {scaled_pt(8):.1f}pt; padding: 20px;"
            " font-style: italic; background: white;"
            " border: 1px solid #E0E0E0; border-radius: 4px;"
        )
        return lbl

    # Properties (not class constants) so they pick up the current global UI
    # font scale at the moment the clipboard widget is constructed/refreshed.
    @property
    def _COL_HEADER_INACTIVE(self) -> str:
        return (
            f"font-weight: bold; font-size: {scaled_pt(8):.1f}pt; color: #555;"
            " padding: 2px 4px; border: none;"
        )

    @property
    def _COL_HEADER_ACTIVE(self) -> str:
        return (
            f"font-weight: bold; font-size: {scaled_pt(8):.1f}pt; color: #1976D2;"
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
            # Right past the image list now lands on the local action
            # tree (the 3rd column), not Sidekick's right pane.
            return self._handle_list_key(self._image_list, event,
                                          right_neighbour=self._action_tree,
                                          left_neighbour=self._text_list)
        if obj is self._action_tree:
            # Tree-column key handling: defer to Qt's defaults for
            # expand-on-Right / collapse-on-Left when the current item
            # supports it. Only intercept the boundary cases:
            #   • Right on a leaf or already-expanded category → swallow
            #     (nothing to the right of the action tree)
            #   • Left on a leaf or already-collapsed category →
            #     move focus to the image list (one column left)
            # That way navigation still works *and* category nodes
            # expand/collapse with the arrow keys as in any QTreeWidget.
            if event.type() == QEvent.Type.KeyPress:
                current = self._action_tree.currentItem()
                if event.key() == Qt.Key.Key_Right:
                    if current is not None and current.childCount() > 0 \
                            and not current.isExpanded():
                        return False  # let Qt expand
                    return True  # swallow
                if event.key() == Qt.Key.Key_Left:
                    if current is not None and current.childCount() > 0 \
                            and current.isExpanded():
                        return False  # let Qt collapse
                    self._focus_list(self._image_list)
                    return True
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
                # right_neighbour can be either a QListWidget (text /
                # image column) or the QTreeWidget (action menu). Both
                # accept setFocus(); _focus_list also auto-selects row
                # 0 for empty lists, which doesn't apply to the tree.
                if isinstance(right_neighbour, QTreeWidget):
                    self._focus_action_tree(right_neighbour)
                else:
                    self._focus_list(right_neighbour)
            else:
                # No right neighbour – legacy Sidekick path (jump to
                # Sidekick's right-pane action tree). Harmless no-op
                # when we're embedded as a Workbench top tab.
                self._focus_sidekick_action_tree()
            return True

        if key == Qt.Key.Key_Left:
            if left_neighbour is not None:
                self._focus_list(left_neighbour)
                return True
            # Already on the leftmost column – Left is a no-op (per design).
            return False

        return False

    def _focus_action_tree(self, tree: QTreeWidget):
        """Give focus to the action tree, selecting the first leaf if
        nothing is currently selected."""
        tree.setFocus(Qt.FocusReason.OtherFocusReason)
        # Auto-select something so Up/Down can navigate from a defined
        # starting point. Prefer an existing selection; otherwise pick
        # the first activatable leaf.
        if tree.currentItem() is None:
            it = QTreeWidgetItem(tree)  # type-hint helper, replaced below
            it = None
            root = tree.invisibleRootItem()
            for i in range(root.childCount()):
                cat = root.child(i)
                if cat.childCount() > 0:
                    cat.setExpanded(True)
                    tree.setCurrentItem(cat.child(0))
                    return
                # No children – just highlight the category itself
                tree.setCurrentItem(cat)
                return

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

    # ------------------------------------------------------------------
    # Action tree (3rd column) – Snippets / Special Characters / Text
    # Conversions / QuickLauncher Prompts. v1.10.2 (Phase 3 of issue
    # #199). Mirrors the structure Sidekick built in its right pane,
    # but lives inside the Clipboard tab so the whole experience –
    # text snippets, images, snippets, conversions, prompts – sits
    # under one navigable surface in Workbench.
    # ------------------------------------------------------------------

    _CATEGORY_SENTINEL = "__category__"  # marks tree items that are categories
    _LEAF_ICON = "•"

    def _build_action_tree(self) -> QTreeWidget:
        """Create the QTreeWidget that hosts the 3rd column's content.

        Populated by ``_populate_action_tree`` shortly after construction
        so the snippets / prompts that depend on the parent app's
        ``user_data_path`` and ``prompt_manager_qt`` have time to wire up.
        """
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setAnimated(True)
        tree.setIndentation(16)
        tree.setStyleSheet(f"""
            QTreeWidget {{
                border: 1px solid #DDD;
                background: #FAFAFA;
                font-size: {scaled_pt(9):.1f}pt; outline: none;
            }}
            QTreeWidget::item {{
                padding: 4px 6px; border-radius: 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: #D6E4F0; color: #1E1E1E;
            }}
            QTreeWidget::item:hover {{
                background-color: #FFFFFF;
            }}
        """)
        tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.itemActivated.connect(self._on_action_tree_activated)
        tree.itemClicked.connect(self._on_action_tree_clicked)
        tree.itemExpanded.connect(self._update_expand_indicators)
        tree.itemCollapsed.connect(self._update_expand_indicators)
        tree.installEventFilter(self)
        # Assign self._action_tree *before* _populate_action_tree runs –
        # the populate helpers (_make_action_category etc.) reference
        # self._action_tree to addTopLevelItem onto it. Without this
        # the first populate call raises AttributeError because
        # _build_action_tree hasn't returned yet.
        self._action_tree = tree
        # Defer populate to a separate method so we can rebuild on
        # demand (e.g. after the user edits the snippet library).
        self._populate_action_tree()
        return tree

    def _populate_action_tree(self):
        """Fill the action tree with categories + entries."""
        tree = self._action_tree
        tree.clear()
        self._action_items.clear()

        # 1. Snippets (file-backed; includes "Special Characters" and
        #    "Personal Snippets" by default, plus any user-created
        #    folders under <user_data>/snippet_library/).
        self._populate_snippet_library()

        # 2. Text Conversions (clipboard-text transformations).
        self._populate_text_conversions()

        # 3. QuickLauncher Prompts (from the unified prompt library;
        #    in v1.10.2 these just copy the prompt body to the
        #    clipboard. Phase-4 follow-up: act on the user's selection
        #    when activated, per issue #199's longer-term vision).
        self._populate_prompt_library()

        self._update_expand_indicators()

    def _make_action_category(self, label: str, expanded: bool = False) -> QTreeWidgetItem:
        """Create a bold category node in the action tree."""
        bold_font = QFont("Segoe UI", round(scaled_pt(9)), QFont.Weight.Bold)
        cat_color = QBrush(QColor("#3D5A80"))
        cat = QTreeWidgetItem([label])
        cat.setFont(0, bold_font)
        cat.setForeground(0, cat_color)
        cat.setData(0, Qt.ItemDataRole.UserRole, self._CATEGORY_SENTINEL)
        self._action_tree.addTopLevelItem(cat)
        cat.setExpanded(expanded)
        return cat

    def _add_action_leaf(self, parent: QTreeWidgetItem, text: str, callback):
        """Add a leaf item with a callback that runs on activation."""
        item = QTreeWidgetItem([text])
        idx = len(self._action_items)
        item.setData(0, Qt.ItemDataRole.UserRole, idx)
        parent.addChild(item)
        self._action_items.append(callback)
        return item

    def _update_expand_indicators(self, *_args):
        """Refresh ▶ / ▼ indicators on each top-level category."""
        root = self._action_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.childCount() > 0:
                text = item.text(0)
                for prefix in ("▶ ", "▼ "):
                    if text.startswith(prefix):
                        text = text[2:]
                        break
                indicator = "▼ " if item.isExpanded() else "▶ "
                item.setText(0, indicator + text)

    def _on_action_tree_activated(self, item: QTreeWidgetItem, _col: int = 0):
        """Enter / double-click on a tree item.

        Categories: toggle expand/collapse. Leaves: fire the callback
        stored in ``self._action_items`` at the item's UserRole index.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data == self._CATEGORY_SENTINEL:
            item.setExpanded(not item.isExpanded())
            return
        if isinstance(data, int) and 0 <= data < len(self._action_items):
            try:
                self._action_items[data]()
            except Exception as e:
                print(f"[ClipboardManagerWidget] Action handler error: {e}")

    def _on_action_tree_clicked(self, item: QTreeWidgetItem, _col: int = 0):
        """Single-click on a tree item.

        Single-click activates leaves immediately (matches the existing
        clipboard text/image columns, which paste on single click). For
        categories, single-click toggles expansion, matching the
        intuition that the entire row is the click target – not just
        the disclosure triangle.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data == self._CATEGORY_SENTINEL:
            item.setExpanded(not item.isExpanded())
            return
        if isinstance(data, int) and 0 <= data < len(self._action_items):
            try:
                self._action_items[data]()
            except Exception as e:
                print(f"[ClipboardManagerWidget] Action handler error: {e}")

    # ---- Snippets -----------------------------------------------------

    def _populate_snippet_library(self):
        """Add file-backed snippets, grouped by their top-level folder.

        Reads .md files from ``<user_data>/snippet_library/`` via
        :class:`SnippetLibrary`. Top-level folders become tree
        categories ("Special Characters", "Personal Snippets" by
        default; any user-created folder gets a generic icon).
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

            from collections import defaultdict
            by_category = defaultdict(list)
            for snip in lib.snippets:
                cat = snip['category'] or "Snippets"
                by_category[cat].append(snip)

            category_icons = {
                "Special Characters": "✨",        # ✨
                "Personal Snippets": "\U0001F4C7",     # 📇
            }
            default_icon = "\U0001F4C1"                # 📁

            for cat_name in sorted(by_category.keys(), key=str.lower):
                icon = category_icons.get(cat_name, default_icon)
                cat_item = self._make_action_category(f"{icon} {cat_name}")
                for snip in sorted(by_category[cat_name], key=lambda s: s['label'].lower()):
                    body = snip['body']
                    self._add_action_leaf(
                        cat_item, snip['label'],
                        lambda t=body: self._copy_to_clipboard(t),
                    )

        except Exception as e:
            print(f"[ClipboardManagerWidget] Snippet population error: {e}")

    # ---- Text Conversions ---------------------------------------------

    def _populate_text_conversions(self):
        """Conversions that act on whatever's currently on the clipboard.

        Result lands back on the system clipboard; the user pastes with
        Ctrl+V wherever they're focused. Sidekick used a paste-and-
        return flow because it floated over another app; in the
        Workbench top tab the user is already where they want to be,
        so "modify clipboard, you paste" is the simpler contract.
        """
        cat = self._make_action_category("\U0001F524 Text Conversions")
        self._add_action_leaf(
            cat, "Uppercase",
            lambda: self._transform_clipboard(str.upper))
        self._add_action_leaf(
            cat, "Lowercase",
            lambda: self._transform_clipboard(str.lower))
        self._add_action_leaf(
            cat, "Title Case",
            lambda: self._transform_clipboard(str.title))
        self._add_action_leaf(
            cat, "Sentence case",
            lambda: self._transform_clipboard(self._to_sentence_case))
        self._add_action_leaf(
            cat, "Single curly quotes: ‘Example’",
            lambda: self._wrap_clipboard("‘", "’"))
        self._add_action_leaf(
            cat, "Double curly quotes: “Example”",
            lambda: self._wrap_clipboard("“", "”"))
        self._add_action_leaf(
            cat, "Round brackets: (Example)",
            lambda: self._wrap_clipboard("(", ")"))
        self._add_action_leaf(
            cat, "Square brackets: [Example]",
            lambda: self._wrap_clipboard("[", "]"))
        self._add_action_leaf(
            cat, "Remove soft hyphens (U+00AD)",
            lambda: self._transform_clipboard(lambda s: s.replace("­", "")))
        self._add_action_leaf(
            cat, "Double quotes → single quotes",
            lambda: self._transform_clipboard(lambda s: s.replace('"', "'")))
        self._add_action_leaf(
            cat, "Make <b>bold</b>",
            lambda: self._wrap_clipboard("<b>", "</b>"))

    @staticmethod
    def _to_sentence_case(text: str) -> str:
        """Lowercase the whole string, then capitalise the first letter
        of each sentence. Cheap heuristic – matches Sidekick's old
        helper behaviour."""
        if not text:
            return text
        lowered = text.lower()
        # Split on ". " / "! " / "? " and re-capitalise
        out = []
        capitalise_next = True
        for ch in lowered:
            if capitalise_next and ch.isalpha():
                out.append(ch.upper())
                capitalise_next = False
            else:
                out.append(ch)
                if ch in '.!?':
                    capitalise_next = True
        return ''.join(out)

    def set_source_window(self, hwnd):
        """Tell the widget which window the user arrived from (via a
        global hotkey). Snippet / conversion activations will then do
        the paste-and-return dance instead of just setting the
        clipboard. ``None`` clears the source – use that when the user
        navigates to the Clipboard tab manually rather than via
        Ctrl+Alt+C, since there's no "elsewhere" to return to."""
        self._source_window = hwnd

    def _paste_to_source(self, text: str):
        """Set clipboard to ``text``, then – if a source window was
        captured – hide Workbench, refocus the source window, and send
        Ctrl+V. Without a source, just set the clipboard and stay put.

        Mirrors Sidekick's ``_paste_and_return`` semantics so users
        who Ctrl+Alt+C from Trados, pick a snippet / conversion, and
        expect the result back in Trados get exactly that. Mirrors
        Sidekick's implementation closely so the UX is identical.
        """
        if text is None:
            return
        self._suppress_next = True
        QApplication.clipboard().setText(text)

        source = self._source_window
        if source is None:
            return  # No source – user is in Workbench by choice; stay.

        # One-shot: clear after we've used it. The next activation
        # without a fresh hotkey trip just sets the clipboard and
        # stays in Workbench, which is the right default.
        self._source_window = None

        # Hide Workbench so the focus-grab doesn't fight the source
        # window for the foreground, AND so it disappears from the
        # taskbar like Sidekick used to. The user can resummon
        # Workbench with any of the global tab-jumping hotkeys
        # (Ctrl+Alt+L / Ctrl+Alt+C), which call show() + raise() to
        # restore it with state intact.
        try:
            parent_window = self._parent_app
            if parent_window is not None and hasattr(parent_window, 'hide'):
                parent_window.hide()
        except Exception as e:
            print(f"[ClipboardManagerWidget] Could not hide Workbench: {e}")

        # Refocus source and send Ctrl+V. Tiny delay so the OS has a
        # tick to action the minimise + focus before the keystroke
        # fires – without it the paste lands on the wrong window.
        from PyQt6.QtCore import QTimer

        def _do_paste():
            try:
                from modules.platform_helpers import (
                    activate_foreground_window, CrossPlatformKeySender,
                )
                activate_foreground_window(source)
                import time
                time.sleep(0.15)
                CrossPlatformKeySender().send_paste()
            except Exception as e:
                print(f"[ClipboardManagerWidget] Paste-and-return error: {e}")

        QTimer.singleShot(100, _do_paste)

    def _transform_clipboard(self, fn):
        """Read clipboard text, apply ``fn``, paste back to source.

        If we have a source window (user arrived via Ctrl+Alt+C), do
        the paste-and-return flow. Otherwise just set the clipboard
        and stay in Workbench.
        """
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            return
        try:
            result = fn(text)
        except Exception as e:
            print(f"[ClipboardManagerWidget] Transform error: {e}")
            return
        self._paste_to_source(result)

    def _wrap_clipboard(self, prefix: str, suffix: str):
        """Read clipboard text, wrap, paste back to source."""
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            return
        self._paste_to_source(prefix + text + suffix)

    def _copy_to_clipboard(self, text: str):
        """Copy a snippet's body to the clipboard and paste back to
        source if one was captured."""
        if not text:
            return
        self._paste_to_source(text)

    # ---- Prompts ------------------------------------------------------

    def _populate_prompt_library(self):
        """Add QuickLauncher prompts from the unified prompt library,
        grouped by their folder structure.

        v1.10.2 behaviour: activating a prompt copies its body to the
        clipboard. A later iteration (per issue #199) will make this
        operate on the user's current selection – "select text, call
        up Clipboard, navigate to prompt, Enter, prompt runs on the
        selection".
        """
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
                folder = parts[0] if len(parts) > 1 else "Prompts"
                display = label or parts[-1].replace('.md', '')
                folders[folder].append((rel_path, display))

            prompts_cat = self._make_action_category("\U0001F4DD Prompts", expanded=False)

            for folder, folder_items in sorted(folders.items()):
                if len(folders) == 1 and folder == "Prompts":
                    parent = prompts_cat
                else:
                    sub_cat = QTreeWidgetItem([f"\U0001F4C1 {folder}"])
                    sub_cat.setData(0, Qt.ItemDataRole.UserRole, self._CATEGORY_SENTINEL)
                    prompts_cat.addChild(sub_cat)
                    parent = sub_cat

                for rel_path, display in sorted(folder_items, key=lambda x: x[1].lower()):
                    self._add_action_leaf(
                        parent,
                        f"{self._LEAF_ICON} {display}",
                        lambda p=rel_path: self._activate_prompt(p),
                    )
        except Exception as e:
            print(f"[ClipboardManagerWidget] Prompt population error: {e}")

    def _activate_prompt(self, rel_path: str):
        """Look up a prompt by its relative path and copy its body to
        the system clipboard. v1.10.2 placeholder; v1.10.x will replace
        this with "fire the prompt against the user's current
        selection" once the cross-app capture plumbing is in place.

        Uses the same ``lib.prompts.get(rel_path)`` lookup Sidekick's
        ``_on_prompt_action`` uses – the prompt library indexes prompts
        by their relative path and returns a dict with ``content`` /
        ``name`` keys. Falls back gracefully if the prompt is missing.
        """
        try:
            pm = getattr(self._parent_app, 'prompt_manager_qt', None)
            if not pm:
                return
            lib = getattr(pm, 'library', None)
            if not lib:
                return
            prompts = getattr(lib, 'prompts', None)
            if prompts is None:
                return
            prompt_data = prompts.get(rel_path)
            if not prompt_data:
                return
            body = (prompt_data.get('content') or "").strip()
            if body:
                self._copy_to_clipboard(body)
        except Exception as e:
            print(f"[ClipboardManagerWidget] Prompt activation error: {e}")
