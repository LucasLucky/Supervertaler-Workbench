"""Spike: detect key release via GetAsyncKeyState polling.

The pynput.keyboard.Listener approach installs a WH_KEYBOARD_LL hook,
which interferes with AHK's hook chain and makes synthetic Ctrl+C
calls hang. This spike tests an alternative: keep press detection on
RegisterHotKey (kernel-level, no hook), and detect release by polling
GetAsyncKeyState in a short-lived thread that runs only while a
recording is live.

Goals to verify on this Windows setup:
  1. GetAsyncKeyState reports the correct state for numpad+ and
     Ctrl+Shift+Space.
  2. Polling latency is acceptable (release detected within ~20–40 ms).
  3. AHK keeps working while polling is active — try running AHK
     (e.g. via 'powershell Start-Process notepad' then typing) and
     confirm nothing locks up.

Run from the Supervertaler repo root:
    .venv-build\\Scripts\\python.exe .dev\\spike_polling_release.py

Instructions are printed on launch. Press Esc (any window) to stop.
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

# GetAsyncKeyState returns SHORT. Bit 0x8000 set = key currently down.
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def is_down(vk: int) -> bool:
    """True iff the key is currently pressed."""
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0


# Common VKs we'll poll
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LMENU = 0xA4   # left Alt
VK_RMENU = 0xA5   # right Alt / AltGr
VK_SPACE = 0x20
VK_ESCAPE = 0x1B
VK_NUM_ADD = 0x6B   # numpad +


def ctrl_down() -> bool:
    return is_down(VK_LCONTROL) or is_down(VK_RCONTROL)


def shift_down() -> bool:
    return is_down(VK_LSHIFT) or is_down(VK_RSHIFT)


def alt_down() -> bool:
    return is_down(VK_LMENU) or is_down(VK_RMENU)


def detect_press_then_release(name: str, is_chord_held, poll_ms: int = 20):
    """Wait for the chord to be held, then poll until it's released.

    Returns (hold_time_ms, polls_done) once the chord is released.
    """
    print(f"[{name}] waiting for press…")
    while not is_chord_held():
        if is_down(VK_ESCAPE):
            return None
        time.sleep(poll_ms / 1000)
    press_t = time.monotonic()
    polls = 0
    print(f"[{name}] PRESS detected at t={press_t:.3f}, polling for release every {poll_ms} ms…")

    while is_chord_held():
        time.sleep(poll_ms / 1000)
        polls += 1
        if is_down(VK_ESCAPE):
            return None

    release_t = time.monotonic()
    hold_ms = (release_t - press_t) * 1000
    print(f"[{name}] RELEASE detected. Held for {hold_ms:.0f} ms across {polls} polls.")
    return hold_ms, polls


if __name__ == "__main__":
    print("=" * 70)
    print("Polling spike: GetAsyncKeyState (no keyboard hook)")
    print("=" * 70)
    print()
    print("This spike does NOT install any keyboard hook, so AHK should")
    print("keep working normally throughout the test.")
    print()
    print("Tests, in order:")
    print()
    print("  1. Hold and release numpad +  (do this 2–3 times)")
    print("  2. Hold and release Ctrl+Shift+Space  (do this 2–3 times)")
    print()
    print("After each release, you'll see how long the chord was held")
    print("and how many 20 ms polls happened.")
    print()
    print("Press Esc anywhere to stop the spike.")
    print()
    print("-" * 70)

    # Test 1: numpad +
    print()
    print("--- Test 1: numpad + ---")
    for i in range(3):
        result = detect_press_then_release(
            f"numpad+ #{i+1}",
            lambda: is_down(VK_NUM_ADD),
        )
        if result is None:
            print("Esc pressed, stopping.")
            raise SystemExit(0)

    # Test 2: Ctrl+Shift+Space
    print()
    print("--- Test 2: Ctrl+Shift+Space ---")
    for i in range(3):
        result = detect_press_then_release(
            f"Ctrl+Shift+Space #{i+1}",
            lambda: ctrl_down() and shift_down() and is_down(VK_SPACE),
        )
        if result is None:
            print("Esc pressed, stopping.")
            raise SystemExit(0)

    print()
    print("All tests done. If AHK kept working while this spike ran, the")
    print("polling approach is safe. Press Esc to exit.")
    while not is_down(VK_ESCAPE):
        time.sleep(0.05)
