# AutoFingers (CAT tool automation)

AutoFingers automates repetitive CAT-tool actions (primarily memoQ) by:

1. Reading source → target pairs from a TMX file
2. Copying the active source segment
3. Looking up the translation
4. Pasting the result and optionally confirming the segment

## Where to find it

- **Tools → AutoFingers - CAT Tool Automation...** (`Ctrl+Shift+A`)
- Or: **Tools** tab → **✋ AutoFingers**

## Quick start

1. Open **✋ AutoFingers**.
2. Choose a TMX file (or use **📥 Import from TM**).
3. Set your TMX language codes (for example: `en` → `nl`).
4. Put focus in memoQ on the segment you want to process.
5. Use one of the global hotkeys:
	 - `Ctrl+Alt+P` — process a single segment
	 - `Ctrl+Shift+L` — start/stop loop mode
	 - `Ctrl+Alt+S` — stop loop mode
	 - `Ctrl+Alt+R` — reload TMX

## Settings that matter

- **Confirm segments**
	- Enabled: confirms segments (Ctrl+Enter)
	- Disabled: moves to next without confirming (Alt+N)
- **Skip no match**: when enabled, AutoFingers will move on if there’s no TMX hit.
- **Timing**: increase delays if memoQ or your PC is slow, decrease if you want it faster.

## Safety & limitations

::: warning
AutoFingers sends keyboard shortcuts to the active window.
Always make sure memoQ is focused before starting loop mode.
:::

- Global hotkeys may require running Supervertaler **as Administrator** on some systems.
- Automation is inherently sensitive to UI focus, memoQ shortcuts, and machine performance.

## Related

- [TMX Editor](tmx-editor.md)
