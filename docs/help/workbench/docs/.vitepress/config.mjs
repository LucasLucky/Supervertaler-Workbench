import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Supervertaler Workbench',
  description: 'Help documentation for Supervertaler Workbench',
  lang: 'en-GB',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/sv-icon.svg' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { href: 'https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap', rel: 'stylesheet' }],
  ],

  themeConfig: {
    logo: '/sv-icon.svg',
    siteTitle: 'Supervertaler Workbench Help',

    nav: [
      { text: 'supervertaler.com', link: 'https://supervertaler.com' },
      { text: 'GitHub', link: 'https://github.com/michaelbeijer/Supervertaler' },
      { text: 'michaelbeijer.co.uk', link: 'https://michaelbeijer.co.uk' },
    ],

    sidebar: [
      {
        text: '',
        items: [
          { text: 'Supervertaler Workbench', link: '/' },
        ]
      },
      {
        text: 'Get Started',
        collapsed: false,
        items: [
          { text: 'Installation', link: '/get-started/installation' },
          { text: 'Quick Start', link: '/get-started/quick-start' },
          { text: 'Your First Project', link: '/get-started/first-project' },
          { text: 'Setting Up API Keys', link: '/get-started/api-keys' },
        ]
      },
      {
        text: 'Editor',
        collapsed: true,
        items: [
          { text: 'Translation Grid', link: '/editor/translation-grid' },
          { text: 'Editing & Confirming', link: '/editor/editing-confirming' },
          { text: 'Navigation', link: '/editor/navigation' },
          { text: 'Filtering', link: '/editor/filtering' },
          { text: 'Find & Replace', link: '/editor/find-replace' },
          { text: 'Keyboard Shortcuts', link: '/editor/keyboard-shortcuts' },
          { text: 'Segment Statuses', link: '/editor/segment-statuses' },
          { text: 'Pagination', link: '/editor/pagination' },
        ]
      },
      {
        text: 'AI Translation',
        collapsed: true,
        items: [
          { text: 'Overview', link: '/ai-translation/overview' },
          { text: 'Single-Segment Translation', link: '/ai-translation/single-segment' },
          { text: 'Batch Translation', link: '/ai-translation/batch-translation' },
          { text: 'Prompts', link: '/ai-translation/prompts' },
          { text: 'Prompt Library', link: '/ai-translation/prompt-library' },
          { text: 'Supported Providers', link: '/ai-translation/providers' },
          { text: 'Ollama (Local AI)', link: '/ai-translation/ollama' },
          { text: 'Quick Launcher', link: '/ai-translation/quicklauncher' },
        ]
      },
      {
        text: 'Glossaries',
        collapsed: true,
        items: [
          { text: 'Glossary Basics', link: '/glossaries/basics' },
          { text: 'Creating a Glossary', link: '/glossaries/creating' },
          { text: 'Importing Terms', link: '/glossaries/importing' },
          { text: 'Term Highlighting', link: '/glossaries/highlighting' },
          { text: 'Term Extraction', link: '/glossaries/extraction' },
          { text: 'TermLens', link: '/glossaries/termlens' },
        ]
      },
      {
        text: 'Translation Memory',
        collapsed: true,
        items: [
          { text: 'TM Basics', link: '/translation-memory/basics' },
          { text: 'Fuzzy Matching', link: '/translation-memory/fuzzy-matching' },
          { text: 'Importing TMX', link: '/translation-memory/importing-tmx' },
          { text: 'Managing TMs', link: '/translation-memory/managing-tms' },
          { text: 'SuperMemory', link: '/translation-memory/supermemory' },
        ]
      },
      {
        text: 'Import & Export',
        collapsed: true,
        items: [
          { text: 'Supported Formats', link: '/import-export/formats' },
          { text: 'Importing DOCX', link: '/import-export/docx-import' },
          { text: 'Importing TXT', link: '/import-export/txt-import' },
          { text: 'Bilingual Tables', link: '/import-export/bilingual-tables' },
          { text: 'Multi-file Projects', link: '/import-export/multi-file' },
          { text: 'Exporting', link: '/import-export/exporting' },
        ]
      },
      {
        text: 'SuperLookup',
        collapsed: true,
        items: [
          { text: 'Overview', link: '/superlookup/overview' },
          { text: 'TM Search', link: '/superlookup/tm-search' },
          { text: 'Glossary Search', link: '/superlookup/glossary-search' },
          { text: 'Machine Translation', link: '/superlookup/mt' },
          { text: 'Web Resources', link: '/superlookup/web-resources' },
        ]
      },
      {
        text: 'CAT Tool Integration',
        collapsed: true,
        items: [
          { text: 'Overview', link: '/cat-tools/overview' },
          { text: 'Trados Studio', link: '/cat-tools/trados' },
          { text: 'memoQ', link: '/cat-tools/memoq' },
          { text: 'CafeTran', link: '/cat-tools/cafetran' },
          { text: 'Phrase TMS', link: '/cat-tools/phrase' },
        ]
      },
      {
        text: 'Quality Assurance',
        collapsed: true,
        items: [
          { text: 'Spellcheck', link: '/qa/spellcheck' },
          { text: 'Tag Validation', link: '/qa/tag-validation' },
          { text: 'Non-Translatables', link: '/qa/non-translatables' },
        ]
      },
      {
        text: 'Tools',
        collapsed: true,
        items: [
          { text: 'AutoFingers', link: '/tools/autofingers' },
          { text: 'Voice Commands', link: '/tools/voice-commands' },
          { text: 'TMX Editor', link: '/tools/tmx-editor' },
          { text: 'PDF Rescue', link: '/tools/pdf-rescue' },
          { text: 'Image Extractor', link: '/tools/image-extractor' },
        ]
      },
      {
        text: 'Settings',
        collapsed: true,
        items: [
          { text: 'General', link: '/settings/general' },
          { text: 'Fonts', link: '/settings/fonts' },
          { text: 'Theme', link: '/settings/theme' },
          { text: 'View', link: '/settings/view' },
          { text: 'Keyboard Shortcuts', link: '/settings/shortcuts' },
        ]
      },
      {
        text: 'Troubleshooting',
        collapsed: true,
        items: [
          { text: 'Common Issues', link: '/troubleshooting/common-issues' },
          { text: 'API Issues', link: '/troubleshooting/api-issues' },
          { text: 'Import/Export Errors', link: '/troubleshooting/import-export-errors' },
          { text: 'Performance', link: '/troubleshooting/performance' },
          { text: 'Linux', link: '/troubleshooting/linux' },
        ]
      },
      {
        text: 'Reference',
        collapsed: true,
        items: [
          { text: 'Changelog', link: '/reference/changelog' },
          { text: 'FAQ', link: '/reference/faq' },
          { text: 'File Formats', link: '/reference/file-formats' },
          { text: 'Contributing', link: '/reference/contributing' },
        ]
      },
    ],

    search: {
      provider: 'local'
    },

    editLink: false,

    socialLinks: [],

    footer: {
      message: 'Supervertaler Workbench',
      copyright: '© Michael Beijer'
    },

    outline: {
      label: 'On this page',
      level: [2, 3]
    },

    docFooter: {
      prev: 'Previous',
      next: 'Next'
    },
  },

  appearance: true,

  markdown: {
    theme: {
      light: 'github-light',
      dark: 'github-dark'
    }
  },
})
