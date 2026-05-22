## Supervertaler Workbench v1.10.146

Two AI-export formats under one menu.

### Changed

- **The "📄 AI-Readable Markdown" export is now a submenu with two formats.** Under **File ▸ Export**, the single AI-Readable Markdown item is now a submenu offering **Markdown Table** (the existing bilingual `| n | source | target |` table) and **Labelled Segments** (a `[SEGMENT 0001]` block with language-labelled `NL:` / `EN:` lines). The labelled-segment format is more robust than a table when segments contain pipe characters, line breaks, or long sentences, and round-trips cleanly – pick whichever an AI agent handles best for the job.

### Added

- **"Labelled Segments" AI export.** A `[SEGMENT NNNN]` / language-labelled export format (previously built but unreachable from the menu) is now exposed under **File ▸ Export ▸ 📄 AI-Readable Markdown ▸ Labelled Segments…**, with configurable language codes, segment numbering, content mode (bilingual / source-only / target-only), and segment filters. Both AI exports read live grid state, so in-progress edits are included without needing to confirm the segment first.

### Install (Windows)

1. Download `Supervertaler-v1.10.146-Windows.zip` below.
2. Extract the whole folder (keep `Supervertaler.exe` next to its `_internal/` folder).
3. Run `Supervertaler.exe`. No installer needed. Optionally double-click "Add Supervertaler to Start Menu.cmd".

### Links

- Help: https://help.supervertaler.com/
- Full changelog: https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md
