# User Data Folder Setup Guide - Supervertaler v3.7.1+

## Overview

As of **v3.7.1**, Supervertaler uses a user-configurable data folder system to store all your personal data, API keys, and projects. This guide explains how to set up and manage your data folder.

## Why a Separate Data Folder?

✅ **Security**: Your API keys never go near the installation folder
✅ **Portability**: Move your data folder to a USB stick or sync it across devices
✅ **Organization**: All your translations, prompts, and resources in one place
✅ **Multiple Users**: Each user can have their own data folder
✅ **Backup**: Easy to backup your entire Supervertaler data

## Quick Start

### Windows Users

**First Launch (v3.7.1+)**:
1. Open Supervertaler for the first time
2. A welcome dialog appears explaining the setup
3. Click "Select Folder" and choose a location
4. Recommended: `C:\Users\YourName\Documents\Supervertaler_Data`
5. Click "Create" to set up your data folder
6. Your `api_keys.txt` file is automatically created
7. Application launches with full functionality

### macOS Users

**First Launch**:
1. Open Supervertaler
2. Select folder dialog appears
3. Recommended: `~/Documents/Supervertaler_Data` or `~/Supervertaler_Data`
4. Click "Create"
5. Application launches

### Linux Users

**First Launch**:
1. Open Supervertaler
2. Select folder dialog appears
3. Recommended: `~/Documents/Supervertaler_Data` or `~/.supervertaler`
4. Click "Create"
5. Application launches

## Your Data Folder Structure

After initial setup, your folder will look like this:

```
Supervertaler_Data/
├── api_keys.txt                      ← Your API credentials (NEVER in git)
├── .supervertaler_config.json        ← Internal configuration
├── Prompt_Library/
│   ├── System_prompts/               ← 19 domain-specific prompts (Legal, Medical, etc.)
│   │   ├── Legal Translation Specialist.md
│   │   ├── Medical Translation Specialist.md
│   │   ├── Financial Translation Specialist.md
│   │   └── ... (16 more)
│   └── Custom_instructions/          ← Your personal preferences
│       ├── Professional Tone & Style.md
│       ├── Preserve Formatting & Layout.md
│       ├── Prefer Translation Memory Matches.md
│       └── ... (5 more)
├── Translation_Resources/
│   ├── Termbases/                    ← Your terminology databases
│   ├── TMs/                          ← Your Translation Memory files
│   ├── Non-translatables/            ← Lists of non-translatable terms
│   └── Segmentation_rules/           ← Custom segmentation rules
└── Projects/                         ← Your translation projects
    ├── MyProject_2025.json
    ├── LegalDoc_v2.json
    └── ... (your projects)
```

## Setting Up Your API Keys

### First Time Setup

1. **Open api_keys.txt** in your data folder
2. **You'll see three sections** (one for each AI provider):

```text
# ======================
# OPENAI API CONFIGURATION
# ======================
OPENAI_API_KEY=sk-proj-YOUR-KEY-HERE
OPENAI_MODEL=gpt-4-turbo

# ======================
# ANTHROPIC API CONFIGURATION
# ======================
ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
ANTHROPIC_MODEL=claude-3-opus-20250219

# ======================
# GOOGLE GEMINI API CONFIGURATION  
# ======================
GEMINI_API_KEY=YOUR-KEY-HERE
GEMINI_MODEL=gemini-2.0-flash
```

3. **Replace** `YOUR-KEY-HERE` with your actual API keys from:
   - **OpenAI**: https://platform.openai.com/api-keys
   - **Anthropic**: https://console.anthropic.com/
   - **Google Gemini**: https://aistudio.google.com/apikey

4. **Save the file**

5. **Restart Supervertaler** - it will load your keys automatically

### Multiple API Keys?

You can add all three! Supervertaler will:
- Use whichever provider you select in the AI settings
- Fall back to another if one fails
- Give you flexibility to test different providers

### Security Notes

✅ **api_keys.txt is git-ignored** - Never committed to repositories
✅ **Stored locally only** - Never uploaded anywhere
✅ **In your data folder** - Away from the installation
✅ **File permissions** - Consider restricting access on shared computers

## Changing Your Data Folder

### From the Settings Menu

If you want to move your data to a different location:

1. Open Supervertaler
2. Go to **Settings** tab
3. Find the **"Data Folder"** section
4. Click **"Change Data Folder"**
5. Select the new location
6. Supervertaler will offer to migrate your existing data
7. Click "Migrate" to move everything
8. Restart the application

### Manual Migration

If you prefer to move the folder yourself:

1. **Close Supervertaler** completely
2. **Move your entire data folder** to the new location
3. **Open Supervertaler** - it will prompt for the location
4. **Select the new location** when asked
5. Done!

## Upgrade from v3.7.0 → v3.7.1

### What Changed?

v3.7.0 had API keys in the installation folder. v3.7.1 moves them to a user data folder.

