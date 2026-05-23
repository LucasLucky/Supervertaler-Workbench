**Supervertaler Workbench v1.10.166** — focused improvements across grid loading performance, import responsiveness, the AutoPrompt flow, and the Prompt Manager layout. 20 commits (v1.10.147 → v1.10.166) condensed into the highlights below; the full per-version detail is in `CHANGELOG.md`.

## Prompt Manager: contextual "?" help link (v1.10.166)

- **Small circular `?` button in the top-right of the Prompt Manager's left panel** — follows the same convention used in every other dialog and section across the Workbench. One click opens the Prompt Manager help page (`help.supervertaler.com/workbench/ai-translation/prompt-library/`) in your default browser. Uses the shared `HelpButton` widget so the styling matches every other in-app `?` affordance.

## Grid & import performance (v1.10.147 → v1.10.153)

- **Page-aware grid loading.** Off-page rows now get cheap placeholders; heavy `QTextEdit` widgets are installed only for rows on the current page and lazy-populated on navigation. Major initial-load speedup on 1000+ segment projects. Based on the same optimisation Hans Lenting applied in his Simpelvertaler fork (which in turn draws on Piotr Bienkowski's [XLIFF2Editor](https://github.com/piotr-bienkowski/XLIFF2Editor)).
- **Idle-time prefetch of the next page** in 10-row batches via `QTimer`, so Next-click / Ctrl+Enter-out-of-last-segment is usually instant rather than triggering a 200-row populate.
- **Progress dialog spans the whole SDLXLIFF import** — no more "Not Responding" during grid build. Shared `_ImportProgressDialog` helper now wraps **all 14 project-import paths** (was 3 of 18 in the audit) — SDLPPX, standalone SDLXLIFF, SDLXLIFF folder, memoQ bilingual / RTF / XLIFF, CafeTran, Trados bilingual, Phrase, DéjàVu, review-table, plain text, multi-file folder.
- **Trados Package Info dialog is height-capped with a scrollable file list**, so 40+ file packages no longer push Import/Cancel off the screen.
- **Switching pagination to "All" on a multi-thousand-segment project** now shows a progress dialog instead of freezing.
- **Cell-clicks no longer freeze for 2-34 seconds after a non-DOCX import** — the in-memory termbase index builder (`_start_termbase_batch_worker`) and TM/MT/LLM prefetch were only wired into the DOCX import path. Now in all 14 project-import paths via a shared `_finalise_import_with_indexes()` helper.
- Several smaller perf fixes: redundant per-row `apply_font_to_grid` pass skipped on fresh load (~9 s on a 479-segment SDLXLIFF), duplicate `auto_resize_rows()` call in import path removed, auto-pagination threshold lowered 2000 / 500 → 1000 / 200, SDLXLIFF parser now skips empty `<trans-unit>` and `<mrk>` segments.

## AutoPrompt overhaul (v1.10.156 → v1.10.158)

- **Worker-thread progress dialog** during generation. The `chat_backend.send_ai_request` call now runs on a dedicated `_AutoPromptWorker` `QThread`, so the window stays responsive instead of freezing for 1-3 minutes on reasoning-capable models (Opus 4.7, GPT-5).
- **Save dialog with name + folder fields** after generation. Pre-fills name with the current project's name; folder dropdown defaults to **Translate** and lists every existing top-level folder in your prompt library (editable for new folder names).
- Custom Prompt activation now **persists across restart** immediately (was previously lost if you restarted inside the 5-minute auto-save window).
- Custom Prompt UI label refreshes immediately after activation (no more "[None selected]" lingering after AutoPrompt completes).
- Generated prompts now go to the **AutoPrompt** folder by default (was "Supervertaler Sidekick Prompts" — Sidekick was retired in v1.10.4).
- Folder dropdown fix: now lists existing folders correctly on Windows (was only showing the hardcoded "Translate" entry).
- Renaming the active Custom Prompt no longer silently breaks restoration on next project open — basename-match fallback restores the activation when exactly one prompt in the library has the same filename stem.

## Prompt Manager layout (v1.10.159 → v1.10.165)

The Active Configuration panel was restructured into **five clearly-numbered, visually-distinct sections**, each with a coloured title strip:

1. **System Prompt** — built-in instructions, edited in Settings
2. **Custom Prompt** — your project-specific instructions, in a two-column split (active prompt + Load External / Clear on the left; ✨ AutoPrompt button on the right)
3. **Attached Prompts** — optional extras with Clear All Attachments inside
4. **Image Context** — visual references for the AI
5. **Prompt Library** — all your saved prompts (button row + tree, all wrapped in one styled section)

Plus a single **👁 Preview Combined** button at the very bottom — one place to see what will actually be sent to the AI. Captions for each section are now consistently at the bottom, prefixed with a blue ⓘ info icon. Redundant "System Prompts" button removed from the library toolbar (the same destination is one extra click away via Section 1's View System Prompt dialog).

## Tab-navigation bug audit + fixes (v1.10.160 → v1.10.161)

- **"View System Prompt" → "Edit in Settings" now goes to Settings** instead of SuperLookup. The button hard-coded `main_tabs.setCurrentIndex(4)` with a comment claiming that was Settings, but SuperLookup, Clipboard Manager, and Voice have been inserted between AI and Settings since the code was written.
- **"View System Prompt" dialog is now resizable** (was a fixed-size `QMessageBox.setDetailedText` that was practically unreadable on multi-page system prompts).
- **MT-status panel's "Open MT Settings" jump** now lands on Settings → MT Settings instead of SuperLookup → Voice.
- Added `_switch_main_tab` and `_switch_settings_subtab` helpers that look up tabs by label substring; all 8 hard-coded tab-navigation call sites now go through them, so future tab insertions can't silently re-break navigation.

## Other quality-of-life fixes

- **Double-tap Shift no longer fires while typing acronyms** ("AB", "OK", "BRANTS", etc.). The detector now tracks whether any non-Shift key was pressed during the hold; if so, that release is consumed and ignored for tap detection.
- **"Auto-generate markdown for imported documents" moved from AI Settings to General Settings** (Settings → ⚙️ General → 📥 Document Import). The trigger is import-time, not AI-time, so it belongs there.
- **Stale "Project Resources" UI path references fixed** in two help strings (the Image Context caption and the "No TMs Activated" warning). There's no "Project Resources" tab — the references were from an old tab layout.

## Install

Download the Windows ZIP attached below, extract, and run `Supervertaler.exe`. Double-click `Add Supervertaler to Start Menu.cmd` (also in the ZIP) if you'd like a Start Menu shortcut.

## Links

- Full changelog: [`CHANGELOG.md`](https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md)
- Help site: <https://help.supervertaler.com>
- Project home: <https://supervertaler.com>
