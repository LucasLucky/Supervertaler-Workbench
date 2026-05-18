## v1.10.82 – Termbase rename, TermLens parity with Trados, range-anchored comments

This release rolls up v1.10.42 → v1.10.82 (40 versions). Three big themes plus a long tail of fixes.

### 🏷️ "Glossary" is now "Termbase" everywhere

The terminology is unified across the Workbench UI, the help docs, and the URLs. Every dialog, tooltip, menu item, and status-bar message that used to say "glossary" now reads "termbase" – matching the Supervertaler for Trados plugin and the term used by every other CAT tool (memoQ, Trados Studio, MateCat). The help site at help.supervertaler.com had its `/workbench/glossaries/` paths renamed to `/workbench/termbases/` with Cloudflare 301 redirects so old bookmarks keep working.

### 🐛 Termbase direction bug fixed (the big one)

A user reported terms added during NL→EN translation work were saving "reversed" into an EN→NL termbase – the Dutch term landed in the column the termbase declared as English, and TermLens never surfaced them in the editor. Investigation found the same class of bug the Trados side hit pre-v4.19.22. The fix (v1.10.62): a new `_orient_term_for_termbase` helper that does per-termbase direction comparison and swaps source/target on save when the termbase runs opposite to the project. Includes a one-time "Reverse Source/Target" repair action for legacy bad data, and a comprehensive smoke test at `.dev/test_termbase_direction_orient.py`.

### 🔍 TermLens parity with the Trados TermLens – feature-complete

The Workbench TermLens panel now reads the same way as the Trados TermLens panel. Side-by-side comparisons should be hard to tell apart on a per-chip basis.

What was added across v1.10.73 → v1.10.82:

- **Synonyms shown in chip tooltips** ("Also: hinge mechanism" for source synonyms; target synonyms become their own clickable alternative chips with shortcut numbers).
- **Abbreviations / Definitions / URLs / Domain** now actually surface in the tooltip (the data was always in the schema; the index builder just wasn't loading the fields).
- **Sticky floating popup** replaces the Qt tooltip – bigger, stays open while you hover into it, clickable URLs, screen-edge-aware positioning.
- **Per-entry popup format** matching Trados – each entry from each termbase gets its own `source → target [TermbaseName] (ID N)` heading + metadata block, separated by horizontal rules.
- **Project termbase chips render pink**, background termbase chips render blue (chip sort now prioritises `ranking == 1` correctly via either `is_project_termbase` column or `termbase_activation.priority = 1`).
- **Forbidden terms** render red with strikethrough; **non-translatables** render amber.
- **Abbreviation-as-primary chip** – when a term matches via its abbreviation (`source_abbreviation` regex), the chip displays the abbreviation pair in purple with `target_abbreviation` as the primary text. Multi-variant supported via `|`-separated abbreviation field.
- **Corner indicators**: amber **ℹ** dot top-right when the entry has metadata; indigo **≡** circle when it has synonyms. Visible at a glance without hovering.
- **`+N` inline on the chip** (was a tiny gray label below).
- **"Editing:" dropdown** in the Edit Termbase Entry dialog – switch between sibling entries from other active termbases without closing and re-opening the dialog. Filtered to active termbases for the current project so users with dozens or hundreds of termbases see a clean, scoped list.

### 🔄 Cross-process refresh

When the same SQLite database is open in both Workbench and the Supervertaler for Trados plugin, changes from one used to require a project reload in the other.

- **🔄 refresh button** added to the TermLens widget header.
- **Automatic refresh** via `QFileSystemWatcher` on the active `supervertaler.db` – debounced 2 s + snapshot-gated (only rebuilds the in-memory termbase index when the termbase tables actually changed, so routine TM writes don't trigger spurious rebuilds).
- **Own-write integration** – every termbase-modifying path updates the snapshot, so own-writes don't cause redundant rebuilds when their `Changed` event fires.
- **F5 and 🔄 collapsed into one path** – `force_refresh_matches` now does the smart snapshot-gated rebuild + the full per-segment redraw. Press whichever is more convenient; they're the same operation.

### 💬 Range-anchored comments (Trados/memoQ parity)

Comments can now be anchored to specific character ranges in source or target text (not just whole segments). DOCX export anchors Word comments to those exact character ranges with run-splitting where needed; reviewer opens the file and sees the comment attached to the precise span. **Ctrl+M** = add comment (matches Trados/memoQ; previously was Ctrl+Shift+M).

### 🗂️ Termbases tab improvements

- **New "Created" column** in the terms grid showing when each entry was added (YYYY-MM-DD HH:MM, full timestamp on hover). Read-only.
- **Click any column header to sort** the whole termbase by that column. Smart defaults: text columns ascending, date columns descending (so a Created click immediately gives newest-first).
- **"Sort:" dropdown** for quick presets – "Source term (A→Z)", "Created (newest first)", "Modified (newest first)", etc.

### Other improvements

- **Diagnostic logging** added to the Edit Termbase Entry dialog (LOAD / SAVE / SAVE-MISMATCH lines) so any future "values look wrong" report can be triaged from the session log.
- **Termbase delete now correctly refreshes** – a new `_post_termbase_delete_refresh` helper consolidates the full refresh chain (cache clear + index rebuild + TermLens refresh) and is called from all 5 delete paths. Deleted terms used to keep appearing as phantom matches in TermLens until project reload; that's gone.
- **Voice dictation prompts** updated and several command-mode keystroke bindings cleaned up.
- **AI Assistant prompt-translation methodology** updated with translator's-comment conventions matching the Trados side.

### Trados plugin

Companion releases v4.19.113 + v4.19.114 ship the matching refresh button + auto-refresh on the Trados side (not part of this Workbench release – installed separately).

### Help docs

The help site at help.supervertaler.com has had the full `glossary` → `termbase` rename. Every page label, URL, sidebar entry, and cross-product link is updated. Old `/glossaries/` URLs 301-redirect.

### Download

[Supervertaler-v1.10.82-Windows.zip](https://github.com/Supervertaler/Supervertaler-Workbench/releases/download/v1.10.82/Supervertaler-v1.10.82-Windows.zip) (≈508 MB)

Extract the ZIP and run `Supervertaler.exe` – keep the EXE next to its `_internal/` folder. Pip install path: `pip install -U supervertaler==1.10.82`.
