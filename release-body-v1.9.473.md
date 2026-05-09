Headline: **translate any Okapi-supported format end-to-end** – IDML, HTML, XLIFF, PO, XLSX, PPTX through one unified menu, with byte-perfect round-trip preservation. Plus a polished Settings tab and a long string of bug fixes that didn't ship externally.

Five small versions accumulated since v1.9.468 – this release ships them all together.

## Highlights

### 🔗 Translate IDML, HTML, XLIFF, PO, XLSX, PPTX – round-trip via Okapi (v1.9.470, v1.9.471, v1.9.472)

A new menu pair handles everything Okapi can extract:

- **File → Import → Other format via Okapi…** — pick `.idml`, `.html` / `.htm`, `.xliff` / `.xlf`, `.po`, `.xlsx`, or `.pptx`. The bundled Okapi sidecar extracts the translatable content plus a structural skeleton, the segments load into the Workbench grid like any other project, and you translate as usual.
- **File → Export → Original format via Okapi…** — merges your translation back through the skeleton to reconstruct the original file format byte-perfectly.

The IDML use case in particular (raised in the public forum) now works without any user-facing Okapi step: drop in `.idml`, translate, drop out as `.idml`. Verified: opens cleanly in Adobe InDesign, all paragraph + character styles preserved, all 8 segments of an 8-segment story round-trip with their italic / regular runs intact.

Two non-trivial bugs were exposed and fixed during testing of this feature, before it ever shipped externally:

- **Multi-sentence paragraphs were silently dropping segments past the first** in the merge. A long paragraph that segmented into 3 sentences during extract round-tripped with only sentence 1 present in the output. Fixed by grouping per-sentence translations back to the parent text-unit at merge time. ([#v1.9.471](https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md#v19471--may-9-2026))
- **HTML inline elements (`<a>`, `<button>`, `<img>`) were leaking as raw `[#$dpNN]` placeholder text** into the output HTML, because the Okapi sidecar's tag-conversion only handled OOXML formatting codes. Fixed by extending the sidecar (v0.1.6 → v0.1.7) to emit generic `<gN>...</gN>` / `<xN/>` tags as a fallback for any inline code, with a matching round-trip path on the merge side. Generic – also benefits XLIFF and PO files with inline tags. ([#v1.9.472](https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md#v19472--may-9-2026))

📖 [Supported File Formats](https://supervertaler.gitbook.io/help/import-and-export/formats) (Workbench help docs).

### Settings UI: cleaner, calmer, no more accidental slider nudges (v1.9.469)

- **Mouse-wheel guard** on every slider, spinbox, and combo box across all settings tabs. They no longer steal wheel events while the cursor crosses them – scrolling the page just scrolls the page. Click into the widget first if you want the wheel to adjust it, same as macOS / Windows convention.
- **Consistent 1000 px width** on every settings tab, left-anchored against the sidebar. Stops the between-tab "page just resized" jump.
- **AI Settings** trimmed: dropped the giant "Free vs Paid API Access" info banner (already in the help docs), replaced with a clean page title.
- **LLM Provider radio buttons** finally look like radio buttons. The custom widget had been rendering as a square indicator with a checkmark – which made an early reviewer think the eight providers were multi-select when they're actually mutually exclusive. Visual only; behaviour was already correct.

### Help links from the Import/Export menus (v1.9.473)

Imports happen straight from a menu (no dialog), so the standard "?" help badge had nowhere to live. New **❓ Supported file formats (online help)…** entries now sit at the foot of both **File → Import** and **File → Export**, plus the standard "?" badge appears on the language-pair dialog of the new Okapi-via import.

## Install

- **Pip:** `pip install --upgrade supervertaler` (PyPI is at v1.9.473).
- **Cloned source / GitHub ZIP download:** `git pull` in your `Supervertaler-Workbench` folder, then run `python supervertaler.py` as before.
- **Windows standalone:** v1.9.473 Windows ZIP attached to this release.

## Full changelog

Per-version detail in [CHANGELOG.md](https://github.com/Supervertaler/Supervertaler-Workbench/blob/main/CHANGELOG.md). The chain ran:

- **v1.9.469** – Settings UI tidy-up
- **v1.9.470** – Other format via Okapi (initial)
- **v1.9.471** – fix multi-sentence merge dropping segments
- **v1.9.472** – fix `[#$dpNN]` placeholder leaks via sidecar v0.1.7
- **v1.9.473** – help links from Import/Export menus + Okapi dialog
