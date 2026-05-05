"""AutoFingers tab – voice commands and dictation control panel.

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
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea, QFrame, QMessageBox, QSplitter, QMenu,
)

from modules.styled_widgets import CheckmarkCheckBox
from modules.voice_command_dialog import VoiceCommandEditDialog
from modules.help_system import Topics as HelpTopics, set_topic as set_help_topic


_TYPE_LABELS = {
    "internal": "Command",
    "keystroke": "Keystroke",
    "ahk_script": "AHK Script",
    "ahk_inline": "AHK Inline",
}

_DISABLED_COLOUR = QColor(170, 170, 170)

# Column indices
_COL_ENABLED  = 0
_COL_PHRASE   = 1
_COL_ALIASES  = 2
_COL_TYPE     = 3
_COL_ACTION   = 4
_COL_CATEGORY = 5


class AutoFingersTab(QWidget):
    """Voice commands + dictation control panel."""

    def __init__(self, parent_app, parent=None):
        super().__init__(parent)
        self._parent_app = parent_app
        self._build_ui()
        self._restore_layout()
        # Connect persistence signals after restore so restore doesn't trigger saves
        self._splitter.splitterMoved.connect(lambda pos, idx: self._save_layout())
        self._table.horizontalHeader().sectionResized.connect(
            lambda idx, old, new: self._save_layout())
        # Initial population
        self._populate_table()
        self._sync_alwayson_from_listener()
        set_help_topic(self, HelpTopics.AUTOFINGERS)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        settings = self._load_settings()

        # --- Header (full width) ---------------------------------------
        header = QLabel(
            "🎤 <b>AutoFingers</b> – voice commands and dictation.<br>"
            "Toggle Always-On to listen continuously, or press <b>F9</b> "
            "(or Ctrl+Alt+D anywhere) to dictate on demand."
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setWordWrap(True)
        header.setStyleSheet(
            "font-size: 9pt; color: #444; padding: 8px;"
            " background-color: #E3F2FD;"
        )
        outer.addWidget(header)

        # --- Main horizontal splitter ----------------------------------
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setChildrenCollapsible(False)
        outer.addWidget(self._splitter, 1)

        # ---- Left panel: settings (scrollable) -----------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_body = QWidget()
        left_layout = QVBoxLayout(left_body)
        left_layout.setContentsMargins(10, 10, 6, 10)
        left_layout.setSpacing(10)
        left_scroll.setWidget(left_body)
        self._splitter.addWidget(left_scroll)

        # Always-On Listening
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

        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Engine:"))
        self._engine_combo = QComboBox()
        # Order matters – first item is the default for fresh installs.
        # Item index → engine string mapping is fixed below in
        # _on_engine_changed and _engine_at_index.
        self._engine_combo.addItems([
            "Vosk (offline, free, commands only) — recommended",
            "faster-whisper (offline, dictates running text)",
            "OpenAI Whisper API (online, fast, dictates running text)",
        ])
        # Default to Vosk on fresh installs. Migrate the legacy
        # ``recognition_engine='local'`` setting to ``'faster_whisper'``.
        eng = settings.get('recognition_engine', 'vosk')
        if eng == 'local':
            eng = 'faster_whisper'
        idx_for_engine = {
            'vosk': 0,
            'faster_whisper': 1,
            'api': 2,
        }
        self._engine_combo.setCurrentIndex(idx_for_engine.get(eng, 0))
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self._engine_combo, stretch=1)
        ao_layout.addLayout(engine_row)

        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Mic sensitivity:"))
        self._sensitivity_combo = QComboBox()
        self._sensitivity_combo.addItems([
            "Low (noisy)", "Medium (normal)", "High (quiet)",
        ])
        saved_sensitivity = settings.get('alwayson_sensitivity', 'medium')
        self._sensitivity_combo.setCurrentIndex(
            {'low': 0, 'medium': 1, 'high': 2}.get(saved_sensitivity, 1))
        self._sensitivity_combo.currentIndexChanged.connect(self._on_sensitivity_changed)
        sens_row.addWidget(self._sensitivity_combo, stretch=1)
        ao_layout.addLayout(sens_row)

        self._commands_only_cb = CheckmarkCheckBox(
            "Listen for commands only – don't type unmatched speech as dictation"
        )
        self._commands_only_cb.setToolTip(
            "When checked, Always-On fires voice commands but ignores any "
            "speech that doesn't match a command. Use Ctrl+Alt+D (or F9 in "
            "the editor) for one-off dictation.\n\n"
            "Has no effect when the engine is set to Vosk – Vosk's grammar-"
            "constrained recogniser already only emits text for known "
            "command phrases; everything else is silently dropped."
        )
        self._commands_only_cb.setChecked(
            bool(settings.get('alwayson_commands_only', False)))
        self._commands_only_cb.toggled.connect(self._on_commands_only_toggled)
        ao_layout.addWidget(self._commands_only_cb)
        # Disable + grey out when Vosk is the active engine, since Vosk's
        # grammar mode is structurally "commands only" and the checkbox
        # would otherwise confuse the user. Re-enables when they switch
        # to faster-whisper or the OpenAI API.
        self._sync_commands_only_for_engine()

        ao_focus_hint = QLabel(
            "ℹ️ <b>How it works:</b> commands and dictation go to whichever "
            "app is in the foreground when you speak. After turning Always-On "
            "on, click into Word, Trados, memoQ, or wherever you want the "
            "text to land – then speak. Press <b>Esc</b> to hide Sidekick."
        )
        ao_focus_hint.setTextFormat(Qt.TextFormat.RichText)
        ao_focus_hint.setWordWrap(True)
        ao_focus_hint.setStyleSheet(
            "font-size: 8pt; color: #555; background-color: #FFF8E1;"
            " border: 1px solid #FFE082; border-radius: 4px; padding: 6px;"
        )
        ao_layout.addWidget(ao_focus_hint)

        # The "OpenAI API recommended" hint is only relevant when the user
        # has a Whisper engine selected. With Vosk (the new default) it's
        # actively misleading – Vosk is purpose-built for commands and
        # cheaper than the API – so we hide it under Vosk via
        # _sync_engine_dependent_widgets() below.
        self._ao_api_tip = QLabel(
            "💡 OpenAI API mode is recommended for Always-On if you also "
            "want running-text dictation in always-on – much faster and "
            "more accurate than the local Whisper fallback. Requires an "
            "OpenAI API key (Settings → AI Settings)."
        )
        self._ao_api_tip.setWordWrap(True)
        self._ao_api_tip.setStyleSheet(
            "font-size: 8pt; color: #555; background-color: #E8F5E9;"
            " border-radius: 4px; padding: 6px;"
        )
        ao_layout.addWidget(self._ao_api_tip)
        alwayson_group.setLayout(ao_layout)
        left_layout.addWidget(alwayson_group)

        # Whisper-specific settings group. Used by push-to-talk dictation
        # (always) and by Always-On when the engine is faster-whisper or
        # the OpenAI API. NOT used when Always-On engine is Vosk – Vosk
        # picks its own model from the Language setting below. We retitle
        # the group so it's obvious which engine these knobs control.
        self._whisper_group = QGroupBox(
            "🤖 faster-whisper Model (offline; used for push-to-talk and "
            "Always-On if engine = faster-whisper)"
        )
        model_layout = QVBoxLayout()
        model_info = QLabel(
            "faster-whisper model size (larger = more accurate but slower).\n"
            "Does not apply to the OpenAI Whisper API – that always uses "
            "whisper-1 server-side regardless of this setting.\n"
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
            settings.get('language', 'Auto (use project target language)'))
        lang_row.addWidget(self._lang_combo, stretch=1)
        model_layout.addLayout(lang_row)
        self._whisper_group.setLayout(model_layout)
        left_layout.addWidget(self._whisper_group)

        # Push-to-Talk
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

        # Engine indicator – tells the user explicitly which engine will
        # be used when they press Ctrl+Alt+D / F9. Push-to-talk dictation
        # produces running text, so Vosk (commands-only) is silently
        # routed to faster-whisper for this path. The OpenAI API engine
        # uses the API for both. _sync_engine_dependent_widgets keeps
        # this label in sync with the engine combo.
        self._ptt_engine_label = QLabel("")
        self._ptt_engine_label.setTextFormat(Qt.TextFormat.RichText)
        self._ptt_engine_label.setWordWrap(True)
        self._ptt_engine_label.setStyleSheet(
            "font-size: 8pt; color: #555; background-color: #FFF8E1;"
            " border: 1px solid #FFE082; border-radius: 4px; padding: 6px;"
        )
        ptt_layout.addWidget(self._ptt_engine_label)
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
        left_layout.addWidget(ptt_group)

        # AutoHotkey Integration
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
        left_layout.addWidget(ahk_group)

        # Save button
        save_btn = QPushButton("💾 Save AutoFingers Settings")
        save_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
            " padding: 8px; border: none;"
        )
        save_btn.clicked.connect(self._save_settings)
        left_layout.addWidget(save_btn)

        left_layout.addStretch()

        # Now that every engine-dependent widget has been instantiated,
        # run a final sync so the OpenAI tip / push-to-talk engine label
        # / commands-only checkbox visibility match the saved engine.
        # The earlier sync call (line ~185) only had access to a subset
        # of these widgets because Push-to-Talk and the Whisper group
        # hadn't been built yet.
        self._sync_engine_dependent_widgets()

        # ---- Right panel: voice commands -----------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 10, 10, 10)
        right_layout.setSpacing(6)
        self._splitter.addWidget(right_widget)

        cmd_label = QLabel("🗣️ <b>Voice Commands</b>")
        cmd_label.setTextFormat(Qt.TextFormat.RichText)
        cmd_label.setStyleSheet("font-size: 10pt; padding: 2px 0;")
        right_layout.addWidget(cmd_label)

        cmd_info = QLabel(
            "Say a phrase to execute its action. If no command matches, the "
            "spoken text is inserted as dictation. Double-click a row to edit."
        )
        cmd_info.setStyleSheet("font-size: 8pt; color: #666;")
        cmd_info.setWordWrap(True)
        right_layout.addWidget(cmd_info)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["", "Phrase", "Aliases", "Type", "Action", "Category"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(_COL_ENABLED,  QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_ENABLED, 28)
        for col in range(_COL_PHRASE, _COL_CATEGORY + 1):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_PHRASE,   160)
        self._table.setColumnWidth(_COL_ALIASES,  200)
        self._table.setColumnWidth(_COL_TYPE,      80)
        self._table.setColumnWidth(_COL_ACTION,   220)
        self._table.setColumnWidth(_COL_CATEGORY,  80)
        hh.setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        right_layout.addWidget(self._table, 1)

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
        right_layout.addLayout(cmd_btn_row)

        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 3)

    # ------------------------------------------------------------------
    # Layout persistence
    # ------------------------------------------------------------------

    def _save_layout(self):
        self._set_dictation_keys(autofingers_layout={
            'splitter': self._splitter.sizes(),
            'columns': [
                self._table.columnWidth(col)
                for col in range(_COL_PHRASE, _COL_CATEGORY + 1)
            ],
        })

    def _restore_layout(self):
        layout = self._load_settings().get('autofingers_layout', {})
        sizes = layout.get('splitter')
        if sizes and len(sizes) == 2:
            self._splitter.setSizes(sizes)
        widths = layout.get('columns')
        if widths and len(widths) == (_COL_CATEGORY - _COL_PHRASE + 1):
            for i, w in enumerate(widths):
                self._table.setColumnWidth(_COL_PHRASE + i, w)

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
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        if mgr is None:
            self._table.blockSignals(False)
            self._table.setSortingEnabled(was_sorting)
            return
        for cmd in mgr.commands:
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsSelectable
            )
            chk.setCheckState(
                Qt.CheckState.Checked if cmd.enabled else Qt.CheckState.Unchecked)
            self._table.setItem(row, _COL_ENABLED, chk)

            self._table.setItem(row, _COL_PHRASE, QTableWidgetItem(cmd.phrase))
            self._table.setItem(row, _COL_ALIASES, QTableWidgetItem(
                ", ".join(cmd.aliases) if cmd.aliases else ""))
            self._table.setItem(row, _COL_TYPE, QTableWidgetItem(
                _TYPE_LABELS.get(cmd.action_type, cmd.action_type)))
            self._table.setItem(row, _COL_ACTION, QTableWidgetItem(
                cmd.description or cmd.action))
            self._table.setItem(row, _COL_CATEGORY, QTableWidgetItem(cmd.category))

            if not cmd.enabled:
                self._set_row_colour(row, _DISABLED_COLOUR)

        self._table.blockSignals(False)
        self._table.setSortingEnabled(was_sorting)

    def _set_row_colour(self, row: int, colour):
        for col in range(_COL_PHRASE, _COL_CATEGORY + 1):
            item = self._table.item(row, col)
            if item is None:
                continue
            if colour is None:
                item.setData(Qt.ItemDataRole.ForegroundRole, None)
            else:
                item.setForeground(colour)

    def _on_item_changed(self, item):
        if item.column() != _COL_ENABLED:
            return
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        row = item.row()
        phrase_item = self._table.item(row, _COL_PHRASE)
        if phrase_item is None:
            return
        phrase = phrase_item.text()
        cmd = next((c for c in mgr.commands if c.phrase == phrase), None)
        if cmd is None:
            return
        enabled = item.checkState() == Qt.CheckState.Checked
        cmd.enabled = enabled
        mgr.save_commands()
        self._table.blockSignals(True)
        self._set_row_colour(row, None if enabled else _DISABLED_COLOUR)
        self._table.blockSignals(False)

    def _on_header_clicked(self, col: int):
        if col != _COL_ENABLED:
            return
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        # Enable all if any are disabled; disable all if all are enabled.
        target = any(not cmd.enabled for cmd in mgr.commands)
        self._set_rows_enabled(list(range(self._table.rowCount())), target)

    def _on_context_menu(self, pos):
        rows = self._selected_rows()
        if not rows:
            return
        menu = QMenu(self)
        act_enable  = menu.addAction("✅ Activate")
        act_disable = menu.addAction("⬜ Deactivate")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == act_enable:
            self._set_rows_enabled(rows, True)
        elif action == act_disable:
            self._set_rows_enabled(rows, False)

    def _selected_rows(self):
        return sorted({item.row() for item in self._table.selectedItems()})

    def _set_rows_enabled(self, rows: list, enabled: bool):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        changed = False
        self._table.blockSignals(True)
        for row in rows:
            phrase_item = self._table.item(row, _COL_PHRASE)
            if phrase_item is None:
                continue
            cmd = next(
                (c for c in mgr.commands if c.phrase == phrase_item.text()), None)
            if cmd is None:
                continue
            cmd.enabled = enabled
            chk = self._table.item(row, _COL_ENABLED)
            if chk:
                chk.setCheckState(
                    Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
            self._set_row_colour(row, None if enabled else _DISABLED_COLOUR)
            changed = True
        self._table.blockSignals(False)
        if changed:
            mgr.save_commands()

    def _on_row_double_clicked(self, row: int, col: int):
        self._edit_command_at_row(row)

    def _add_command(self):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        dialog = VoiceCommandEditDialog(self)
        if dialog.exec():
            mgr.add_command(dialog.get_command())
            self._broadcast_table_refresh()

    def _edit_command(self):
        selected = self._table.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "Edit Command", "Please select a command to edit.")
            return
        self._edit_command_at_row(selected[0].row())

    def _edit_command_at_row(self, row: int):
        mgr = self._voice_command_manager()
        if mgr is None:
            return
        phrase_item = self._table.item(row, _COL_PHRASE)
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
        phrase_item = self._table.item(row, _COL_PHRASE)
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
        # Mirrors the order of items added in __init__'s engine_combo block.
        engine_at_index = {0: 'vosk', 1: 'faster_whisper', 2: 'api'}
        self._set_dictation_keys(
            recognition_engine=engine_at_index.get(idx, 'vosk'))
        # Vosk is grammar-constrained → the "commands only" checkbox is
        # implicit. Whisper engines accept any speech → checkbox is meaningful.
        self._sync_commands_only_for_engine()

    def _sync_commands_only_for_engine(self):
        """Back-compat shim – delegates to the new unified sync method."""
        self._sync_engine_dependent_widgets()

    def _sync_engine_dependent_widgets(self):
        """Show / hide / update widgets whose relevance depends on the
        currently-selected Always-On engine.

        Mapping (engine_combo index → widget visibility / text):
          0 = Vosk:
            - "Listen for commands only" checkbox: HIDDEN (no-op for Vosk)
            - "OpenAI API recommended" tip:        HIDDEN (Vosk is the recommendation now)
            - Push-to-talk engine label:           "faster-whisper" (vosk routes there)
          1 = faster-whisper:
            - Checkbox: SHOWN
            - API tip:  HIDDEN (user already on local)
            - PT label: "faster-whisper"
          2 = OpenAI API:
            - Checkbox: SHOWN
            - API tip:  HIDDEN (user already on API)
            - PT label: "OpenAI Whisper API"
        """
        try:
            idx = self._engine_combo.currentIndex()
        except Exception:
            return

        is_vosk = (idx == 0)
        is_api = (idx == 2)

        try:
            self._commands_only_cb.setVisible(not is_vosk)
            self._commands_only_cb.setEnabled(not is_vosk)
        except Exception:
            pass

        try:
            # The OpenAI-API recommendation tip was historical advice from
            # before Vosk landed. Hide it across the board – the engine
            # selector itself now carries the recommendation ("Vosk —
            # recommended"), so the tip is just noise.
            self._ao_api_tip.setVisible(False)
        except Exception:
            pass

        # Tell the user explicitly which engine push-to-talk dictation
        # will use, since it doesn't always match the always-on engine.
        try:
            if is_api:
                txt = ("ℹ️ Push-to-talk dictation will use: <b>OpenAI Whisper API</b> "
                       "(running text, online, requires API key).")
            else:
                txt = ("ℹ️ Push-to-talk dictation will use: <b>faster-whisper</b> "
                       "(running text, offline). Vosk is commands-only, so "
                       "Ctrl+Alt+D / F9 always routes through Whisper for "
                       "running text – unless your engine above is set to OpenAI API.")
            self._ptt_engine_label.setText(txt)
        except Exception:
            pass

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
                "Couldn't save settings – check the log for details.")

    def _open_ahk_folder(self):
        fn = getattr(self._parent_app, '_open_voice_scripts_folder', None)
        if callable(fn):
            fn()
