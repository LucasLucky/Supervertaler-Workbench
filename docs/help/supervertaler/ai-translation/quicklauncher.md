# Supervertaler Assistant

The **Supervertaler Assistant** is a floating AI assistant window that gives you instant access to an AI chat, translation tools, text conversions, snippets, and your custom prompts -- from anywhere on your computer.

It replaces the old QuickLauncher popup menu with a persistent, resizable window featuring a chat panel on the left and an expandable action menu on the right.

## Opening the Assistant

### Inside Supervertaler

| Method | Shortcut |
|--------|----------|
| Keyboard shortcut | **Ctrl+Q** |

### From any application (system-wide)

| Method | Shortcut |
|--------|----------|
| Global hotkey | **Ctrl+Alt+A** |

Select text in any application (Word, memoQ, Trados, browser, etc.), then press **Ctrl+Alt+A**. The assistant opens with the selected text available for AI tools, text conversions, or snippets.

{% hint style="info" %}
If Ctrl+Alt+A doesn't work, another application may have claimed that shortcut. You can change it in **Settings > Keyboard Shortcuts > Global > Supervertaler Assistant**.
{% endhint %}

## Window Layout

The assistant has two panels separated by a draggable splitter:

- **Left: Chat panel** -- conversational AI chat with full markdown rendering, image paste support, and model selector
- **Right: Action menu** -- expandable categories with tools, prompts, snippets, and text conversions

The window size, position, and splitter proportions are remembered across sessions.

## Chat Panel

The chat panel is a full AI assistant with the same capabilities as the chat in the AI tab:

- Type messages and press **Enter** to send (Shift+Enter for new line)
- **Ctrl+V** to paste images from the clipboard (works with vision-capable models)
- Click the **model indicator** next to Send to switch AI provider/model on the fly
- **Context chips** (Document, TMs, Termbases, Files) toggle what data is included in the AI context. Right-click a chip for details or to attach files

### Shared Conversation

All chat views share the same conversation: the grid-side AI Assistant panel, the AI tab's Assistant sub-tab, and the floating assistant window all show the same messages and stay in sync.

## Action Menu

The right panel has expandable categories. Click a category heading to expand or collapse it. Use **arrow keys** to navigate and **Enter** to activate.

### Workbench Tools

- **QuickTrans** -- instant machine translation of the input text
- **Superlookup** -- concordance search across TMs, glossaries, and web resources

### Prompts

Your custom prompts from the Prompt Manager, grouped by folder. Clicking a prompt runs it against the input text and shows the AI response in the chat.

### Special Characters

Quick-insert symbols, arrows, primes, dashes and quotes, currency signs, legal symbols, maths operators, and bullet characters. Clicking an item copies it to the clipboard and (if launched from an external app) pastes it over your selection.

### Personal Snippets

Frequently used text snippets (e.g. phone numbers, addresses, boilerplate text). Clicking an item copies it to the clipboard and pastes it back.

### Text Conversions

Transform selected text:

| Conversion | Result |
|-----------|--------|
| Uppercase | SELECTED TEXT |
| Lowercase | selected text |
| Title Case | Selected Text |
| Sentence case | Selected text |
| Single curly quotes | 'Selected text' |
| Double curly quotes | "Selected text" |
| Round brackets | (Selected text) |
| Square brackets | [Selected text] |
| Remove soft hyphens | Strips invisible U+00AD characters |
| Double to single quotes | Replaces " with ' |
| Make bold | Wraps in `<b>...</b>` HTML tags |

**Direct action flow:** When launched from an external app via Ctrl+Alt+A, text conversions and snippets are *direct actions* -- the assistant hides immediately, returns focus to the source application, and pastes the result over your selection.

## Keyboard Navigation

| Key | Action |
|-----|--------|
| **Arrow keys** | Navigate menu items |
| **Enter** | Activate selected item (or expand/collapse a category) |
| **Tab** | Switch focus between the action menu and the chat input |
| **Escape** | Close the assistant |

## Context Chips

The context chips row appears above the chat input in all chat views:

| Chip | Left-click | Right-click |
|------|-----------|-------------|
| Document | Toggle document context | View project/language info |
| TMs | Toggle TM data inclusion | Browse available TMs |
| Termbases | Toggle termbase inclusion | Browse available termbases |
| Files | Toggle file context | Attach files or view attached files |

## Customising Hotkeys

You can change the default keyboard shortcuts in **Settings > Keyboard Shortcuts**:

| Default shortcut | Action |
|------------------|--------|
| **Ctrl+Q** | Open Supervertaler Assistant (in-app) |
| **Ctrl+Alt+A** | Open Supervertaler Assistant (global, from any app) |
| **Ctrl+M** | QuickTrans (direct, skip assistant) |

## Tips

- **Press Ctrl+Alt+A without selecting text** to open the assistant for general AI chat
- **Use text conversions** for quick formatting changes without leaving your current app
- **Right-click context chips** to browse and select specific TMs or termbases
- **Paste images** (Ctrl+V) to ask the AI about screenshots or diagrams
- The assistant works without a project open -- useful for general-purpose AI lookups
