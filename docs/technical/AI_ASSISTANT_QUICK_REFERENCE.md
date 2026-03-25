# AI Assistant Quick Reference

## Getting Started

### Location
**Prompt Manager** tab → **✨ AI Assistant** sub-tab

### Quick Actions
- **🔍 AutoPrompt**: Auto-analyze current project and suggest/generate prompts

## Chat Interface

### Sending Messages
- Type message in bottom input area
- **Enter**: Send message
- **Shift+Enter**: New line in message

### What You Can Ask
- "Create a prompt for [domain] translations"
- "Improve my [type] prompt to be more specific"
- "What are the key points in this attached style guide?"
- "Generate a project prompt for [specific requirements]"
- "What prompts in my library would work for [use case]?"

## File Attachments

### Supported Formats
✅ PDF, DOCX, PPTX, XLSX (auto-converted to markdown)
✅ TXT, MD (direct import)

### How to Attach
1. Click **📎 Attached Files** in left sidebar
2. Select file(s) from dialog
3. Wait for conversion (if PDF/DOCX)
4. Ask questions about attached content

### Use Cases
- Style guides → "Summarize the key style requirements"
- Reference docs → "Extract terminology from this document"
- Source files → "Analyze this document and suggest appropriate prompts"

## Context Resources

### Available in Sidebar
- **📄 Current Document**: Your active project file
- **📎 Attached Files**: Documents you've attached (with count)
- **💡 Prompt Library**: All 38+ prompts available
- **💾 Translation Memories**: [Coming soon]
- **📚 Termbases**: [Coming soon]

## Common Workflows

### 1. Generate Domain Prompt
```
1. Click "🔍 AutoPrompt"
2. Review AI analysis and suggestions
3. Ask: "Create a complete prompt for [domain]"
4. Copy generated prompt
5. Save to Prompt Library (manual for now)
```

### 2. Improve Existing Prompt
```
1. Go to Prompt Library sub-tab
2. Select prompt to improve
3. Switch to AI Assistant
4. Ask: "Make the [prompt name] more specific for [use case]"
5. Review improvements
6. Update prompt in library
```

### 3. Analyze Style Guide
```
1. Attach style guide PDF/DOCX
2. Ask: "What are the main style requirements?"
3. Follow up: "Create a style guide prompt from this"
4. Save generated prompt
```

### 4. Project-Specific Prompt
```
1. Attach project documents
2. Click "🔍 AutoPrompt"
3. Review analysis
4. Ask: "Generate a project prompt with these requirements: [list]"
5. Save to library under Project Prompts folder
```

## Tips & Best Practices

### Be Specific
❌ "Make a legal prompt"
✅ "Create a legal contract translation prompt for EN→DE with formal tone"

### Use Context
- Attach relevant style guides before asking for improvements
- Reference specific prompts by name: "Improve my Medical Translation Specialist prompt"
- Provide project details: language pair, domain, special requirements

### Iterative Refinement
1. Start broad: "Create a medical prompt"
2. Review response
3. Refine: "Add more about regulatory compliance"
4. Continue until satisfied

### Leverage Resources
- Ask: "Which prompts in my library are relevant for [project]?"
- Request: "Compare my Legal and Patent prompts for similarities"
- Query: "Show me prompts with [specific keyword]"

## Conversation Management

### Persistence
- Conversations auto-save after each message
- Last 10 messages reload on app restart
- Full history stored in `user_data/ai_assistant/conversation.json`

### Context Memory
AI remembers:
- ✅ Recent conversation (last 5 messages)
- ✅ Currently attached files
- ✅ Available prompts in library
- ❌ Conversations from previous sessions (not yet implemented)

## Troubleshooting

### "AI Assistant not available"
**Solution**: Configure API keys in Settings → API Configuration
- Add OpenAI, Claude, or Gemini API key
- Restart app if needed

### No Response / Slow Response
**Causes**:
- Large attached files (processing time)
- Complex analysis requests
- Network issues

**Solutions**:
- Wait (some requests take 30-60 seconds)
- Reduce attached file sizes
- Check internet connection

### "Conversion error" for PDF/DOCX
**Causes**:
- Corrupted file
- Unsupported PDF format
- Protected/encrypted document

**Solutions**:
- Try different file
- Convert to TXT manually and attach
- Check file isn't password-protected

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| New line in message | Shift+Enter |
| Send message | Enter |
| Focus message input | (click in text area) |

## Advanced Features (Coming Soon)

- 🔄 Clear conversation history
- 💾 Export conversation as markdown
- 📝 Direct "Save to Library" from AI responses
- 🔍 Search conversation history
- 📊 Compare multiple prompts side-by-side
- 🎯 TM/Termbase integration in chat

## Example Prompts to Try

### Prompt Generation
```
"Create a comprehensive medical device translation prompt for EN→DE 
with focus on regulatory compliance and IEC 60601 standards"
```

### Improvement Request
```
"My Legal Translation Specialist prompt is too generic. 
Make it more specific for contract law with emphasis on 
Dutch legal terminology and formal register"
```

### Document Analysis
```
[Attach client style guide]
"Extract all terminology requirements, formatting rules, 
and tone guidelines from this style guide. Format as a 
structured prompt I can save to my library"
```

### Resource Query
```
"Which prompts in my library would be most suitable for 
translating pharmaceutical product information from 
English to Dutch?"
```

## Support

### Resources
- **User Guide**: `docs/AI_ASSISTANT_GUIDE.md`
- **Technical Details**: `docs/AI_ASSISTANT_IMPLEMENTATION.md`
- **Prompt Library**: See Prompt Library sub-tab

### Getting Help
1. Check AI Assistant Guide (full documentation)
2. Ask AI: "What can you help me with?"
3. Review existing prompts for examples

---

**Version**: 4.0.0-beta
**Last Updated**: November 8, 2025
