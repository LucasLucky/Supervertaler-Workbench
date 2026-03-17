# Machine Translation

Superlookup’s **Machine Translation** tab can query multiple MT providers and show results side-by-side.

## Providers

Superlookup supports these MT providers (depending on your settings/API keys):

- DeepL
- Google Translate
- Microsoft Translator
- Amazon Translate
- ModernMT
- MyMemory (free)

## Configure providers

At the top of the MT tab you’ll see a provider status summary:

- ✅ **Active** providers
- ⏸️ **Disabled** providers
- ❌ Providers missing an API key

Click **Configure in Settings** to jump to **Settings → MT Settings**.

## Language behavior

- If **From/To** are set, Superlookup uses that language pair for MT.
- If **From/To = Any**, Superlookup falls back to the project language pair.

## Copying results

- Successful results show a **📋 copy button**.
- You can also **double-click** a result row to copy the translation.

::: info
If a provider call fails, Superlookup shows the error message in red.
:::
