# Supervertaler Workbench

[![PyPI version](https://badge.fury.io/py/supervertaler.svg)](https://pypi.org/project/Supervertaler/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Professional AI-enhanced translation workbench** with multi-LLM support (GPT-4, Claude, Gemini, Mistral, Ollama), translation memory, glossary management, and seamless CAT tool integration (memoQ, Trados, CafeTran, Phrase, Déjà Vu).

**Latest release:** v1.9.393 – Non-translatables unified with the termbase model. The standalone "🚫 Non-Translatables" tab and `.svntl` file system are gone; NTs are now flagged on individual termbase entries via the `is_nontranslatable` column (the same convention the Trados plugin already uses), so both products share storage when pointed at the same database. Mark a term as NT from the term editor's new checkbox, or from the grid via the existing right-click "Add to Non-Translatables" / Ctrl+Alt+N — both now write to the project (or first writable activated) termbase.

---

## Installation

```bash
pip install supervertaler
supervertaler
```

Or run from source:

```bash
git clone https://github.com/Supervertaler/Supervertaler-Workbench.git
cd Supervertaler
pip install -r requirements.txt
python Supervertaler.py
```

### macOS Standalone App (.dmg)

macOS will block the app on first launch because it is not signed with an Apple Developer certificate. To allow it:

1. **Double-click** `Supervertaler.app` — macOS will show a warning
2. Open **System Settings > Privacy & Security**
3. Scroll down and click **"Open Anyway"** next to the Supervertaler message
4. Confirm when prompted — the app will launch normally from now on

---

## Key Features

- **Supervertaler Sidekick** - System-wide floating AI assistant (Ctrl+Alt+A from any app) with chat, text conversions, snippets, and prompt library actions
- **Multi-LLM AI Translation** - OpenAI GPT-4/5, Anthropic Claude, Google Gemini, Mistral AI, Local Ollama, OpenRouter (200+ models)
- **Translation Memory** - Fuzzy matching TM with TMX import/export
- **Glossary System** - Project/Background glossary highlighting with forbidden term marking
- **Superlookup** - Unified concordance search across TM, glossaries, MT, and web resources
- **CAT Tool Integration** - memoQ XLIFF, Trados SDLPPX/SDLRPX, CafeTran, Phrase, Déjà Vu X3
- **Voice Commands** - Hands-free translation with OpenAI Whisper
- **Document Support** - DOCX, bilingual DOCX/RTF, PDF, Markdown, plain text + built-in [Okapi Framework](https://okapiframework.org/) sidecar for industry-standard file extraction and round-trip export with full formatting preservation

---

## Documentation

| Resource | Description |
|----------|-------------|
| [Online Manual](https://supervertaler.gitbook.io/help/) | Quick start, guides, and troubleshooting |
| [Changelog](CHANGELOG.md) | Complete version history |
| [Keyboard Shortcuts](docs/guides/KEYBOARD_SHORTCUTS.md) | Shortcut reference |
| [FAQ](FAQ.md) | Common questions |
| [Similar Apps](docs/SIMILAR_APPS.md) | CotranslatorAI, TransAIde, TWAS Suite, and other translation tools |
| [Website](https://supervertaler.com) | Project homepage |

---

## Requirements

- Python 3.10+
- PyQt6
- Windows, macOS, or Linux

---

## Contributing

- [Report bugs](https://github.com/Supervertaler/Supervertaler-Workbench/issues)
- [Request features](https://github.com/orgs/Supervertaler/discussions)
- [Contributing guide](CONTRIBUTING.md)

---

## About

**Supervertaler** is maintained by [Michael Beijer](https://michaelbeijer.co.uk), a professional translator with 30 years of experience in technical and patent translation.

- [Stargazers](https://github.com/Supervertaler/Supervertaler-Workbench/stargazers) - See who's starred the project
- [Gitstalk](https://gitstalk.netlify.app/michaelbeijer) - See what I'm up to on GitHub

**License:** MIT - Free for personal and commercial use.

---

**Current Version:** See [CHANGELOG.md](CHANGELOG.md) for the latest release notes.
