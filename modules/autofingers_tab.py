"""AutoFingers tab — voice commands and dictation control panel.

Designed to live inside Supervertaler Sidekick (modules/floating_assistant.py)
as a 4th tab, but works standalone with any parent that exposes the same
contract on the parent_app object:

    - voice_command_manager: VoiceCommandManager instance
    - voice_listener: ContinuousVoiceListener or None
    - load_dictation_settings() -> dict
    - _toggle_alwayson_listening() -> None
    - _save_voice_settings(model, duration, lang, enabled) -> None
    - _reset_voice_commands() -> None
    - _check_ahk_installed() -> str
    - _open_voice_scripts_folder() -> None

Always-On status is pushed by the main app's _update_alwayson_ui, which
locates this widget via parent_app._floating_assistant._autofingers_widget.
Voice-command CRUD broadcasts back to the parent app's
_populate_voice_commands_table so any future surface tied into that
refresh entry point also updates.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea, QFrame, QMessageBox,
)

from modules.styled_widgets import CheckmarkCheckBox

from modules.voice_command_dialog import VoiceCommandEditDialog


_TYPE_LABELS = {
    "internal": "Command",
    "keystroke": "Keystroke",
    "ahk_script": "AHK Script",
    "ahk_inline": "AHK Inline",
}


class AutoFingersTab(QWidget):
    """Voice commands + dictation control panel."""

    def __init__(self, parent_app, parent=None):
        super().__init__(parent)
        self._parent_app = parent_app
        self._build_ui()
        # Initial population
        self._populate_table()
        self._sync_alwayson_from_listener()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        settings = self._load_settings()

        # --- Header ----------------------------------------------------
        header = QLabel(
            "🎤 <b>AutoFingers</b> — voice commands and dictation.<br>"
            "Toggle Always-On to listen continuously, or press <b>F9</b> "
            "(or Ctrl+Alt+D anywhere) to dictate on demand."
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setWordWrap(True)
        header.setStyleSheet(
            "font-size: 9pt; color: #444; padding: 8px;"
            " background-color: #E3F2FD; border-radius: 4px;"
        )
        layout.addWidget(header)

        # --- Always-On controls ---------------------------------------
        alwayson_group = QGroupBox("🎧 Always-On Listening")
        ao_layout = QVBoxLayout()

        ao_status_row = QHBoxLayout()
        self._status_label = QLabel("⚪ Not active")
        self._status_label.setStyleSheet("font-size: 9pt; padding: 4px;")
        ao_status_row.addWidget(self._status_label)
        ao_status_row.addStretch()
        self._toggle_btn = QPushButton("▶️ Start Always-On")
        self._toggle_btn.setStyleSheet("padding: 6px 12px;")
        self._toggle_btn.clicked.connect(self._toggle_alwayson)
        ao_status_row.addWidget(self._toggle_btn)
        ao_layout.addLayout(ao_status_row)

        # Recognition engine
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Engine:"))
        self._engine_combo = QComboBox()
        self._engine_combo.addItems([
            "Local Whisper (offline, slower)",
            "OpenAI Whisper API (online, fast)",
        ])
        if settings.get('recognition_engine', 'local') == 'api':
            self._engine_combo.setCurrentIndex(1)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self._engine_combo, stretch=1)
        ao_layout.addLayout(engine_row)

        # Sensitivity
        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Mic sensitivity:"))
        self._sensitivity_combo = QComboBox()
        self._sensitivity_combo.addItems([
            "Low (noisy)", "Medium (normal)", "High (quiet)",
        ])
        saved_sensitivity = settings.get('alwayson_sensitivity', 'medium')
        idx = {'low': 0, 'medium': 1, 'high': 2}.get(saved_sensitivity, 1)
        self._sensitivity_combo.setCurrentIndex(idx)
        self._sensitivity_combo.currentIndexChanged.connect(self._on_sensitivity_changed)
        sens_row.addWidget(self._sensitivity_combo, stretch=1)
        ao_layout.addLayout(sens_row)

        # Commands-only toggle
        self._commands_only_cb = CheckmarkCheckBox(
            "Listen for commands only — don't type unmatched speech as dictation"
        )
        self._commands_only_cb.setToolTip(
            "When checked, Always-On fires voice commands but ignores any "
            "speech that doesn't match a command. Use Ctrl+Alt+D (or F9 in "
            "the editor) for one-off dictation."
        )
        self._commands_only_cb.setChecked(
            bool(settings.get('alwayson_commands_only', False)))
        self._commands_only_cb.toggled.connect(self._on_commands_only_toggled)
        ao_layout.addWidget(self._commands_only_cb)

        ao_focus_hint = QLabel(
            "ℹ️ <b>How it works:</b> commands and dictation go to whichever "
            "app is in the foreground when you speak. After turning Always-On "
            "on, click into Word, Trados, memoQ, or wherever you want the "
            "text to land — then speak. Press <b>Esc</b> to hide Sidekick."
        )
        ao_focus_hint.setTextFormat(Qt.TextFormat.RichText)
        ao_focus_hint.setWordWrap(True)
        ao_focus_hint.setStyleSheet(
            "font-size: 8pt; color: #555; background-color: #FFF8E1;"
            " border: 1px solid #FFE082; border-radius: 4px; padding: 6px;"
        )
        ao_layout.addWidget(ao_focus_hint)

        ao_tip = QLabel(
            "💡 OpenAI API mode is recommended for Always-On — much faster and "
            "more accurate. Requires an OpenAI API key (Settings → AI Settings)."
        )
        ao_tip.setWordWrap(True)
        ao_tip.setStyleSheet(
            "font-size: 8pt; color: #555; background-color: #E8F5E9;"
            " border-radius: 4px; padding: 6px;"
        )
        ao_layout.addWidget(ao_tip)

        alwayson_group.setLayout(ao_layout)
        layout.addWidget(alwayson_group)

        # --- Voice commands table -------------------------------------
        cmd_group = QGroupBox("🗣️ Voice Commands")
        cmd_layout = QVBoxLayout()

        cmd_info = QLabel(
            "Say a phrase to execute its action. If no command matches, the "
            "spoken text is inserted as dictation."
        )
        cmd_info.setStyleSheet("font-size: 8pt; color: #666;")
        cmd_info.setWordWrap(True)
        cmd_layout.addWidget(cmd_info)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Phrase", "Aliases", "Type", "Action", "Category"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setMinimumHeight(220)
        # Click any column header to sort by that column; click again to
        # reverse the sort. Sorting is disabled during _populate_table so
        # the Qt-known "items reshuffle while you're inserting" footgun
        # doesn't apply here.
        self._table.setSortingEnabled(True)
        cmd_layout.addWidget(self._table)

        cmd_btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ Add")
        add_btn.clicked.connect(self._add_command)
        cmd_btn_row.addWidget(add_btn)
        edit_btn = QPushButton("✏️ Edit")
        edit_btn.clicked.connect(self._edit_command)
        cmd_btn_row.addWidget(edit_btn)
        remove_btn = QPushButton("🗑️ Remove")
        remove_btn.clicked.connect(self._remove_command)
        cmd_btn_row.addWidget(remove_btn)
        cmd_btn_row.addStretch()
        reset_btn = QPushButton("🔄 Reset")
        reset_btn.clicked.connect(self._reset_commands)
        cmd_btn_row.addWidget(reset_btn)
        cmd_layout.addLayout(cmd_btn_row)

        cmd_group.setLayout(cmd_layout)
        layout.addWidget(cmd_group)

        # --- Speech recognition model --------------------------------
        model_group = QGroupBox("🤖 Speech Recognition Model")
        model_layout = QVBoxLayout()

        model_info = QLabel(
            "Whisper model size (larger = more accurate but slower):\n"
            "• tiny ~75 MB  • base ~142 MB (recommended)  • small ~466 MB\n"
            "• medium ~1.5 GB  • large ~2.9 GB"
        )
        model_info.setStyleSheet("font-size: 8pt; color: #555;")
        model_info.setWordWrap(True)
        model_layout.addWidget(model_info)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self._model_combo.setCurrentText(settings.get('model', 'base'))
        model_row.addWidget(self._model_combo)
        model_row.addSpacing(12)
        model_row.addWidget(QLabel("Max:"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setMinimum(3)
        self._duration_spin.setMaximum(60)
        self._duration_spin.setValue(settings.get('max_duration', 10))
        self._duration_spin.setSuffix(" sec")
        model_row.addWidget(self._duration_spin)
        model_layout.addLayout(model_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems([
            "Auto (use project target language)",
            "English", "Dutch", "German", "French", "Spanish",
            "Italian", "Portuguese", "Polish", "Russian",
            "Chinese", "Japanese", "Korean",
        ])
        self._lang_combo.setCurrentText(
            settings.get('language', 'Auto (use project target language)')
        )
        lang_row.addWidget(self._lang_combo, stretch=1)
        model_layout.addLayout(lang_row)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # --- Push-to-talk mode ---------------------------------------
        ptt_group = QGroupBox("🎯 Push-to-Talk Mode (F9)")
        ptt_layout = QVBoxLayout()

        ptt_info = QLabel(
            "Controls how the F9 key (and the Dictate button in the "
            "translation grid) start and stop recording. The global "
            "<b>Ctrl+Alt+D</b> hotkey always uses Toggle mode."
        )
        ptt_info.setTextFormat(Qt.TextFormat.RichText)
        ptt_info.setWordWrap(True)
        ptt_info.setStyleSheet("font-size: 8pt; color: #666;")
        ptt_layout.addWidget(ptt_info)

        ptt_row = QHBoxLayout()
        ptt_row.addWidget(QLabel("Mode:"))
        self._ptt_combo = QComboBox()
        self._ptt_combo.addItem(
            "Toggle (press F9 to start, press again to stop)", "toggle")
        self._ptt_combo.addItem(
            "Hold-to-talk (hold F9, release to stop)", "hold")
        saved_ptt = settings.get('pushtotalk_mode', 'toggle')
        for i in range(self._ptt_combo.count()):
            if self._ptt_combo.itemData(i) == saved_ptt:
                self._ptt_combo.setCurrentIndex(i)
                break
        self._ptt_combo.currentIndexChanged.connect(self._on_ptt_changed)
        ptt_row.addWidget(self._ptt_combo, stretch=1)
        ptt_layout.addLayout(ptt_row)

        ptt_group.setLayout(ptt_layout)
        layout.addWidget(ptt_group)

        # --- AutoHotkey integration ----------------------------------
        ahk_group = QGroupBox("⌨️ AutoHotkey Integration")
        ahk_layout = QVBoxLayout()
        ahk_info = QLabel(
            "Voice commands can trigger AutoHotkey scripts for system-level "
            "automation across Trados, memoQ, Word, and other apps."
        )
        ahk_info.setWordWrap(True)
        ahk_info.setStyleSheet("font-size: 8pt; color: #666;")
        ahk_layout.addWidget(ahk_info)

        ahk_row = QHBoxLayout()
        self._ahk_status_label = QLabel(self._ahk_status_text())
        self._ahk_status_label.setStyleSheet("font-size: 8pt;")
        ahk_row.addWidget(self._ahk_status_label)
        ahk_row.addStretch()
        scripts_btn = QPushButton("📂 Open Scripts Folder")
        scripts_btn.clicked.connect(self._open_ahk_folder)
        ahk_row.addWidget(scripts_btn)
        ahk_layout.addLayout(ahk_row)

        ahk_group.setLayout(ahk_layout)
        layout.addWidget(ahk_group)

        # --- Save button ---------------------------------------------
        save_btn = QPushButton("💾 Save AutoFingers Settings")
        save_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
            " padding: 8px; border: none;"
        )
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _load_settings(self) -> dict:
        loader = getattr(self._parent_app, 'load_dictation_settings', None)
        if callable(loader):
            try:
                return loader() or {}
            except Exception:
                return {}
        return {}

    def _ahk_status_text(self) -> str:
        check = getattr(self._parent_app, '_check_ahk_installed', None)
        if callable(check):
            try:
                return check()
            except Exception:
                return ""
        return ""

    def refresh(self):
        """Re-read voice commands and Always-On state from the parent app."""
        self._populate_table()
        self._sync_alwayson_from_listener()
        self._ahk_status_label.setText(self._ahk_status_text())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # ------------------------------------------------------------------
    # Voice commands CRUD
    # ------------------------------------------------------------------

    def _voice_command_manager(self):
        return getattr(self._parent_app, 'voice_command_manager', None)

    def _populate_table(self):
        mgr = self._voice_command_manager()
        # Suspend sorting during bulk insert so each setItem doesn't
        # trigger a re-sort that would scramble subsequent row indices.
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        if mgr is None:
            self._table.setSortingEnabled(was_sorting)
            return
        for cmd in mgr.commands:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(cmd.phrase))
            self._table.setItem(row, 1, QTableWidgetItem(
                ", ".join(cmd.aliases) if cmd.aliases else ""))
            self._table.setItem(row, 2, QTableWidgetItem(
                _TYPE_LABELS.get(cmd.action_type, cmd.action_type)))
            self._table.setItem(row, 3, QTableWidgetItem(
                cmd.description or cmd.action))
            self._table.setItem(row, 4, QTableWidgetItem(cmd.category))
        self._table.setSortingEnabled(was_sorting)

    def _add_command(self):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        dialog = VoiceCommandEditDialog(self)
        if dialog.exec():
            mgr.add_command(dialog.get_command())
            self._broadcast_table_refresh()

    def _edit_command(self):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        selected = self._table.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "Edit Command", "Please select a command to edit.")
            return
        row = selected[0].row()
        phrase_item = self._table.item(row, 0)
        if phrase_item is None:
            return
        phrase = phrase_item.text()
        cmd = next((c for c in mgr.commands if c.phrase == phrase), None)
        if cmd is None:
            return
        dialog = VoiceCommandEditDialog(self, cmd)
        if dialog.exec():
            mgr.remove_command(phrase)
            mgr.add_command(dialog.get_command())
            self._broadcast_table_refresh()

    def _remove_command(self):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        selected = self._table.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "Remove Command", "Please select a command to remove.")
            return
        row = selected[0].row()
        phrase_item = self._table.item(row, 0)
        if phrase_item is None:
            return
        phrase = phrase_item.text()
        confirm = QMessageBox.question(
            self, "Remove Command",
            f"Remove voice command '{phrase}'?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            mgr.remove_command(phrase)
            self._broadcast_table_refresh()

    def _reset_commands(self):
        reset_fn = getattr(self._parent_app, '_reset_voice_commands', None)
        if callable(reset_fn):
            reset_fn()
        self._broadcast_table_refresh()

    def _broadcast_table_refresh(self):
        """Refresh this tab via the parent app's central entry point so any
        future surfaces tied into _populate_voice_commands_table also update."""
        broadcast = getattr(
            self._parent_app, '_populate_voice_commands_table', None)
        if callable(broadcast):
            try:
                broadcast()
                return
            except Exception:
                pass
        # Fallback: refresh just our own table.
        self._populate_table()

    # ------------------------------------------------------------------
    # Always-On
    # ------------------------------------------------------------------

    def _toggle_alwayson(self):
        toggle = getattr(self._parent_app, '_toggle_alwayson_listening', None)
        if callable(toggle):
            toggle()

    def _sync_alwayson_from_listener(self):
        """Read live state from parent_app.voice_listener and reflect it."""
        listener = getattr(self._parent_app, 'voice_listener', None)
        if listener is not None and getattr(listener, 'is_listening', False):
            self.set_alwayson_status("listening")
        else:
            self.set_alwayson_status("stopped")

    def set_alwayson_status(self, status: str):
        """Update the Always-On UI for an externally-driven status change.

        Called from Supervertaler._update_alwayson_ui so this tab stays in
        sync with the grid toolbar button and the legacy settings panel.
        """
        if status in ("listening", "waiting"):
            self._status_label.setText("🟢 Listening for speech…")
            self._status_label.setStyleSheet(
                "font-size: 9pt; padding: 4px; color: #2E7D32;")
            self._toggle_btn.setText("⏹️ Stop Always-On")
            self._toggle_btn.setStyleSheet(
                "padding: 6px 12px; background-color: #FFCDD2;")
        elif status == "recording":
            self._status_label.setText("🔴 Recording…")
            self._status_label.setStyleSheet(
                "font-size: 9pt; padding: 4px; color: #C62828;")
        elif status == "processing":
            self._status_label.setText("⏳ Processing…")
            self._status_label.setStyleSheet(
                "font-size: 9pt; padding: 4px; color: #F57C00;")
        else:
            self._status_label.setText("⚪ Not active")
            self._status_label.setStyleSheet(
                "font-size: 9pt; padding: 4px;")
            self._toggle_btn.setText("▶️ Start Always-On")
            self._toggle_btn.setStyleSheet("padding: 6px 12px;")

    # ------------------------------------------------------------------
    # Settings handlers
    # ------------------------------------------------------------------

    def _set_dictation_keys(self, **keys):
        """Update one or more keys under prefs['ui']['dictation_settings'] in
        the unified settings JSON, preserving any unrelated keys."""
        load = getattr(self._parent_app, '_load_unified_settings', None)
        save = getattr(self._parent_app, '_save_unified_settings', None)
        if not callable(load) or not callable(save):
            return False
        try:
            all_settings = load()
            prefs = all_settings.setdefault('ui', {})
            ds = prefs.setdefault('dictation_settings', {})
            ds.update(keys)
            save(all_settings)
            return True
        except Exception:
            return False

    def _on_engine_changed(self, idx: int):
        self._set_dictation_keys(
            recognition_engine='api' if idx == 1 else 'local')

    def _on_sensitivity_changed(self, idx: int):
        sensitivity = ['low', 'medium', 'high'][idx]
        self._set_dictation_keys(alwayson_sensitivity=sensitivity)
        # Live-apply if a listener is currently running.
        listener = getattr(self._parent_app, 'voice_listener', None)
        if listener is not None and hasattr(listener, 'set_sensitivity'):
            try:
                listener.set_sensitivity(sensitivity)
            except Exception:
                pass

    def _on_ptt_changed(self, idx: int):
        mode = self._ptt_combo.itemData(idx) or 'toggle'
        self._set_dictation_keys(pushtotalk_mode=mode)

    def _on_commands_only_toggled(self, checked: bool):
        self._set_dictation_keys(alwayson_commands_only=bool(checked))

    def _save_settings(self):
        ok = self._set_dictation_keys(
            model=self._model_combo.currentText(),
            max_duration=self._duration_spin.value(),
            language=self._lang_combo.currentText(),
        )
        if ok:
            QMessageBox.information(
                self, "AutoFingers Settings", "Settings saved.")
        else:
            QMessageBox.warning(
                self, "AutoFingers Settings",
                "Couldn't save settings — check the log for details.")

    def _open_ahk_folder(self):
        fn = getattr(self._parent_app, '_open_voice_scripts_folder', None)
        if callable(fn):
            fn()
