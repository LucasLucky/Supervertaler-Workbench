# CAT Tool Integration Overview

Supervertaler is designed to work alongside professional CAT (Computer-Assisted Translation) tools, not replace them. Use it as a **companion tool** for AI-powered translation within your existing workflow.

## Supported CAT Tools

| CAT Tool | Import Format | Export Format |
|----------|--------------|---------------|
| **memoQ** | Bilingual DOCX, XLIFF | Bilingual DOCX |
| **Trados Studio** | SDLPPX packages | SDLRPX return packages |
| **Phrase (Memsource)** | Bilingual DOCX | Bilingual DOCX |
| **CafeTran Espresso** | Bilingual table DOCX | Bilingual table DOCX |

## Why Use Supervertaler with CAT Tools?

### AI Translation Power

CAT tools have limited AI integration. Supervertaler lets you:
- Use multiple LLM providers (GPT-4, Claude, Gemini)
- Create custom translation prompts
- Batch translate with context awareness
- Leverage semantic TM search (Supermemory)

### Workflow Flexibility

- Translate offline with Ollama
- Work on files while others are locked in the CAT tool
- Quick review and post-editing without heavy software

## Typical Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR CAT TOOL                            │
│  (memoQ, Trados, Phrase, CafeTran)                         │
│                                                             │
│  1. Receive project from client                            │
│  2. Set up TM, termbases in CAT tool                       │
│  3. Export bilingual file or package                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    SUPERVERTALER                            │
│                                                             │
│  4. Import bilingual file                                  │
│  5. AI translate + post-edit                               │
│  6. Use Superlookup for research                           │
│  7. Export bilingual file                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    YOUR CAT TOOL                            │
│                                                             │
│  8. Import translations back                               │
│  9. Run QA checks                                          │
│  10. Deliver to client                                     │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Preserving Formatting

Supervertaler preserves CAT tool formatting tags:
- memoQ: `{1}`, `[2}`, `{MQ}` inline tags
- Trados: `<1>`, `</1>` numbered tags
- Tags are highlighted in the grid for visibility

### Segment Status

Segment statuses map between tools:
- **Draft** → Trados *Draft* / memoQ *Edited*
- **Confirmed** → Trados *Translated* ✓ / memoQ *Confirmed*
- **Approved** → Trados *Sign-off Approved* / memoQ *Reviewer 2 confirmed*

See [Segment Statuses](../editor/segment-statuses.md) for the full reference.

### Round-Trip Compatibility

Files exported from Supervertaler can be imported back into the CAT tool with:
- All translations preserved
- Status information maintained
- Formatting intact

## Choosing the Right Workflow

| Scenario | Recommended Workflow |
|----------|---------------------|
| **Full project in memoQ** | [memoQ Bilingual DOCX](memoq.md) |
| **Trados Studio package** | [SDLPPX/SDLRPX](trados.md) |
| **Phrase/Memsource project** | [Phrase Bilingual DOCX](phrase.md) |
| **CafeTran external view** | [CafeTran DOCX](cafetran.md) |
| **Standalone DOCX** | Direct import, no CAT tool needed |

---

## Tool-Specific Guides

<div class="sv-cards">
  <a class="sv-card" href="/cat-tools/memoq">
    <span class="sv-card-title">memoQ</span>
    <span class="sv-card-desc">memoQ workflow guide →</span>
  </a>
  <a class="sv-card" href="/cat-tools/trados">
    <span class="sv-card-title">Trados Studio</span>
    <span class="sv-card-desc">Trados workflow guide →</span>
  </a>
  <a class="sv-card" href="/cat-tools/phrase">
    <span class="sv-card-title">Phrase</span>
    <span class="sv-card-desc">Phrase workflow guide →</span>
  </a>
  <a class="sv-card" href="/cat-tools/cafetran">
    <span class="sv-card-title">CafeTran</span>
    <span class="sv-card-desc">CafeTran workflow guide →</span>
  </a>
</div>
