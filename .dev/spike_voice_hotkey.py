"""Spike: verify pynput.keyboard.Listener delivers press AND release for
arbitrary keys globally on this Windows setup.

Goal: prove the same OS-level keyboard hook that Handy uses (rdev → WH_KEYBOARD_LL)
works through pynput so we can replace our current RegisterHotKey path. Specifically
verify:
  - numpad + (the user's preferred dictation hotkey from Handy)
  - Ctrl+Shift+Space (current Workbench default)
  - That release events fire on every modifier release (so the "release any key in
    the chord stops recording" semantic is feasible).

Also probes a couple of layout-specific edge cases on Windows / NL-intl keyboards:
  - AltGr — Windows delivers this as Ctrl + Alt; we want to see exactly what pynput
    surfaces (alt_gr? alt_r? both Ctrl and Alt?).
  - Numpad with NumLock on vs off (the same physical key fires different vks).

Run from the Supervertaler repo root:
    .venv-build\\Scripts\\python.exe .dev\\spike_voice_hotkey.py
Press Esc to stop.
"""
from pynput import keyboard
from datetime import datetime

START = datetime.now()


def t() -> str:
    return f"{(datetime.now() - START).total_seconds():7.3f}s"


# --- Modifier tracking ----------------------------------------------------

MOD_KEYS = {
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl,
    keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift,
    keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt,
    keyboard.Key.alt_gr,
    keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd,
}
NORM = {
    keyboard.Key.ctrl_l: 'Ctrl', keyboard.Key.ctrl_r: 'Ctrl', keyboard.Key.ctrl: 'Ctrl',
    keyboard.Key.shift_l: 'Shift', keyboard.Key.shift_r: 'Shift', keyboard.Key.shift: 'Shift',
    keyboard.Key.alt_l: 'Alt', keyboard.Key.alt_r: 'AltGr', keyboard.Key.alt: 'Alt',
    keyboard.Key.alt_gr: 'AltGr',
    keyboard.Key.cmd_l: 'Cmd', keyboard.Key.cmd_r: 'Cmd', keyboard.Key.cmd: 'Cmd',
}

mods: set[str] = set()


def fmt(key) -> str:
    """Best-effort human-readable name for any key event."""
    if hasattr(key, 'char') and key.char:
        return repr(key.char)
    if hasattr(key, 'name'):
        return key.name
    if hasattr(key, 'vk') and key.vk is not None:
        return f"vk={key.vk}"
    return str(key)


def chord_str(key) -> str:
    name = fmt(key)
    if mods:
        return '+'.join(sorted(mods)) + '+' + name
    return name


# --- Target hotkey detection ---------------------------------------------

VK_ADD = 107   # numpad +
VK_SUBTRACT = 109  # numpad - (for reference, in case we want to test something else)


def is_numpad_plus(key) -> bool:
    return getattr(key, 'vk', None) == VK_ADD


def is_ctrl_shift_space(key) -> bool:
    return (fmt(key) == 'space'
            and 'Ctrl' in mods
            and 'Shift' in mods)


# --- Listener callbacks ---------------------------------------------------

def on_press(key):
    if key in MOD_KEYS:
        mods.add(NORM[key])

    flag = ''
    if is_numpad_plus(key):
        flag = '   ⬅ NUMPAD + (Handy default)'
    elif is_ctrl_shift_space(key):
        flag = '   ⬅ Ctrl+Shift+Space (Workbench default)'

    print(f"[{t()}] PRESS    {chord_str(key)}{flag}")


def on_release(key):
    flag = ''
    if is_numpad_plus(key):
        flag = '   ⬅ NUMPAD + released'
    elif fmt(key) == 'space' and ('Ctrl' in mods or 'Shift' in mods):
        flag = '   ⬅ space released (Ctrl+Shift+Space chord)'

    print(f"[{t()}] RELEASE  {chord_str(key)}{flag}")

    # Update mod tracking AFTER printing so the chord shows the state at release
    if key in MOD_KEYS:
        mods.discard(NORM[key])

    if key == keyboard.Key.esc:
        print("\n--- Esc pressed, stopping listener ---")
        return False


# --- Run -----------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Voice hotkey spike — pynput.keyboard.Listener (low-level hook)")
    print("=" * 70)
    print()
    print("Try these and watch the output:")
    print()
    print("  1. Hold numpad + for 2 seconds, release.")
    print("     Expect: PRESS at t=0s, RELEASE ~2s later.")
    print()
    print("  2. Hold Ctrl+Shift+Space for 2 seconds, release.")
    print("     Expect: PRESS each modifier, PRESS space, RELEASE space,")
    print("             RELEASE each modifier.")
    print()
    print("  3. Press AltGr alone (right Alt on NL/intl keyboard).")
    print("     This shows how pynput names that key on your layout.")
    print()
    print("  4. Toggle NumLock and try numpad + again — does the vk change?")
    print()
    print("Press Esc to stop.")
    print()
    print("-" * 70)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
