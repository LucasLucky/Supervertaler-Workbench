# Find & Replace

Supervertaler's Find & Replace feature helps you quickly find text and make consistent changes across your translation.

## Opening Find & Replace

- Press `Ctrl+F` or `Ctrl+H`
- Or go to **Edit → Find & Replace**

## Basic Usage

### Finding Text

1. Type your search term in the **Find** field
2. Click **Find All** to see all matches
3. Matches are highlighted in yellow in the grid
4. The results counter shows how many matches were found

### Replacing Text

1. Type your search term in the **Find** field
2. Type your replacement in the **Replace** field
3. Click **Replace All** to replace all occurrences
4. A confirmation shows how many replacements were made

## Search Options

### Match Mode

| Mode | Description |
|------|-------------|
| **Contains** | Matches anywhere in the text |
| **Whole Word** | Only matches complete words |
| **Starts With** | Matches at the beginning of text |
| **Ends With** | Matches at the end of text |
| **Regex** | Use regular expressions |

### Case Sensitivity

Toggle **Case Sensitive** to:
- ✅ **On**: "Hello" won't match "hello"
- ❌ **Off**: "Hello" matches "hello", "HELLO", etc.

### Search Scope

| Scope | Description |
|-------|-------------|
| **Source + Target** | Search in both columns |
| **Source Only** | Search only in source text |
| **Target Only** | Search only in translations |

## History Dropdowns

Both the Find and Replace fields remember your recent searches:

- Click the dropdown arrow to see your last 20 entries
- Start typing to filter the history
- History persists between sessions

## F&R Sets (Batch Operations)

Save and reuse multiple find/replace operations as a set.

### Creating a Set

1. Expand the **📁 F&R Sets** panel
2. Click **➕ New Set**
3. Give your set a name (e.g., "Client Style Guide")
4. The set appears in the dropdown

### Adding Operations to a Set

1. Enter your Find and Replace terms
2. Set your options (case, scope, mode)
3. Click **➕ Add Current to Set**
4. The operation is saved to the active set

### Managing Operations

In the F&R Sets panel:
- ✅ Enable/disable individual operations
- 📝 Edit operations (double-click)
- ⬆️⬇️ Reorder operations
- 🗑️ Delete operations

### Running a Batch

1. Select your set from the dropdown
2. Click **▶️ Run All**
3. A progress dialog shows each operation
4. See how many replacements were made

### Importing & Exporting Sets

Share sets with colleagues:
- **Export**: Click **📤 Export Set** to save as `.svfr` file
- **Import**: Click **📥 Import Set** to load a shared file

## Use Cases

### Terminology Consistency

Create a set for client-specific terms:
- "colour" → "color" (US spelling)
- "organisation" → "organization"
- "programme" → "program"

### Style Guide Rules

Enforce style guidelines:
- Double spaces → Single space
- "e.g." → "for example"
- Straight quotes → Curly quotes

### Post-Translation Cleanup

Clean up common MT artifacts:
- Remove unwanted spaces before punctuation
- Fix capitalization issues
- Normalize formatting

## Tips

::: tip
**Pro Tip:** Use regex mode for complex patterns. For example, `\s+` matches any whitespace to clean up extra spaces.
:::

::: info
**Undo Support:** All replacements can be undone with `Ctrl+Z` (within the same session).
:::
