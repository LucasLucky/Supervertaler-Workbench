# Translating Supervertaler Workbench

Thanks for considering a translation contribution! This guide covers the workflow for adding a new language or improving an existing one.

## What's translatable today (v1.10.207)

The **MVP infrastructure** ships with these areas wrapped for translation:

- **Menu bar** – every menu title, submenu title, menu item, and action tooltip
- **Settings tabs** – the tab labels (⚙️ General, 🤖 AI Settings, 🎤 Voice, etc.)
- **General settings group titles** – Startup Settings, 🌐 Language, Privacy, etc.

That's roughly **180 strings**. Dialog bodies, error messages, status-bar text, and per-cell tooltips remain in English in this first pass. Subsequent passes will widen coverage.

## How translation works

Supervertaler uses **Qt Linguist `.ts` files** — XML files that pair each English source string with its translation. One file per locale lives in this folder:

```
translations/
├── supervertaler_template.ts   <- regenerated from source; never edited by hand
├── supervertaler_zh_CN.ts      <- Simplified Chinese
├── supervertaler_zh_TW.ts      <- Traditional Chinese
└── supervertaler_pl.ts         <- Polish
```

At startup, Supervertaler reads the `.ts` matching the user's selected language (Settings → General → 🌐 Language) and applies it. Unfinished or missing translations fall through to English — partial coverage is fine.

## Adding a new language

1. **Pick the locale code** following Qt's `language[_TERRITORY]` form: `de`, `fr`, `es`, `ja`, `zh_CN`, `zh_TW`, `pt_BR`, etc.
2. **Copy the template** as a starting point:

   ```bash
   cp translations/supervertaler_template.ts translations/supervertaler_<your_locale>.ts
   ```

3. **Translate the strings** (see below).
4. **Add your locale to the dropdown** by editing `modules/i18n.py` → `SUPPORTED_LOCALES`. Insert a tuple `("xx_XX", "Native name — English name")` in the list. (Already present for most major languages.)
5. **Commit your `.ts` file** and open a PR.

The Settings dropdown automatically marks locales without a `.ts` as `[no translation yet]`, so dropping in a new `.ts` makes the language available immediately on the next launch.

## Translating with Qt Linguist (recommended)

[Qt Linguist](https://doc.qt.io/qt-6/linguist-translators.html) is a free GUI tool that makes translation comfortable: side-by-side source/target panes, context, finished-flag tracking, and basic glossary support.

1. Install Qt Linguist (ships with the Qt SDK; also available as `pyside6-essentials` for a smaller install).
2. Open `translations/supervertaler_<your_locale>.ts` in Qt Linguist.
3. Translate each string. Mark it as **finished** (green tick) when you're confident — unfinished strings fall through to English at runtime.
4. Save. Commit the `.ts`.

## Translating by hand (no Qt Linguist)

The `.ts` format is plain XML. Each string looks like:

```xml
<message>
    <location filename="..\Supervertaler.py" line="9698" />
    <source>&amp;Project</source>
    <translation type="unfinished" />
</message>
```

To translate:
1. Replace `<translation type="unfinished" />` with `<translation>Your translation</translation>`.
2. XML-escape any `&` in your translation as `&amp;` (mnemonic letters like `&P`, `&O`, `&N` use the same syntax — they become Alt-shortcut hints in the menu).
3. Keep emoji and any leading whitespace from the source.

Example:

```xml
<message>
    <location filename="..\Supervertaler.py" line="9698" />
    <source>&amp;Project</source>
    <translation>项目(&amp;P)</translation>
</message>
```

## Things to know about mnemonics

- `&` in a string marks the next letter as a keyboard mnemonic (Alt+letter accelerator on Windows/Linux). `&Edit` → underlined **E**dit, activated by Alt+E.
- Keep mnemonics in your translation. Place them so the underlined letter feels natural — Chinese conventions often put the mnemonic in parentheses after the term: `编辑(&E)`.
- Avoid mnemonic collisions within the same menu (two items both using `&S`, for example). Qt will still work but only one will respond to the shortcut.

## Things to know about formatting

- Strings with `\n` should keep the newline.
- Emoji (📁 🔍 ⚙️ etc.) should stay in the translation — they're part of the visual identity.
- Don't translate format placeholders like `{0}` or `%1` — keep them verbatim.

## Testing your translation

1. Run Supervertaler.
2. Settings → General → 🌐 Language → pick your locale.
3. Restart Supervertaler.
4. Open the menu bar, browse the Settings tabs — your translations should appear.
5. Untranslated strings remain in English; that's expected for partial coverage.

If a string doesn't appear, common causes:

- `<translation>` still has `type="unfinished"` — remove that attribute.
- `&` in the translation isn't XML-escaped (file would fail to load).
- The source string in your `.ts` doesn't match the source in the codebase exactly (case, punctuation, spaces matter).

## Regenerating the template

Whenever new translatable strings are added to the codebase, the template needs refreshing so all locales can pick them up:

```bash
pylupdate6 Supervertaler.py modules/i18n.py --ts translations/supervertaler_template.ts
```

Then re-merge the template into each locale file (Qt Linguist does this from File → Update, or you can copy unfinished entries by hand). New strings appear as `type="unfinished"`; existing translations are preserved.

## Questions

Open an issue tagged `i18n` on the [Supervertaler-Workbench tracker](https://github.com/Supervertaler/Supervertaler-Workbench/issues).
