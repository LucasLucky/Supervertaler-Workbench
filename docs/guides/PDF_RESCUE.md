# PDF Rescue - AI-Powered OCR Tool

**Part of [Supervertaler](https://supervertaler.com/) • by Michael Beijer**

---

## 📖 Overview

**PDF Rescue** is a specialised AI-powered OCR tool designed to extract clean, editable text from poorly formatted PDFs. Built into Supervertaler v3.5.0-beta, it uses GPT-4 Vision to intelligently recognise text, formatting, redactions, stamps, and signatures–producing professional, translator-ready documents.

### 🎯 The Problem It Solves

Have you ever received a PDF translation job where:
- The text won't copy-paste cleanly?
- Line breaks are all over the place?
- Formatting is completely broken?
- Traditional OCR produces gibberish?
- Redacted sections show as black boxes?
- Stamps and signatures clutter the text?

**PDF Rescue fixes all of this.**

###  Real-World Success Story

> *"I had a client reach out for a rush job–a 4-page legal document that had clearly been scanned badly. Traditional OCR couldn't handle it, and manual retyping would have taken hours.*
> 
> *I used PDF Rescue's one-click PDF import, processed all 4 pages with AI OCR, and it produced a flawless Word document that I could immediately start working with. What would have been a multi-day nightmare became a straightforward job I could deliver on time.*
> 
> *I was able to tell my client that I could handle the job–and delivered professional quality. PDF Rescue literally saved a client relationship."*
> 
> – Michael Beijer, Professional Translator

---

## ✨ Key Features

### 1. 📄 **One-Click PDF Import**
- **No external tools needed** - Import PDFs directly
- **Automatic page extraction** - Each page saved as high-quality PNG (2x resolution)
- **Persistent storage** - Images saved next to source PDF in `{filename}_images/` folder
- **Client-ready** - Images can be delivered to end clients if needed

### 2. 🧠 **Smart AI-Powered OCR**
- **GPT-4 Vision** - Industry-leading OCR accuracy
- **Context-aware** - Understands document structure and formatting
- **Intelligent cleanup** - Fixes line breaks, spacing, and formatting issues
- **Redaction handling** - Inserts descriptive placeholders like `[naam]`, `[bedrag]` in document language
- **Stamps & signatures** - Detects and describes non-text elements: `[stempel]`, `[handtekening]`

### 3. 🎨 **Optional Formatting Preservation**
- **Markdown-based** - Uses `**bold**`, `*italic*`, `__underline__`
- **Toggle on/off** - User-controlled via checkbox
- **Clean output** - Markdown converted to proper formatting in DOCX export
- **Visual preview** - See formatting markers before export

### 4. 📊 **Batch Processing**
- **Process selected** - Work on individual images
- **Process all** - Batch process entire document
- **Progress tracking** - Visual progress bar and status updates
- **Skip processed** - Already-processed images are skipped (unless re-selected)

### 5. 📝 **Comprehensive Logging**
- **Activity log integration** - All operations logged with timestamps
- **PDF import progress** - Each page extraction logged
- **OCR processing** - Per-image processing logged
- **DOCX export** - Export operations tracked

### 6. 👁️ **Full Transparency**
- **"Show Prompt" button** - View exact instructions sent to AI
- **Configuration display** - See model, formatting settings, max tokens
- **No black boxes** - Complete visibility into AI processing

### 7. 📊 **Professional Session Reports**
- **Markdown format** - Clean, readable documentation
- **Complete configuration** - All settings recorded
- **Processing summary** - Table of all images and status
- **Full extracted text** - All OCR results included
- **Statistics** - Character/word counts and averages
- **Supervertaler branding** - Professional client-ready reports

### 8. 💾 **Flexible Export Options**
- **DOCX export** - Formatted Word documents with optional bold/italic/underline
- **Copy to clipboard** - Quick text extraction
- **Session reports** - Professional MD documentation

### 9. 🚀 **Standalone Mode**
Can run independently outside Supervertaler:
```bash
python modules/pdf_rescue.py
```
Full-featured standalone application with all capabilities.

---

## 🎯 Workflow

### Quick Start (5 Steps)

1. **Open PDF Rescue** - Navigate to Assistant panel → PDF Rescue tab
2. **Import PDF** - Click "📄 PDF" button, select your badly-formatted PDF
3. **Check formatting option** - Leave "Preserve formatting" checked (default)
4. **Process** - Click "⚡ Process ALL" to OCR all pages
5. **Export** - Click "💾 Save DOCX" to create Word document

**That's it!** You now have a clean, editable Word document ready for translation.

---

### Detailed Workflow

#### Step 1: Import Your PDF

**Method 1: Direct PDF Import** (Recommended)
```
Click: 📄 PDF button
→ Select PDF file
→ Automatic page extraction to {filename}_images/ folder
→ All pages added to processing queue
```

**Method 2: Manual Image Import**
```
Click: 📁 Add Files → Select individual images
OR
Click: 📂 Folder → Select folder with images
```

**Result**: All images listed in left panel with ✓ status indicators

---

#### Step 2: Configure Settings

**Model Selection**:
- `gpt-4o` (Recommended) - Latest, fastest, best quality
- `gpt-4o-mini` - Budget option, good quality
- `gpt-4-turbo` - Alternative, similar quality to gpt-4o

**Formatting Option**:
- ✓ **Preserve formatting (bold/italic/underline)** - Enabled by default
- Unchecked = Plain text output only

**Extraction Instructions**:
- Default instructions optimized for badly formatted PDFs
- Handles redactions, stamps, signatures automatically
- Can customize if needed (advanced)
- Click **"👁️ Show Prompt"** to see exact AI instructions

---

#### Step 3: Process Images

**Option A: Process Selected**
```
1. Select image(s) in list
2. Click: 🔍 Process Selected
3. View result in preview pane
```

**Option B: Process All** (Recommended)
```
1. Click: ⚡ Process ALL
2. Confirm batch processing dialog
3. Watch progress bar
4. All pages processed automatically
```

**Processing Details**:
- Each image sent to GPT-4 Vision
- Text extracted with context awareness
- Formatting detected (if enabled)
- Redactions/stamps/signatures handled
- Results stored in memory
- ✓ indicator appears when processed

---

#### Step 4: Review & Export

**Review Extracted Text**:
- Click any processed image in list
- Preview pane shows extracted text
- Formatting shown as markdown (`**bold**`, `*italic*`, etc.)
- Verify quality before export

**Export Options**:

1. **💾 Save DOCX** (Primary export)
   - Formatted Word document
   - Markdown converted to proper formatting
   - One page per document page
   - Page headers with filenames
   - Ready for translation work

2. **📋 Copy All**
   - All text to clipboard
   - Includes page separators
   - Quick paste into any application

3. **📊 Session Report**
   - Professional markdown documentation
   - Complete configuration record
   - All extracted text included
   - Statistics and metadata
   - Client-ready deliverable

---

## 🎨 Smart Features Explained

### Redaction Handling

PDF Rescue intelligently detects redacted/blacked-out text and inserts descriptive placeholders **in the document's language**:

**Example (Dutch document)**:
```
Source PDF: "De heer ████████ heeft op ██████ een bedrag van €████ betaald."

PDF Rescue Output: "De heer [naam] heeft op [datum] een bedrag van €[bedrag] betaald."
```

**Example (English document)**:
```
Source PDF: "Mr. ████████ paid $████ on ██████."

PDF Rescue Output: "Mr. [name] paid $[amount] on [date]."
```

**How it works**:
- AI detects language automatically
- Contextually determines what's redacted (name, date, amount, etc.)
- Inserts appropriate placeholder in square brackets
- No manual language specification needed!

---

### Stamp & Signature Detection

Non-text elements are described in square brackets:

**Dutch**:
- `[stempel]` - Stamp/seal
- `[handtekening]` - Signature
- `[logo]` - Company logo

**English**:
- `[stamp]` - Official stamp
- `[signature]` - Handwritten signature
- `[seal]` - Official seal

**Benefit**: Translators know where non-text elements belong without seeing the original.

---

### Formatting Preservation

When **"Preserve formatting"** is checked:

**Input (as seen by AI)**:
```
This document contains **important legal terms** that must be followed.
Payment is due *within 30 days* of invoice date.
The __deadline is strict__.
```

**DOCX Export**:
- "**important legal terms**" → **important legal terms** (bold)
- "*within 30 days*" → *within 30 days* (italic)
- "__deadline is strict__" → <u>deadline is strict</u> (underlined)

**Preview Shows Markdown** (temporary):
- Preview pane displays `**bold**`, `*italic*`, `__underline__`
- Final DOCX has proper formatting (no visible markers)

---

## 📊 Session Reports

Session reports provide professional documentation of OCR sessions:

### Report Structure

```markdown
# PDF Rescue - Session Report
**Generated by [Supervertaler](https://supervertaler.com/) • by Michael Beijer**

**Date**: 2025-10-16 14:32:15

---

## Configuration
- **Model**: gpt-4o
- **Formatting Preservation**: Enabled ✓
- **Total Images Processed**: 4
- **Total Images in List**: 4

## Extraction Instructions
```
[Full prompt displayed]
```

## Processing Summary
| # | Image File | Status |
|---|------------|--------|
| 1 | Document_page_001.png | ✓ Processed |
| 2 | Document_page_002.png | ✓ Processed |
| 3 | Document_page_003.png | ✓ Processed |
| 4 | Document_page_004.png | ✓ Processed |

---

## Extracted Text

### Page 1: Document_page_001.png
```
[Full extracted text]
```

---

## Statistics
- **Total Characters Extracted**: 15,432
- **Total Words Extracted**: 2,547
- **Average Characters per Page**: 3,858
- **Average Words per Page**: 636

---

*Report generated by **PDF Rescue** - AI-Powered OCR Tool*

*Part of [**Supervertaler**](https://supervertaler.com/) • by Michael Beijer*
```

### Use Cases for Reports
- ✅ Project documentation
- ✅ Client deliverable (along with DOCX)
- ✅ Quality assurance record
- ✅ Troubleshooting reference
- ✅ Billing support (word counts)

---

## 💡 Pro Tips

### Best Practices

1. **Always use PDF import** - Eliminates manual screenshot/conversion steps
2. **Leave formatting enabled** - Better output quality, easily disabled if needed
3. **Review first page** - Process one page first to check quality before batch
4. **Save session report** - Professional documentation for clients/records
5. **Keep images** - Stored next to PDF for future reference

### Quality Optimization

**For best OCR results**:
- ✅ Use high-quality source PDFs when possible
- ✅ gpt-4o model recommended (best accuracy)
- ✅ Process similar pages in batches (consistent instructions)
- ✅ Review extracted text before delivering
- ✅ Customize instructions for specialized documents (if needed)

**If results aren't perfect**:
- Try different model (gpt-4-turbo vs gpt-4o)
- Disable formatting if causing issues
- Adjust instructions (advanced users)
- Process problematic pages individually
- Use "Show Prompt" to understand AI behavior

### Cost Management

**API Usage**:
- Each image = 1 API call
- Cost depends on model:
  - `gpt-4o` - Most expensive, best quality
  - `gpt-4o-mini` - Budget option, ~90% quality
  - `gpt-4-turbo` - Middle ground

**Optimization**:
- ✅ Process only selected pages if partial document
- ✅ Use gpt-4o-mini for drafts/testing
- ✅ Review one page before processing all (catch issues early)
- ✅ Skip already-processed pages (automatic)

---

## 🔧 Technical Details

### Folder Structure

**After PDF Import**:
```
C:\Path\To\Your\
├── Document.pdf (source)
└── Document_images\
    ├── Document_page_001.png (2x resolution)
    ├── Document_page_002.png
    ├── Document_page_003.png
    └── Document_page_004.png
```

**Benefits**:
- Permanent storage (not temp files)
- Easy to locate (same folder as source)
- Client-deliverable images
- Translator reference during work

### Dependencies

**Required** (automatically included in Supervertaler):
- `openai` - OpenAI API client
- `python-docx` - DOCX file handling
- `PyMuPDF (fitz)` - PDF page extraction
- `tkinter` - GUI framework
- `PIL/Pillow` - Image processing

**Optional**:
- None - all features included!

### API Integration

**Models Supported**:
- `gpt-4o` - Latest multimodal model
- `gpt-4o-mini` - Compact version
- `gpt-4-turbo` - Previous generation
- All support vision capabilities

**API Call Structure**:
```python
{
  "model": "gpt-4o",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "[instructions]"},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,[...]"}}
    ]
  }],
  "max_tokens": 4000
}
```

---

## ❓ FAQ

### General Questions

**Q: Do I need ABBYY FineReader or other OCR software?**  
A: No! PDF Rescue handles everything internally. No external tools needed.

**Q: What file formats are supported?**  
A: **Input**: PDF (direct), or image files (JPG, PNG, BMP, GIF, TIFF)  
**Output**: DOCX (Word), TXT (clipboard), MD (session report)

**Q: Can I use it without Supervertaler?**  
A: Yes! Run standalone: `python modules/pdf_rescue.py`

**Q: Does it work with handwritten text?**  
A: GPT-4 Vision can handle some handwriting, but results vary. Best for printed text.

**Q: What languages are supported?**  
A: All languages supported by GPT-4 (100+ languages). Auto-detects language.

### Technical Questions

**Q: Where are images stored?**  
A: Next to source PDF in `{pdf_name}_images/` folder (not temp directory).

**Q: Can I edit the extraction instructions?**  
A: Yes! Advanced users can modify the instructions text box. Default instructions are optimized for most cases.

**Q: What does "Show Prompt" do?**  
A: Opens a popup showing the exact prompt sent to OpenAI API, including all modifications based on your settings.

**Q: How is formatting preserved?**  
A: AI outputs markdown (`**bold**`, `*italic*`, `__underline__`), which is parsed and converted to proper Word formatting during DOCX export.

**Q: Can I process only specific pages?**  
A: Yes! Select specific images in the list and click "🔍 Process Selected".

### Cost & Performance

**Q: How much does it cost per page?**  
A: Depends on model and content:
- `gpt-4o-mini`: ~$0.01-0.03 per page
- `gpt-4o`: ~$0.05-0.15 per page
- `gpt-4-turbo`: ~$0.03-0.10 per page

**Q: How long does processing take?**  
A: 2-5 seconds per page (depends on API response time and content complexity).

**Q: Can I pause batch processing?**  
A: Currently no - batch processing runs until complete. Process in smaller batches if needed.

---

## 🐛 Troubleshooting

### Common Issues

**PDF Import Not Working**
- ✅ Check PDF is not password-protected
- ✅ Verify PDF has actual pages (not empty)
- ✅ Try opening PDF in Adobe Reader first
- ✅ Check error message in log

**Poor OCR Quality**
- ✅ Try different model (gpt-4o vs gpt-4-turbo)
- ✅ Check source PDF quality (low-res scans may fail)
- ✅ Disable formatting if causing issues
- ✅ Process problematic pages individually

**Missing Formatting in Export**
- ✅ Verify "Preserve formatting" was checked during processing
- ✅ Re-process with formatting enabled
- ✅ Check preview shows markdown markers (`**bold**`, etc.)

**API Errors**
- ✅ Verify OpenAI API key in `api_keys.txt`
- ✅ Check API key has credits/billing enabled
- ✅ Try again (temporary API issues)
- ✅ Check log for specific error message

**Slow Processing**
- ✅ Normal - each page takes 2-5 seconds
- ✅ Check internet connection
- ✅ OpenAI API response time varies
- ✅ Consider gpt-4o-mini for faster processing

---

## 📚 Related Documentation

- **Main README**: [README.md](../../README.md)
- **User Guide**: [USER_GUIDE.md](USER_GUIDE.md)
- **FAQ**: [FAQ.md](../../FAQ.md)
- **Installation**: [INSTALLATION.md](INSTALLATION.md)
- **Changelog**: [CHANGELOG-CAT.md](../../CHANGELOG-CAT.md)

---

## 🎉 Summary

PDF Rescue is the ultimate tool for translators dealing with badly formatted PDFs. With one-click PDF import, intelligent AI-powered OCR, smart redaction handling, and professional DOCX export, it transforms unusable PDFs into clean, translator-ready documents.

**No more**:
- ❌ Manual retyping
- ❌ External OCR software
- ❌ Broken formatting
- ❌ Missing text
- ❌ Unusable documents

**Instead**:
- ✅ One-click import
- ✅ Professional output
- ✅ Clean formatting
- ✅ Smart placeholders
- ✅ Client-ready deliverables

**Start using PDF Rescue today and never turn down a badly-formatted PDF job again!** 🚀

---

*Part of [**Supervertaler**](https://supervertaler.com/) • by Michael Beijer*
