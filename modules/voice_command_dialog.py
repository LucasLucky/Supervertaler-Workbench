"""Dialog for adding and editing voice commands.

Extracted from Supervertaler.py so that both the legacy Tools tab and the
Sidekick AutoFingers tab can use it without creating a circular import (modules/
must not import from Supervertaler.py).
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTextEdit, QPushButton,
)

from modules.voice_commands import VoiceCommand


class VoiceCommandEditDialog(QDialog):
    """Dialog for adding/editing voice commands"""

    CATEGORIES = ["navigation", "editing", "translation", "lookup", "file",
                  "view", "dictation", "memoq", "trados", "custom"]
    ACTION_TYPES = [
        ("internal", "Internal Action (Supervertaler)"),
        ("keystroke", "Keystroke (e.g., ctrl+s)"),
        ("ahk_inline", "AutoHotkey Code"),
        ("ahk_script", "AutoHotkey Script File"),
    ]

    def __init__(self, parent=None, command: VoiceCommand = None):
        super().__init__(parent)
        self.command = command
        self.setup_ui()

        if command:
            self.populate_from_command(command)

    def setup_ui(self):
        self.setWindowTitle("Edit Voice Command" if self.command else "Add Voice Command")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        phrase_layout = QHBoxLayout()
        phrase_layout.addWidget(QLabel("Phrase:"))
        self.phrase_edit = QLineEdit()
        self.phrase_edit.setPlaceholderText("e.g., confirm segment")
        phrase_layout.addWidget(self.phrase_edit)
        layout.addLayout(phrase_layout)

        aliases_layout = QHBoxLayout()
        aliases_layout.addWidget(QLabel("Aliases:"))
        self.aliases_edit = QLineEdit()
        self.aliases_edit.setPlaceholderText("e.g., confirm, done, okay (comma-separated)")
        aliases_layout.addWidget(self.aliases_edit)
        layout.addLayout(aliases_layout)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        for value, label in self.ACTION_TYPES:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        action_layout = QVBoxLayout()
        action_label = QLabel("Action:")
        action_layout.addWidget(action_label)
        self.action_edit = QTextEdit()
        self.action_edit.setMaximumHeight(100)
        self.action_edit.setPlaceholderText("For internal: action_name\nFor keystroke: ctrl+s\nFor AHK: Send, ^s")
        action_layout.addWidget(self.action_edit)
        layout.addLayout(action_layout)

        self.internal_actions_layout = QHBoxLayout()
        self.internal_actions_layout.addWidget(QLabel("Preset:"))
        self.internal_combo = QComboBox()
        self.internal_combo.addItems([
            "navigate_next", "navigate_previous", "navigate_first", "navigate_last",
            "confirm_segment", "copy_source_to_target", "clear_target",
            "translate_segment", "batch_translate",
            "open_superlookup", "concordance_search",
            "show_log", "show_editor",
            "start_dictation", "stop_listening"
        ])
        self.internal_combo.currentTextChanged.connect(lambda t: self.action_edit.setPlainText(t))
        self.internal_actions_layout.addWidget(self.internal_combo)
        self.internal_actions_layout.addStretch()
        layout.addLayout(self.internal_actions_layout)

        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("e.g., Confirm current segment")
        desc_layout.addWidget(self.desc_edit)
        layout.addLayout(desc_layout)

        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(self.CATEGORIES)
        self.cat_combo.setEditable(True)
        cat_layout.addWidget(self.cat_combo)
        layout.addLayout(cat_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        self._on_type_changed()

    def _on_type_changed(self):
        """Show/hide internal actions dropdown based on type"""
        is_internal = self.type_combo.currentData() == "internal"
        for i in range(self.internal_actions_layout.count()):
            widget = self.internal_actions_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(is_internal)

    def populate_from_command(self, cmd: VoiceCommand):
        self.phrase_edit.setText(cmd.phrase)
        self.aliases_edit.setText(", ".join(cmd.aliases))

        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == cmd.action_type:
                self.type_combo.setCurrentIndex(i)
                break

        self.action_edit.setPlainText(cmd.action)
        self.desc_edit.setText(cmd.description)

        idx = self.cat_combo.findText(cmd.category)
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)
        else:
            self.cat_combo.setCurrentText(cmd.category)

    def get_command(self) -> VoiceCommand:
        aliases_text = self.aliases_edit.text().strip()
        aliases = [a.strip() for a in aliases_text.split(",") if a.strip()] if aliases_text else []

        return VoiceCommand(
            phrase=self.phrase_edit.text().strip(),
            aliases=aliases,
            action_type=self.type_combo.currentData(),
            action=self.action_edit.toPlainText().strip(),
            description=self.desc_edit.text().strip(),
            category=self.cat_combo.currentText().strip(),
            enabled=True,
        )
