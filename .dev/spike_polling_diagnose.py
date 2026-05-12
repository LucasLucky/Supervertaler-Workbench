"""Spike 2: diagnostic — find out what VK codes the user's keys produce.

The previous spike used VK_ADD (0x6B) for numpad+ and didn't detect the
user's press. Either the vk is different on this hardware/layout, or the
GetAsyncKeyState approach is misbehaving in a way we don't yet understand.

This spike polls *every* VK from 1 to 254 and prints transitions
(up → down and down → up) with timestamps. Press anything; the output
tells us what fired.

To stop: close the terminal window, or press F12 three times in a row
(F12 was picked because Esc is unreliable — Windows' WaitForSingleObject
and other paths can leave Esc in a sticky state).

Run from the Supervertaler repo root:
    .venv-build\\Scripts\\python.exe .dev\\spike_polling_diagnose.py
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def is_down(vk: int) -> bool:
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0


# Friendly names for common VKs so we don't have to look them up. Anything
# we don't have a name for prints as vk=NNN.
NAMES = {
    0x08: 'Backspace', 0x09: 'Tab', 0x0D: 'Enter', 0x10: 'Shift',
    0x11: 'Ctrl', 0x12: 'Alt', 0x13: 'Pause', 0x14: 'CapsLock',
    0x1B: 'Esc', 0x20: 'Space',
    0x21: 'PageUp', 0x22: 'PageDown', 0x23: 'End', 0x24: 'Home',
    0x25: '←', 0x26: '↑', 0x27: '→', 0x28: '↓',
    0x2C: 'PrintScreen', 0x2D: 'Insert', 0x2E: 'Delete',
    0x5B: 'LWin', 0x5C: 'RWin',
    0x60: 'Num0', 0x61: 'Num1', 0x62: 'Num2', 0x63: 'Num3', 0x64: 'Num4',
    0x65: 'Num5', 0x66: 'Num6', 0x67: 'Num7', 0x68: 'Num8', 0x69: 'Num9',
    0x6A: 'Num*', 0x6B: 'Num+', 0x6C: 'NumEnter', 0x6D: 'Num-',
    0x6E: 'Num.', 0x6F: 'Num/',
    0x90: 'NumLock', 0x91: 'ScrollLock',
    0xA0: 'LShift', 0xA1: 'RShift', 0xA2: 'LCtrl', 0xA3: 'RCtrl',
    0xA4: 'LAlt', 0xA5: 'RAlt (AltGr)',
    0xBA: ';', 0xBB: '=  (VK_OEM_PLUS)', 0xBC: ',', 0xBD: '-',
    0xBE: '.', 0xBF: '/', 0xC0: '`',
    0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'",
    **{vk: f'F{vk - 0x6F}' for vk in range(0x70, 0x88)},
    **{vk: chr(vk) for vk in range(0x30, 0x3A)},   # 0–9
    **{vk: chr(vk) for vk in range(0x41, 0x5B)},   # A–Z
}


def name(vk: int) -> str:
    return NAMES.get(vk, f'vk={vk} (0x{vk:02X})')


START = time.monotonic()


def t() -> str:
    return f"{time.monotonic() - START:7.3f}s"


def main():
    print("=" * 72)
    print("Polling diagnostic — prints every key transition (no keyboard hook)")
    print("=" * 72)
    print()
    print("Try: hold numpad+, hold Ctrl+Shift+Space, press AltGr, etc.")
    print("Each PRESS and RELEASE is printed below.")
    print()
    print("To stop: press F12 three times.")
    print()
    print("-" * 72)

    # Track state of every VK (1..254). Initial state = whatever
    # GetAsyncKeyState reports right now (skips printing initial state).
    state = {vk: is_down(vk) for vk in range(1, 255)}
    f12_taps = 0
    last_f12_release = 0.0

    poll_ms = 10
    while True:
        time.sleep(poll_ms / 1000)
        for vk in range(1, 255):
            cur = is_down(vk)
            if cur == state[vk]:
                continue
            state[vk] = cur
            if cur:
                print(f"[{t()}] PRESS    {name(vk)}")
            else:
                print(f"[{t()}] RELEASE  {name(vk)}")

                if vk == 0x7B:  # F12
                    now = time.monotonic()
                    if now - last_f12_release < 1.0:
                        f12_taps += 1
                    else:
                        f12_taps = 1
                    last_f12_release = now
                    if f12_taps >= 3:
                        print()
                        print("F12 tapped 3 times — stopping.")
                        return


if __name__ == "__main__":
    main()
