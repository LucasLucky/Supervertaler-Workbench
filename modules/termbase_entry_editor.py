"""
Glossary Entry Editor Dialog

Dialog for editing individual glossary entries with all metadata fields.
Can be opened from translation results panel (edit button or right-click menu).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QSpinBox, QCheckBox, QPushButton, QGroupBox,
    QMessageBox, QListWidget, QListWidgetItem, QMenu, QScrollArea,
    QWidget, QToolButton, QApplication, QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from typing import Optional

from modules.styled_widgets import CheckmarkCheckBox  # noqa: E402



class TermbaseEntryEditor(QDialog):
    """Dialog for editing a termbase entry"""
    
    def __init__(self, parent=None, db_manager=None, termbase_id: Optional[int] = None, term_id: Optional[int] = None):
        """
        Initialize termbase entry editor
        
        Args:
            parent: Parent widget
            db_manager: DatabaseManager instance
            termbase_id: Termbase ID
            term_id: Term ID to edit (if None, creates new term)
        """
        super().__init__(parent)
        self.db_manager = db_manager
        self.termbase_id = termbase_id
        self.term_id = term_id
        self.term_data = None
        
        self.setWindowTitle("Edit Termbase Entry" if term_id else "New Termbase Entry")
        self.setModal(True)
        self.setMinimumWidth(550)

        # Auto-resize to fit screen (max 85% of screen height)
        screen = QApplication.primaryScreen().availableGeometry()
        max_height = int(screen.height() * 0.85)
        self.setMaximumHeight(max_height)

        # Start with very compact size for laptops
        self.resize(600, min(550, max_height))

        self.setup_ui()
        
        # Load existing term data if editing
        if term_id and db_manager:
            self.load_term_data()
    
    def setup_ui(self):
        """Setup the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # Term row – editable, side by side, mirrors the Add Term dialog
        # (TermMetadataDialog) layout introduced in v1.9.475/.478.  Per
        # language: term + abbreviation; the synonym group built later in
        # this method drops into the same column.
        term_row = QHBoxLayout()
        term_row.setSpacing(12)

        # Resolve language names from the main window's current project,
        # so the column captions read e.g. "English" / "Dutch" rather
        # than "Source" / "Target". Walk up the parent chain because
        # this dialog is opened from contexts (TermLens, results panel)
        # that aren't the main window directly.
        src_caption, tgt_caption = "Source", "Target"
        try:
            ancestor = self.parent()
            while ancestor is not None and not hasattr(ancestor, 'current_project'):
                ancestor = ancestor.parent() if callable(getattr(ancestor, 'parent', None)) else None
            proj = getattr(ancestor, 'current_project', None) if ancestor else None
            if proj and getattr(proj, 'source_lang', None):
                src_caption = proj.source_lang
            if proj and getattr(proj, 'target_lang', None):
                tgt_caption = proj.target_lang
        except Exception:
            pass

        # Source column: term + abbreviation (synonyms appended later)
        source_col = QVBoxLayout()
        source_col.setSpacing(2)
        source_col.addWidget(QLabel(f"<b>{src_caption}:</b>"))
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Source language term...")
        self.source_edit.setStyleSheet("padding: 4px;")
        source_col.addWidget(self.source_edit)
        source_col.addWidget(QLabel("Abbreviation:"))
        self.source_abbr_edit = QLineEdit()
        self.source_abbr_edit.setStyleSheet("padding: 4px;")
        source_col.addWidget(self.source_abbr_edit)

        # Target column: term + abbreviation
        target_col = QVBoxLayout()
        target_col.setSpacing(2)
        target_col.addWidget(QLabel(f"<b>{tgt_caption}:</b>"))
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("Target language term...")
        self.target_edit.setStyleSheet("padding: 4px;")
        target_col.addWidget(self.target_edit)
        target_col.addWidget(QLabel("Abbreviation:"))
        self.target_abbr_edit = QLineEdit()
        self.target_abbr_edit.setStyleSheet("padding: 4px;")
        target_col.addWidget(self.target_abbr_edit)

        # Stash for synonym-group placement further down.
        self._source_col_layout = source_col
        self._target_col_layout = target_col

        term_row.addLayout(source_col, 1)
        term_row.addLayout(target_col, 1)
        layout.addLayout(term_row)
        
        # Source Synonyms section (collapsible)
        source_syn_group = QGroupBox()
        source_syn_main_layout = QVBoxLayout()

        # Header with collapse button
        source_syn_header = QHBoxLayout()
        self.source_syn_toggle = QToolButton()
        self.source_syn_toggle.setText("▼")
        self.source_syn_toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.source_syn_toggle.setFixedSize(20, 20)
        self.source_syn_toggle.setCheckable(True)
        self.source_syn_toggle.setChecked(False)
        source_syn_header.addWidget(self.source_syn_toggle)

        source_syn_label = QLabel("Source Synonyms (Optional)")
        source_syn_label.setStyleSheet("font-weight: bold;")
        source_syn_header.addWidget(source_syn_label)
        source_syn_header.addStretch()
        source_syn_main_layout.addLayout(source_syn_header)

        # Collapsible content
        self.source_syn_content = QWidget()
        source_syn_layout = QVBoxLayout(self.source_syn_content)
        source_syn_layout.setContentsMargins(0, 0, 0, 0)
        self.source_syn_content.setVisible(False)
        
        source_syn_info = QLabel("Alternative source terms. First item = preferred:")
        source_syn_info.setStyleSheet("color: #666; font-size: 10px;")
        source_syn_layout.addWidget(source_syn_info)
        
        source_add_layout = QHBoxLayout()
        self.source_synonym_edit = QLineEdit()
        self.source_synonym_edit.setPlaceholderText("Enter source synonym...")
        self.source_synonym_edit.setStyleSheet("padding: 4px; font-size: 10px;")
        source_add_layout.addWidget(self.source_synonym_edit)
        
        self.source_synonym_forbidden_check = CheckmarkCheckBox("Forbidden")
        self.source_synonym_forbidden_check.setStyleSheet("font-size: 10px;")
        source_add_layout.addWidget(self.source_synonym_forbidden_check)
        
        source_add_btn = QPushButton("Add")
        source_add_btn.setMaximumWidth(50)
        source_add_btn.setStyleSheet("padding: 4px; font-size: 10px;")
        source_add_btn.clicked.connect(self.add_source_synonym)
        source_add_layout.addWidget(source_add_btn)
        source_syn_layout.addLayout(source_add_layout)
        
        self.source_synonym_edit.returnPressed.connect(self.add_source_synonym)
        
        source_list_layout = QHBoxLayout()
        self.source_synonym_list = QListWidget()
        self.source_synonym_list.setMaximumHeight(80)
        self.source_synonym_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.source_synonym_list.customContextMenuRequested.connect(self.show_source_synonym_context_menu)
        source_list_layout.addWidget(self.source_synonym_list)
        
        source_btn_col = QVBoxLayout()
        source_up_btn = QPushButton("▲")
        source_up_btn.setMaximumWidth(25)
        source_up_btn.setToolTip("Move up")
        source_up_btn.clicked.connect(lambda: self.move_synonym(self.source_synonym_list, -1))
        source_btn_col.addWidget(source_up_btn)
        
        source_down_btn = QPushButton("▼")
        source_down_btn.setMaximumWidth(25)
        source_down_btn.setToolTip("Move down")
        source_down_btn.clicked.connect(lambda: self.move_synonym(self.source_synonym_list, 1))
        source_btn_col.addWidget(source_down_btn)
        source_btn_col.addStretch()
        
        source_del_btn = QPushButton("✗")
        source_del_btn.setMaximumWidth(25)
        source_del_btn.setToolTip("Delete")
        source_del_btn.clicked.connect(lambda: self.delete_synonym(self.source_synonym_list))
        source_btn_col.addWidget(source_del_btn)
        
        source_list_layout.addLayout(source_btn_col)
        source_syn_layout.addLayout(source_list_layout)

        # Add collapsible content to main layout
        source_syn_main_layout.addWidget(self.source_syn_content)
        source_syn_group.setLayout(source_syn_main_layout)

        # Connect toggle button
        self.source_syn_toggle.clicked.connect(lambda: self.toggle_section(self.source_syn_toggle, self.source_syn_content))

        # Drop into the source-language column rather than the main vertical
        # layout – matches the Trados plugin's per-language column layout.
        self._source_col_layout.addWidget(source_syn_group)
        
        # Target Synonyms section (collapsible)
        target_syn_group = QGroupBox()
        target_syn_main_layout = QVBoxLayout()

        # Header with collapse button
        target_syn_header = QHBoxLayout()
        self.target_syn_toggle = QToolButton()
        self.target_syn_toggle.setText("▼")
        self.target_syn_toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.target_syn_toggle.setFixedSize(20, 20)
        self.target_syn_toggle.setCheckable(True)
        self.target_syn_toggle.setChecked(False)
        target_syn_header.addWidget(self.target_syn_toggle)

        target_syn_label = QLabel("Target Synonyms (Optional)")
        target_syn_label.setStyleSheet("font-weight: bold;")
        target_syn_header.addWidget(target_syn_label)
        target_syn_header.addStretch()
        target_syn_main_layout.addLayout(target_syn_header)

        # Collapsible content
        self.target_syn_content = QWidget()
        target_syn_layout = QVBoxLayout(self.target_syn_content)
        target_syn_layout.setContentsMargins(0, 0, 0, 0)
        self.target_syn_content.setVisible(False)
        
        target_syn_info = QLabel("Alternative target terms. First item = preferred:")
        target_syn_info.setStyleSheet("color: #666; font-size: 10px;")
        target_syn_layout.addWidget(target_syn_info)
        
        target_add_layout = QHBoxLayout()
        self.target_synonym_edit = QLineEdit()
        self.target_synonym_edit.setPlaceholderText("Enter target synonym...")
        self.target_synonym_edit.setStyleSheet("padding: 4px; font-size: 10px;")
        target_add_layout.addWidget(self.target_synonym_edit)
        
        self.target_synonym_forbidden_check = CheckmarkCheckBox("Forbidden")
        self.target_synonym_forbidden_check.setStyleSheet("font-size: 10px;")
        target_add_layout.addWidget(self.target_synonym_forbidden_check)
        
        target_add_btn = QPushButton("Add")
        target_add_btn.setMaximumWidth(50)
        target_add_btn.setStyleSheet("padding: 4px; font-size: 10px;")
        target_add_btn.clicked.connect(self.add_target_synonym)
        target_add_layout.addWidget(target_add_btn)
        target_syn_layout.addLayout(target_add_layout)
        
        self.target_synonym_edit.returnPressed.connect(self.add_target_synonym)
        
        target_list_layout = QHBoxLayout()
        self.target_synonym_list = QListWidget()
        self.target_synonym_list.setMaximumHeight(80)
        self.target_synonym_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.target_synonym_list.customContextMenuRequested.connect(self.show_target_synonym_context_menu)
        target_list_layout.addWidget(self.target_synonym_list)
        
        target_btn_col = QVBoxLayout()
        target_up_btn = QPushButton("▲")
        target_up_btn.setMaximumWidth(25)
        target_up_btn.setToolTip("Move up")
        target_up_btn.clicked.connect(lambda: self.move_synonym(self.target_synonym_list, -1))
        target_btn_col.addWidget(target_up_btn)
        
        target_down_btn = QPushButton("▼")
        target_down_btn.setMaximumWidth(25)
        target_down_btn.setToolTip("Move down")
        target_down_btn.clicked.connect(lambda: self.move_synonym(self.target_synonym_list, 1))
        target_btn_col.addWidget(target_down_btn)
        target_btn_col.addStretch()
        
        target_del_btn = QPushButton("✗")
        target_del_btn.setMaximumWidth(25)
        target_del_btn.setToolTip("Delete")
        target_del_btn.clicked.connect(lambda: self.delete_synonym(self.target_synonym_list))
        target_btn_col.addWidget(target_del_btn)
        
        target_list_layout.addLayout(target_btn_col)
        target_syn_layout.addLayout(target_list_layout)

        # Add collapsible content to main layout
        target_syn_main_layout.addWidget(self.target_syn_content)
        target_syn_group.setLayout(target_syn_main_layout)

        # Connect toggle button
        self.target_syn_toggle.clicked.connect(lambda: self.toggle_section(self.target_syn_toggle, self.target_syn_content))

        # Drop into the target-language column (see source-side comment).
        self._target_col_layout.addWidget(target_syn_group)
        
        # Metadata group – matches the Add Term dialog exactly: same
        # QFormLayout (label-on-the-left), same field order, same
        # placeholders. Editing and adding now look identical.
        metadata_group = QGroupBox("Metadata")
        metadata_layout = QFormLayout()

        # Definition – Trados-style dedicated field, separate from notes.
        self.definition_edit = QTextEdit()
        self.definition_edit.setMaximumHeight(45)
        self.definition_edit.setPlaceholderText("Brief definition or gloss...")
        self.definition_edit.setStyleSheet("padding: 3px;")
        metadata_layout.addRow("Definition:", self.definition_edit)

        # Domain
        self.domain_edit = QLineEdit()
        self.domain_edit.setPlaceholderText("e.g., Patents, Legal, Medical, IT...")
        metadata_layout.addRow("Domain:", self.domain_edit)

        # Notes (kept as `note_edit` to preserve existing references in
        # load_term_data / save_term elsewhere in this class).
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(45)
        self.note_edit.setPlaceholderText("Usage notes, context...")
        self.note_edit.setStyleSheet("padding: 3px;")
        metadata_layout.addRow("Notes:", self.note_edit)

        # URL (column added in v1.9.478)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://...")
        metadata_layout.addRow("URL:", self.url_edit)

        # Client
        self.client_edit = QLineEdit()
        self.client_edit.setPlaceholderText("Optional client name...")
        metadata_layout.addRow("Client:", self.client_edit)

        # Project
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("Optional project name...")
        metadata_layout.addRow("Project:", self.project_edit)

        # Non-translatable checkbox – when ticked, the target field is
        # auto-synced to the source so the term copies through unchanged
        # at translation time. Highlighted in pastel yellow in TermLens
        # to match the convention used by the Trados plugin.
        self.nontranslatable_check = CheckmarkCheckBox(
            "Non-translatable (keep source text in target)"
        )
        self.nontranslatable_check.toggled.connect(self._on_nontranslatable_toggled)
        metadata_layout.addRow("", self.nontranslatable_check)

        # Forbidden term checkbox
        self.forbidden_check = CheckmarkCheckBox(
            "Forbidden term (warn when used in translation)"
        )
        metadata_layout.addRow("", self.forbidden_check)

        metadata_group.setLayout(metadata_layout)
        layout.addWidget(metadata_group)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        # Delete button (only show when editing existing term)
        if self.term_id:
            self.delete_btn = QPushButton("🗑️ Delete")
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 20px;
                    font-size: 11px;
                    font-weight: bold;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
                QPushButton:focus {
                    outline: none;
                }
            """)
            self.delete_btn.clicked.connect(self.delete_term)
            buttons_layout.addWidget(self.delete_btn)
        
        buttons_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 11px;
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 11px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.save_btn.clicked.connect(self.save_term)
        buttons_layout.addWidget(self.save_btn)
        
        layout.addLayout(buttons_layout)
        
        # Set the scroll area content
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def toggle_section(self, toggle_btn, content_widget):
        """Toggle visibility of a collapsible section"""
        is_visible = content_widget.isVisible()
        content_widget.setVisible(not is_visible)
        toggle_btn.setText("▼" if is_visible else "▲")

    def add_source_synonym(self):
        """Add source synonym to list"""
        text = self.source_synonym_edit.text().strip()
        if text:
            for i in range(self.source_synonym_list.count()):
                if self.source_synonym_list.item(i).data(Qt.ItemDataRole.UserRole)['text'] == text:
                    QMessageBox.warning(self, "Duplicate", "Synonym already added")
                    return
            
            forbidden = self.source_synonym_forbidden_check.isChecked()
            display = f"{'🚫 ' if forbidden else ''}{text}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, {'text': text, 'forbidden': forbidden})
            if forbidden:
                item.setForeground(QColor('#d32f2f'))
            self.source_synonym_list.addItem(item)
            self.source_synonym_edit.clear()
            self.source_synonym_forbidden_check.setChecked(False)
    
    def add_target_synonym(self):
        """Add target synonym to list"""
        text = self.target_synonym_edit.text().strip()
        if text:
            for i in range(self.target_synonym_list.count()):
                if self.target_synonym_list.item(i).data(Qt.ItemDataRole.UserRole)['text'] == text:
                    QMessageBox.warning(self, "Duplicate", "Synonym already added")
                    return
            
            forbidden = self.target_synonym_forbidden_check.isChecked()
            display = f"{'🚫 ' if forbidden else ''}{text}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, {'text': text, 'forbidden': forbidden})
            if forbidden:
                item.setForeground(QColor('#d32f2f'))
            self.target_synonym_list.addItem(item)
            self.target_synonym_edit.clear()
            self.target_synonym_forbidden_check.setChecked(False)
    
    def move_synonym(self, list_widget, direction):
        """Move synonym up (-1) or down (1)"""
        row = list_widget.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if 0 <= new_row < list_widget.count():
            item = list_widget.takeItem(row)
            list_widget.insertItem(new_row, item)
            list_widget.setCurrentRow(new_row)
    
    def delete_synonym(self, list_widget):
        """Delete selected synonym"""
        row = list_widget.currentRow()
        if row >= 0:
            list_widget.takeItem(row)
    
    def show_source_synonym_context_menu(self, position):
        """Show context menu for source synonyms"""
        self._show_synonym_context_menu(self.source_synonym_list, position)
    
    def show_target_synonym_context_menu(self, position):
        """Show context menu for target synonyms"""
        self._show_synonym_context_menu(self.target_synonym_list, position)
    
    def _show_synonym_context_menu(self, list_widget, position):
        """Show context menu for synonym list"""
        if list_widget.count() == 0:
            return
        
        item = list_widget.currentItem()
        if not item:
            return
        
        menu = QMenu()
        data = item.data(Qt.ItemDataRole.UserRole)
        is_forbidden = data.get('forbidden', False)
        
        toggle_action = menu.addAction("Mark as Allowed" if is_forbidden else "Mark as Forbidden")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(list_widget.mapToGlobal(position))
        
        if action == toggle_action:
            data['forbidden'] = not is_forbidden
            text = data['text']
            display = f"{'🚫 ' if data['forbidden'] else ''}{text}"
            item.setText(display)
            item.setData(Qt.ItemDataRole.UserRole, data)
            item.setForeground(QColor('#d32f2f') if data['forbidden'] else QColor('#000000'))
        elif action == delete_action:
            list_widget.takeItem(list_widget.row(item))
    
    def _on_nontranslatable_toggled(self, checked: bool):
        """When NT is turned on, mirror source into target so the entry
        renders as a copy-through. Untoggling leaves whatever the user
        last typed in the target field – they can edit it freely again.
        """
        if checked:
            source_text = self.source_edit.text().strip() if hasattr(self, 'source_edit') else ''
            if source_text:
                self.target_edit.setText(source_text)

    def load_term_data(self):
        """Load existing term data from database"""
        if not self.db_manager or not self.term_id:
            return

        try:
            cursor = self.db_manager.cursor
            # is_nontranslatable wrapped in COALESCE so legacy databases
            # that have not yet had the migration run come back as 0
            # rather than blowing up the SELECT.
            # COALESCE on the new url / abbreviation columns so legacy
            # databases that haven't run the v1.9.478 migration yet still
            # return rows rather than blowing up the SELECT.
            cursor.execute("""
                SELECT source_term, target_term, domain, definition, forbidden,
                       notes, project, client,
                       COALESCE(is_nontranslatable, 0),
                       COALESCE(url, ''),
                       COALESCE(source_abbreviation, ''),
                       COALESCE(target_abbreviation, '')
                FROM termbase_terms
                WHERE id = ?
            """, (self.term_id,))

            row = cursor.fetchone()
            if row:
                self.term_data = {
                    'source_term': row[0],
                    'target_term': row[1],
                    'domain': row[2] or '',
                    'definition': row[3] or '',
                    'forbidden': row[4] or False,
                    'note': row[5] or '',
                    'project': row[6] or '',
                    'client': row[7] or '',
                    'is_nontranslatable': bool(row[8]),
                    'url': row[9] or '',
                    'source_abbreviation': row[10] or '',
                    'target_abbreviation': row[11] or '',
                }

                # Populate fields
                self.source_edit.setText(self.term_data['source_term'])
                self.target_edit.setText(self.term_data['target_term'])
                self.source_abbr_edit.setText(self.term_data['source_abbreviation'])
                self.target_abbr_edit.setText(self.term_data['target_abbreviation'])
                self.domain_edit.setText(self.term_data['domain'])
                self.definition_edit.setPlainText(self.term_data['definition'])
                self.note_edit.setPlainText(self.term_data['note'])
                self.url_edit.setText(self.term_data['url'])
                self.project_edit.setText(self.term_data['project'])
                self.client_edit.setText(self.term_data['client'])
                self.forbidden_check.setChecked(self.term_data['forbidden'])
                # Block the toggled signal on initial load so populating the
                # checkbox doesn't mirror source into target and overwrite
                # an intentionally-different target on a legacy NT entry.
                self.nontranslatable_check.blockSignals(True)
                self.nontranslatable_check.setChecked(self.term_data['is_nontranslatable'])
                self.nontranslatable_check.blockSignals(False)
                
                # Load synonyms
                self.load_synonyms()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load term data: {e}")
    
    def load_synonyms(self):
        """Load synonyms for current term"""
        if not self.db_manager or not self.term_id:
            return
        
        try:
            cursor = self.db_manager.cursor
            
            # Check if forbidden column exists (backward compatibility)
            cursor.execute("PRAGMA table_info(termbase_synonyms)")
            columns = [row[1] for row in cursor.fetchall()]
            has_forbidden = 'forbidden' in columns
            has_display_order = 'display_order' in columns
            
            # Load source synonyms
            if has_forbidden and has_display_order:
                cursor.execute("""
                    SELECT synonym_text, forbidden FROM termbase_synonyms
                    WHERE term_id = ? AND language = 'source'
                    ORDER BY display_order ASC
                """, (self.term_id,))
            else:
                cursor.execute("""
                    SELECT synonym_text FROM termbase_synonyms
                    WHERE term_id = ? AND language = 'source'
                    ORDER BY created_date ASC
                """, (self.term_id,))
            
            for row in cursor.fetchall():
                text = row[0]
                forbidden = bool(row[1]) if has_forbidden and len(row) > 1 else False
                display = f"{'🚫 ' if forbidden else ''}{text}"
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, {'text': text, 'forbidden': forbidden})
                if forbidden:
                    item.setForeground(QColor('#d32f2f'))
                self.source_synonym_list.addItem(item)
            
            # Load target synonyms
            if has_forbidden and has_display_order:
                cursor.execute("""
                    SELECT synonym_text, forbidden FROM termbase_synonyms
                    WHERE term_id = ? AND language = 'target'
                    ORDER BY display_order ASC
                """, (self.term_id,))
            else:
                cursor.execute("""
                    SELECT synonym_text FROM termbase_synonyms
                    WHERE term_id = ? AND language = 'target'
                    ORDER BY created_date ASC
                """, (self.term_id,))
            
            for row in cursor.fetchall():
                text = row[0]
                forbidden = bool(row[1]) if has_forbidden and len(row) > 1 else False
                display = f"{'🚫 ' if forbidden else ''}{text}"
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, {'text': text, 'forbidden': forbidden})
                if forbidden:
                    item.setForeground(QColor('#d32f2f'))
                self.target_synonym_list.addItem(item)
                
        except Exception as e:
            # Silently fail for backward compatibility
            print(f"Warning: Could not load synonyms: {e}")
    
    def delete_term(self):
        """Delete this term from database"""
        if not self.db_manager or not self.term_id:
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete this termbase entry?\n\nSource: {self.source_edit.text()}\nTarget: {self.target_edit.text()}\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.db_manager.cursor
                cursor.execute("DELETE FROM termbase_terms WHERE id = ?", (self.term_id,))
                self.db_manager.connection.commit()
                QMessageBox.information(self, "Success", "Termbase entry deleted")
                self.accept()  # Close dialog with success
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete entry: {e}")
    
    def save_term(self):
        """Save term to database"""
        # Validate inputs
        source_term = self.source_edit.text().strip()
        target_term = self.target_edit.text().strip()
        
        if not source_term or not target_term:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Both source and target terms are required."
            )
            return
        
        if not self.db_manager:
            QMessageBox.critical(
                self,
                "Error",
                "No database connection available."
            )
            return
        
        try:
            cursor = self.db_manager.cursor
            
            # Gather data
            definition = self.definition_edit.toPlainText().strip() if hasattr(self, 'definition_edit') else ""
            domain = self.domain_edit.text().strip()
            note = self.note_edit.toPlainText().strip()
            url = self.url_edit.text().strip() if hasattr(self, 'url_edit') else ""
            project = self.project_edit.text().strip()
            client = self.client_edit.text().strip()
            forbidden = self.forbidden_check.isChecked()
            is_nt = self.nontranslatable_check.isChecked()
            source_abbr = self.source_abbr_edit.text().strip() if hasattr(self, 'source_abbr_edit') else ""
            target_abbr = self.target_abbr_edit.text().strip() if hasattr(self, 'target_abbr_edit') else ""

            if self.term_id:
                # Update existing term
                cursor.execute("""
                    UPDATE termbase_terms
                    SET source_term = ?, target_term = ?,
                        definition = ?, domain = ?, notes = ?, url = ?,
                        project = ?, client = ?,
                        forbidden = ?, is_nontranslatable = ?,
                        source_abbreviation = ?, target_abbreviation = ?
                    WHERE id = ?
                """, (source_term, target_term, definition, domain, note, url,
                      project, client, forbidden, 1 if is_nt else 0,
                      source_abbr, target_abbr, self.term_id))
            else:
                # Insert new term
                cursor.execute("""
                    INSERT INTO termbase_terms
                    (termbase_id, source_term, target_term, definition, domain, notes, url,
                     project, client, forbidden, is_nontranslatable,
                     source_abbreviation, target_abbreviation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (self.termbase_id, source_term, target_term, definition, domain, note, url,
                      project, client, forbidden, 1 if is_nt else 0,
                      source_abbr, target_abbr))
            
            self.db_manager.connection.commit()
            
            # Save synonyms (get the term_id if this was a new term)
            if not self.term_id:
                self.term_id = cursor.lastrowid
            
            self.save_synonyms()
            
            # Success
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save term: {e}"
            )
    
    def save_synonyms(self):
        """Save synonyms to database"""
        if not self.db_manager or not self.term_id:
            return
        
        try:
            cursor = self.db_manager.cursor
            
            # Delete existing synonyms for this term
            cursor.execute("DELETE FROM termbase_synonyms WHERE term_id = ?", (self.term_id,))
            
            # Save source synonyms
            for i in range(self.source_synonym_list.count()):
                item = self.source_synonym_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                cursor.execute("""
                    INSERT INTO termbase_synonyms (term_id, synonym_text, language, display_order, forbidden)
                    VALUES (?, ?, 'source', ?, ?)
                """, (self.term_id, data['text'], i, 1 if data['forbidden'] else 0))
            
            # Save target synonyms
            for i in range(self.target_synonym_list.count()):
                item = self.target_synonym_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                cursor.execute("""
                    INSERT INTO termbase_synonyms (term_id, synonym_text, language, display_order, forbidden)
                    VALUES (?, ?, 'target', ?, ?)
                """, (self.term_id, data['text'], i, 1 if data['forbidden'] else 0))
            
            self.db_manager.connection.commit()
            
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to save synonyms: {e}")
    
    def get_term_data(self) -> Optional[dict]:
        """Get the current term data from the form fields"""
        return {
            'source_term': self.source_edit.text().strip(),
            'target_term': self.target_edit.text().strip(),
            'domain': self.domain_edit.text().strip(),
            'note': self.note_edit.toPlainText().strip(),
            'project': self.project_edit.text().strip(),
            'client': self.client_edit.text().strip(),
            'forbidden': self.forbidden_check.isChecked(),
            'is_nontranslatable': self.nontranslatable_check.isChecked(),
        }
