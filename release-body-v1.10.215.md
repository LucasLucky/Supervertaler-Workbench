**Translation memory plumbing fixes.** This release rolls up three connected fixes on the TM write/read path that were causing `Bulk Operations → Update Active TMs` to write rows the editor's match panel couldn't see afterwards. Also new: the [Shared TM Bridge with Trados](https://help.supervertaler.com/workbench/translation-memory/shared-tm-bridge/) help page covering the Workbench side of the Phase 2 integration that shipped on the Trados-plugin side this week.

If you've been seeing confirmed segments fail to surface as TM matches, this is the build that fixes that class of failure.

### What was wrong

The "Target Translation Memory" dropdown in `Bulk Operations → Update Active TMs` was storing each TM's **integer primary key** as its combo data (e.g. `86` for `BRANTS`, `42` for `PATENTS`), which then got passed through to the SQLite insert as the row's `tm_id`. The editor's match panel, however, queries by **string `tm_id`** (e.g. `'brants_ursu_008_be_ep'`, `'patents'`). So every row written by `Update Active TMs` landed under a key the read path never asked about – the data was in the DB, just indexed under the wrong identifier.

The reason most users never noticed: the save-on-confirm path, which fires every time you confirm a segment, uses the string `tm_id` correctly. So newly-confirmed segments showed matches as expected. The mismatch only surfaced for segments confirmed **before** save-on-confirm could fire on them (e.g. segments confirmed in an older version, or with Write off, then later sent in bulk).

### What's in the fix

- **Bulk dropdown now stores the canonical string `tm_id`** (`Supervertaler.py:45721`). Future writes from `Update Active TMs` go to the same identifier the match panel queries.
- **Match-panel cache invalidates after a bulk write.** Previously, even when the write went to the correct key, segments already navigated to kept showing their pre-bulk-write match set until the project was closed and reopened. The bulk operation now calls `invalidate_translation_cache()` after the loop completes.
- **Project load no longer silently flips the global Write toggle.** `translation_memories.read_only` is a *per-TM* column, but project load was eagerly re-applying each project's saved Write state on every open. Opening project B would silently un-tick Write on a TM that project A had saved as read-only. The restore code now logs a note when the saved state disagrees with the current global state and leaves the global state alone.
- **Belt-and-braces guard on TU inserts.** `database_manager.add_translation_unit` and `add_translation_units_batch` now refuse writes whose `tm_id` has no corresponding row in `translation_memories`, accepting either the string `tm_id` form or the integer-PK-as-string form for backward compatibility. Prevents stray phantom-TM writes from any current or future caller.

### What's the same

Everything else. The Phase 1 Shared TM Bridge UI from v1.10.212 is unchanged. The i18n machinery, the editor, the termbase pipeline, AI translation, AutoPrompt, all imports and exports – no behaviour changes.

### Install

Download `Supervertaler-v1.10.215-Windows.zip` below, extract, and run `Supervertaler.exe`.

pip users: `pip install --upgrade supervertaler`

Full changelog: https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md

### Notes

- **Upgrading from an older release**: extract this new build over the same location as before. Your `D:\Supervertaler\` user-data folder is unchanged across the upgrade – TMs, termbases, prompts, settings all carry over.
- **If `Update Active TMs` has been silently writing under integer-PK identifiers in older releases**, those rows remain in the DB. They're inaccessible to the match panel (which queries by string `tm_id`) but harmless. A re-run of `Update Active TMs` on the same project after upgrading writes the canonical string-keyed copy so the affected segments start matching properly.
- **Shared TM Bridge with Trados (Phase 2)** shipped on the Trados-plugin side this week (Supervertaler for Trados v4.20.26 – v4.20.33). Tick `Bridge` on any TM in this version's TMs tab and it becomes attachable as a translation provider inside Trados Studio. See the [help page](https://help.supervertaler.com/workbench/translation-memory/shared-tm-bridge/) for the full flow.
