# Translating Supervertaler Workbench

Thanks for considering a translation contribution! This guide covers the workflow for adding a new language or improving an existing one.

## What's translatable today (v1.10.208)

The **MVP infrastructure** ships with these areas wrapped for translation:

- **Menu bar** – every menu title, submenu title, menu item, and action tooltip
- **Settings tabs** – the tab labels (⚙️ General, 🤖 AI Settings, 🎤 Voice, etc.)
- **General settings group titles** – Startup Settings, 🌐 Language, Privacy, etc.

That's roughly **180 strings**. Dialog bodies, error messages, status-bar text, and per-cell tooltips remain in English in this first pass. Subsequent passes will widen coverage.

## File format: XLIFF 1.2

Supervertaler ships translation files in **XLIFF 1.2** – the industry-standard interchange format that every CAT tool in regular use eats natively. You don't need any special editor: open the `.xlf` in **Trados Studio, memoQ, Phrase, OmegaT, Wordfast, or Supervertaler Workbench itself**.

One file per locale, in this folder:

```
translations/
├── supervertaler_template.xlf   <- regenerated from source; never edited by hand
├── supervertaler_zh_CN.xlf      <- Simplified Chinese
├── supervertaler_zh_TW.xlf      <- Traditional Chinese
└── supervertaler_pl.xlf         <- Polish
```

At startup, Supervertaler reads the `.xlf` matching the user's selected language (Settings → General → 🌐 Language) and applies it. Targets marked `needs-translation` (the default for untranslated entries) fall through to English – partial coverage is fine.

## Adding a new language

1. **Pick the locale code** following Qt's `language[_TERRITORY]` form: `de`, `fr`, `es`, `ja`, `zh_CN`, `zh_TW`, `pt_BR`, etc. (XLIFF metadata uses the hyphenated equivalent internally; Supervertaler handles the conversion.)
2. **Copy the template** as a starting point:

   ```bash
   cp translations/supervertaler_template.xlf translations/supervertaler_<your_locale>.xlf
   ```

3. **Set the target language** on the `<file>` element near the top of the new file:

   ```xml
   <file ... target-language="zh-CN" ...>
   ```

4. **Translate the strings** (see below).
5. **Add your locale to the dropdown** by editing `modules/i18n.py` → `SUPPORTED_LOCALES`. Insert a tuple `("xx_XX", "Native name — English name")` in the list. (Already present for most major languages.)
6. **Commit your `.xlf` file** and open a PR.

The Settings dropdown automatically marks locales without a `.xlf` as `[no translation yet]`, so dropping in a new `.xlf` makes the language available immediately on the next launch.

## Translating in your CAT tool

Pick any CAT tool that handles XLIFF (they all do). Open `translations/supervertaler_<your_locale>.xlf` as a regular source file. You'll see the English source on the left and an empty target column on the right – the same workflow as any other XLIFF job.

**Workbench itself**: File → Import → Bilingual XLIFF (.sdlxliff or generic). Supervertaler's XLIFF is the standard variant, not SDLXLIFF or MQXLIFF, but the generic XLIFF importer handles it.

**Trados Studio**: File → Open → Translate Single Document → select the `.xlf`. Studio recognises XLIFF 1.2 out of the box.

**memoQ**: Project → Import documents → select the `.xlf`. Choose the standard XLIFF filter.

**Phrase**: Upload as a regular bilingual file.

**OmegaT**: Drop into the project's `source/` folder.

When translating:
- Translate every segment.
- Mark each as **confirmed / translated / approved** (the term varies by tool) so the target's `state` attribute becomes `translated`. Unconfirmed targets are loaded by Workbench but the state attribute stays as `needs-translation`, which Workbench skips.
- Save / export back to XLIFF. Most tools preserve the original structure cleanly.

## Translating by hand (no CAT tool)

The `.xlf` format is XML. Each string looks like:

```xml
<trans-unit id="SupervertalerQt.&amp;Project">
  <source>&amp;Project</source>
  <target state="needs-translation"></target>
  <context-group purpose="location">
    <context context-type="x-qt-context">SupervertalerQt</context>
    <context context-type="sourcefile">Supervertaler.py</context>
    <context context-type="linenumber">9698</context>
  </context-group>
</trans-unit>
```

To translate:
1. Put your translation inside the `<target>` element.
2. Change `state="needs-translation"` to `state="translated"`.
3. XML-escape any `&` in your translation as `&amp;` (mnemonic letters like `&P`, `&O`, `&N` use the same syntax – they become Alt-shortcut hints in the menu).

Example:

```xml
<trans-unit id="SupervertalerQt.&amp;Project">
  <source>&amp;Project</source>
  <target state="translated">项目(&amp;P)</target>
  <context-group purpose="location">
    <context context-type="x-qt-context">SupervertalerQt</context>
    <context context-type="sourcefile">Supervertaler.py</context>
    <context context-type="linenumber">9698</context>
  </context-group>
</trans-unit>
```

## Things to know about mnemonics

- `&` in a string marks the next letter as a keyboard mnemonic (Alt+letter accelerator on Windows/Linux). `&Edit` → underlined **E**dit, activated by Alt+E.
- Keep mnemonics in your translation. Place them so the underlined letter feels natural – Chinese conventions often put the mnemonic in parentheses after the term: `编辑(&E)`.
- Avoid mnemonic collisions within the same menu (two items both using `&S`, for example). Qt will still work but only one will respond to the shortcut.

## Things to know about formatting

- Strings with `\n` should keep the newline.
- Emoji (📁 🔍 ⚙️ etc.) should stay in the translation – they're part of the visual identity.
- Don't translate format placeholders like `{0}` or `%1` – keep them verbatim.

## Testing your translation

1. Run Supervertaler.
2. Settings → General → 🌐 Language → pick your locale.
3. Restart Supervertaler.
4. Open the menu bar, browse the Settings tabs – your translations should appear.
5. Untranslated strings remain in English; that's expected for partial coverage.

If a string doesn't appear, common causes:
- `<target>` still has `state="needs-translation"` – change to `state="translated"`.
- `&` in the translation isn't XML-escaped (file would fail to load).
- The source string in your `.xlf` doesn't match the source in the codebase exactly (case, punctuation, spaces matter).

## Regenerating the template

Whenever new translatable strings are added to the codebase, the template needs refreshing so all locales can pick them up:

```bash
python tools/extract_strings.py
```

That walks the AST of `Supervertaler.py` + `modules/i18n.py`, finds every `self.tr(...)` call, and writes the result to `translations/supervertaler_template.xlf`. CAT tools' "update from source" or "merge new strings" workflows can then propagate new entries into existing locale files while preserving completed translations.

## Why XLIFF? (Brief)

Three formats were considered for translation files:

| Format | Why we didn't pick it |
|---|---|
| Qt Linguist `.ts` (XML) | Qt-only tool, niche outside Qt circles |
| GNU gettext `.po` | Broadly supported but ergonomics vary by CAT tool, less familiar to translators |
| **XLIFF 1.2** ✓ | Industry standard. Every CAT tool eats it natively. Workbench can dogfood its own format. |

## Questions

Open an issue tagged `i18n` on the [Supervertaler-Workbench tracker](https://github.com/Supervertaler/Supervertaler-Workbench/issues).
