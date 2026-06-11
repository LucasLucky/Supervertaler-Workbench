Changes since v1.10.259 (v1.10.260 – v1.10.261).

## Fixed

- **Importing a document keeps the project's language pair – no more silent switch to English.** The Import Document / Import Plain Text / Import Folder dialogs offered only a hardcoded list of 12 languages; if a project's source or target language wasn't in it (e.g. Slovak), the dialog couldn't pre-select it and quietly fell back to the first item, English – so a Russian→Slovak project imported as Russian→English. The dialogs now use the full canonical language set (52 languages) and pre-selection is robust (matched on the base code, and the language is added if it's somehow not listed), so a project's language pair can never be silently dropped to English again. *(v1.10.261)*
- **Prompt Manager (AI tab) no longer clips on shorter screens.** Sections 1–4 (System / Custom / Attached Prompts / Image Context) sat in a box with a hard-coded minimum height that let it shrink below its content on short laptop screens. The left column is now wrapped in a scroll area, so every section stays fully visible and the column scrolls instead of compressing. Normal/tall screens are unchanged. *(v1.10.260)*

Full per-version detail in [CHANGELOG.md](https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md).

## Install

- **Windows (standalone):** download `Supervertaler-v1.10.261-Windows.zip` below, extract it, and run `Supervertaler.exe` **from the extracted folder** (keep it next to the `_internal/` directory).
- **macOS:** download `Supervertaler-v1.10.261-macOS.dmg` below, open it, and drag **Supervertaler** to your Applications folder. It's signed and notarised, so it opens without Gatekeeper warnings.