### Automatic Migration

When you first launch v3.7.1:

1. **SetupWizard appears** - helps you choose a data folder location
2. **Existing keys are found** - if you had `api_keys.txt` in the old location
3. **Keys are copied** to your new data folder automatically
4. **Old keys are removed** from the installation folder
5. Application uses the new location going forward

### What Gets Migrated?

- ✅ Your API keys
- ✅ Your recent projects
- ✅ Your custom prompts (if they were already in `user data/`)
- ✅ Your translation memory files
- ✅ Your termbases
- ✅ Your project files

## Multiple Computers?

### Syncing with Cloud Storage

You can sync your data folder using cloud services:

**Option 1: Cloud Sync Tools**
- OneDrive: Sync `C:\Users\YourName\Supervertaler_Data`
- Google Drive: Sync your data folder via Google Drive for Desktop
- Dropbox: Same approach
- iCloud (macOS): Sync the folder via iCloud Drive

**Option 2: Manual Backup**
- Regularly backup your `Supervertaler_Data` folder
- Transfer between computers via USB or cloud

### Important Notes

⚠️ **Close Supervertaler** before syncing/backing up
⚠️ **API Keys**: Consider keeping separate keys per computer
⚠️ **Conflicts**: If syncing, resolve conflicts before opening

## Troubleshooting

### "SetupWizard keeps appearing"

**Problem**: SetupWizard appears on every launch

**Solution**:
- Check that `~/.supervertaler_config.json` was created
- Make sure you selected a valid folder location
- Try closing and reopening the app

### "API keys not loading"

**Problem**: Supervertaler can't find your API keys

**Solution**:
1. Open your data folder
2. Check that `api_keys.txt` exists
3. Verify you added your actual API keys (not `YOUR-KEY-HERE`)
4. Save the file and restart

### "Can't find my data folder"

**Problem**: You forgot where you put it

**Solution**:
1. **Windows**: Search for `Supervertaler_Data` in File Explorer
2. **macOS/Linux**: Terminal: `find ~/ -name "Supervertaler_Data"`
3. Once found, you can tell Supervertaler via Settings > Change Data Folder

### "Out of disk space"

**Problem**: Your data folder is using too much space

**Solution**:
1. Check `Projects/` folder - remove old projects
2. Check `Translation_Resources/TMs/` - old translation memories
3. Consider archiving old projects to external storage

## Advanced: Multiple Data Folders

### Use Case

You might want separate data folders for:
- **Personal projects** vs **Client work**
- **Testing** vs **Production**
- **Different languages** you translate

### How to Switch

1. Close Supervertaler
2. Edit `~/.supervertaler_config.json` (your config file)
3. Change the `"data_folder_path"` value
4. Save and reopen Supervertaler

**Example config file** (`~/.supervertaler_config.json`):
```json
{
  "data_folder_path": "C:\\Users\\YourName\\Documents\\Supervertaler_Data",
  "last_project": "MyProject.json"
}
```

## Security Best Practices

### Protect Your API Keys

✅ **Do**:
- Keep `api_keys.txt` on a local, encrypted drive
- Use strong API key limits (rate limits) in your provider settings
- Rotate keys periodically
- Use different keys for different environments (dev vs production)

❌ **Don't**:
- Share your `api_keys.txt` with anyone
- Commit it to version control (it's git-ignored for a reason!)
- Upload it to cloud storage unencrypted
- Use production keys for testing

### Backup Your Data

1. **Weekly backup**: Copy your entire `Supervertaler_Data` folder
2. **Version your projects**: Keep numbered project versions
3. **Archive old TMs**: Move old translation memories to archive storage
4. **Test restores**: Occasionally test that your backups work

## Frequently Asked Questions

**Q: Where do my projects get saved?**
A: In `YourDataFolder/Projects/` as `.json` files

**Q: Can I use a cloud folder?**
A: Yes, but close Supervertaler before syncing to avoid conflicts

**Q: What if I delete my data folder?**
A: SetupWizard will appear on next launch and create a new one

**Q: Can I have different folders for different users on Windows?**
A: Yes! Each user gets their own `~/.supervertaler_config.json`

**Q: Should I back up my api_keys.txt?**
A: Yes, but keep backups secure. Consider using a password manager instead.

**Q: Can I move my data folder after setup?**
A: Yes! Use Settings > "Change Data Folder" to move and migrate

## Need More Help?

- 📖 **User Guide**: [USER_GUIDE.md](../USER_GUIDE.md)
- 🐛 **Report Issues**: [GitHub Issues](https://github.com/michaelbeijer/Supervertaler/issues)
- 💬 **Ask Questions**: [Supervertaler Forum](https://forum.supervertaler.com/)
- 🌐 **Website**: [supervertaler.com](https://supervertaler.com)

---

**Last Updated**: October 20, 2025  
**Version**: v3.7.1+  
**License**: MIT (Open Source)
