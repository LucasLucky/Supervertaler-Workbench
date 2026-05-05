"""Dialog for adding and editing voice commands.

Extracted from Supervertaler.py so that both the legacy Tools tab and the
Sidekick AutoFingers tab can use it without creating a circular import (modules/
must not import from Supervertaler.py).
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTextEdit, QPushButton,
)

from modules.voice_commands import VoiceCommand


# Per-action-type cheat sheets shown below the Action field. Each entry
# is a short HTML snippet describing what to put in the Action field for
# that action type, plus a few canonical examples. Edited as a single
# block to keep the dialog code clean; rendered into a QLabel so the
# user gets links/bold/code styling for free.
_ACTION_CHEAT_SHEETS = {
    "internal": (
        "<b>Internal actions</b> are built into Supervertaler. Use the "
        "<b>Preset</b> dropdown above, or type one of these names directly:"
        "<ul style='margin-top:2px; margin-bottom:0;'>"
        "<li><code>navigate_next</code>, <code>navigate_previous</code>, "
        "<code>navigate_first</code>, <code>navigate_last</code></li>"
        "<li><code>confirm_segment</code>, <code>copy_source_to_target</code>, "
        "<code>clear_target</code></li>"
        "<li><code>translate_segment</code>, <code>batch_translate</code></li>"
        "<li><code>open_superlookup</code>, <code>concordance_search</code></li>"
        "<li><code>show_log</code>, <code>show_editor</code></li>"
        "<li><code>start_dictation</code>, <code>stop_listening</code></li>"
        "</ul>"
    ),
    "keystroke": (
        "<b>Keystroke</b> sends a key combination to whichever app is in the "
        "foreground (Trados, memoQ, Word, browser, etc.).<br><br>"
        "<b>Modifiers</b> &mdash; combine with <code>+</code>:<br>"
        "<code>ctrl</code>, <code>alt</code>, <code>shift</code>, <code>win</code>"
        "<br><br>"
        "<b>Special keys</b>:<br>"
        "<code>enter</code>, <code>tab</code>, <code>escape</code>, "
        "<code>space</code>, <code>backspace</code>, <code>delete</code>, "
        "<code>insert</code>, <code>home</code>, <code>end</code>, "
        "<code>pageup</code>, <code>pagedown</code>, <code>up</code>, "
        "<code>down</code>, <code>left</code>, <code>right</code>, "
        "<code>f1</code>&hellip;<code>f12</code>"
        "<br><br>"
        "<b>Examples</b>:"
        "<ul style='margin-top:2px; margin-bottom:0;'>"
        "<li><code>ctrl+s</code> &mdash; Save</li>"
        "<li><code>ctrl+shift+enter</code> &mdash; Confirm + next segment (Trados)</li>"
        "<li><code>tab</code> &mdash; Tab key (inserts tab in text editors, "
        "advances field in dialogs)</li>"
        "<li><code>alt+tab</code> &mdash; Switch app</li>"
        "</ul>"
    ),
    "ahk_inline": (
        "<b>AutoHotkey v2 code</b>, run inline against the foreground window. "
        "<i>Windows only.</i><br><br>"
        "<b>Common patterns</b>:"
        "<ul style='margin-top:2px; margin-bottom:0;'>"
        "<li><code>Send \"{Tab}\"</code> &mdash; press Tab</li>"
        "<li><code>Send \"^s\"</code> &mdash; press Ctrl+S</li>"
        "<li><code>SendText \"Hello, world\"</code> &mdash; type literal text "
        "(no key interpretation)</li>"
        "<li><code>Sleep 200</code> &mdash; pause 200&nbsp;ms</li>"
        "<li><code>WinActivate \"ahk_exe Trados.Studio.exe\"</code> &mdash; "
        "bring Trados to front</li>"
        "</ul><br>"
        "Multi-line snippets work too. Full reference at "
        "<a href='https://www.autohotkey.com/docs/v2/'>autohotkey.com/docs/v2</a>."
    ),
    "ahk_script": (
        "<b>Path to an .ahk file</b> (AutoHotkey v2 syntax). "
        "<i>Windows only.</i><br><br>"
        "<b>Examples</b>:"
        "<ul style='margin-top:2px; margin-bottom:0;'>"
        "<li><code>D:\\AHK\\confirm-segment.ahk</code></li>"
        "<li><code>C:\\Users\\you\\Documents\\AHK\\my-macro.ahk</code></li>"
        "</ul><br>"
        "Tip: keep reusable scripts in one folder, reference them by full path. "
        "Use the AutoHotkey Integration → <b>Open Scripts Folder</b> button on "
        "the AutoFingers tab to jump there."
    ),
}


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

        # Context-sensitive cheat sheet that updates with the Type
        # dropdown – tells the user what to put in the Action field for
        # each type (modifier syntax, special-key names, AHK examples,
        # available internal actions, etc.). The content lives in
        # _ACTION_CHEAT_SHEETS at the top of this module.
        self._cheat_sheet = QLabel()
        self._cheat_sheet.setTextFormat(Qt.TextFormat.RichText)
        self._cheat_sheet.setWordWrap(True)
        self._cheat_sheet.setOpenExternalLinks(True)
        self._cheat_sheet.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        self._cheat_sheet.setStyleSheet(
            "font-size: 8pt; color: #444; background-color: #FAFAFA;"
            " border: 1px solid #DDD; border-radius: 4px; padding: 8px;"
        )
        action_layout.addWidget(self._cheat_sheet)
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
        """Show/hide internal actions dropdown + refresh cheat sheet."""
        action_type = self.type_combo.currentData()
        is_internal = action_type == "internal"
        for i in range(self.internal_actions_layout.count()):
            widget = self.internal_actions_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(is_internal)
        # Update the contextual cheat sheet to match the new type.
        try:
            self._cheat_sheet.setText(_ACTION_CHEAT_SHEETS.get(action_type, ""))
        except Exception:
            pass

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
