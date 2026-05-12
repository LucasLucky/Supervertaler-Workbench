"""Unit tests for modules.voice_hotkey_listener.HotkeyMatcher.

Pure-logic tests – no pynput thread, no Qt event loop. Run with:
    .venv-build\\Scripts\\python.exe .dev\\test_voice_hotkey_listener.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.voice_hotkey_listener import HotkeyMatcher, parse_qt_shortcut


# Windows VKs we'll synthesise in tests
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_LALT = 0xA4
VK_RALT = 0xA5  # AltGr
VK_SPACE = 0x20
VK_F9 = 0x78
VK_NUM_ADD = 0x6B


def make_matcher():
    pressed_events = []
    released_events = []
    m = HotkeyMatcher(
        on_chord_pressed=pressed_events.append,
        on_chord_released=released_events.append,
    )
    return m, pressed_events, released_events


def test_parse():
    assert parse_qt_shortcut("Ctrl+Shift+Space") == frozenset({'CTRL', 'SHIFT', 0x20})
    assert parse_qt_shortcut("F9") == frozenset({0x78})
    assert parse_qt_shortcut("Num+") == frozenset({0x6B})
    assert parse_qt_shortcut("ctrl+alt+d") == frozenset({'CTRL', 'ALT', ord('D')})
    assert parse_qt_shortcut("") is None
    assert parse_qt_shortcut("Garbage") is None
    print("PASS parse_qt_shortcut")


def test_single_key_hold():
    """Numpad+ press → start, release → stop. With ~30 auto-repeat presses
    in between (Windows fires repeat-PRESS while a key is held); the matcher
    must dedupe so we only see one START and one STOP."""
    m, pressed, released = make_matcher()
    m.register('dictate', parse_qt_shortcut('Num+'))

    m.on_press(VK_NUM_ADD)
    for _ in range(24):  # simulate ~720 ms of auto-repeat
        m.on_press(VK_NUM_ADD)
    m.on_release(VK_NUM_ADD)

    assert pressed == ['dictate'], pressed
    assert released == ['dictate'], released
    print("PASS single_key_hold (auto-repeat deduped)")


def test_chord_with_modifiers():
    """Ctrl+Shift+Space chord: each modifier fires independently, then space.
    On release of any key in the chord, the binding fires released exactly
    once."""
    m, pressed, released = make_matcher()
    m.register('dictate', parse_qt_shortcut('Ctrl+Shift+Space'))

    m.on_press(VK_LCONTROL)   # not enough yet
    assert pressed == []
    m.on_press(VK_LSHIFT)     # still not enough
    assert pressed == []
    m.on_press(VK_SPACE)      # complete – fires
    assert pressed == ['dictate']

    # Hold (auto-repeat space presses) → no new fires
    m.on_press(VK_SPACE); m.on_press(VK_SPACE)
    assert pressed == ['dictate']

    # Release space – binding no longer satisfied → fires released
    m.on_release(VK_SPACE)
    assert released == ['dictate']

    # Cleaning up the modifiers shouldn't fire anything else
    m.on_release(VK_LSHIFT)
    m.on_release(VK_LCONTROL)
    assert pressed == ['dictate']
    assert released == ['dictate']
    print("PASS chord_with_modifiers")


def test_release_any_modifier_stops():
    """Release of any key in the chord ends the hold (matches user expectation
    – hold-to-talk should stop the moment you lift any of the keys)."""
    m, pressed, released = make_matcher()
    m.register('dictate', parse_qt_shortcut('Ctrl+Shift+Space'))

    m.on_press(VK_LCONTROL); m.on_press(VK_LSHIFT); m.on_press(VK_SPACE)
    assert pressed == ['dictate']

    # Release CTRL first – binding's CTRL token is gone → stop
    m.on_release(VK_LCONTROL)
    assert released == ['dictate']
    print("PASS release_any_modifier_stops")


def test_left_or_right_modifier_works():
    """Pressing right Ctrl satisfies a binding stored as Ctrl. Both physical
    keys normalize to the same canonical token."""
    m, pressed, _ = make_matcher()
    m.register('dictate', parse_qt_shortcut('Ctrl+Space'))

    m.on_press(VK_RCONTROL)
    m.on_press(VK_SPACE)
    assert pressed == ['dictate']
    print("PASS left_or_right_modifier_works")


def test_altgr_does_not_misfire_ctrl_binding():
    """Reproduce the Windows AltGr quirk: pressing AltGr fires ctrl_l +
    alt_gr. A user-bound Ctrl-modified hotkey must NOT mis-fire when the
    user types AltGr-composed characters."""
    m, pressed, _ = make_matcher()
    m.register('dictate', parse_qt_shortcut('Ctrl+E'))  # imagine user binds Ctrl+E

    # Windows fires both, ~2ms apart, in this order:
    m.on_press(VK_LCONTROL)
    m.on_press(VK_RALT)
    # User now types 'e' to compose an é
    m.on_press(ord('E'))
    # If we mis-fired, pressed would have 'dictate'. With AltGr-strip it doesn't.
    assert pressed == [], f"unexpected fire: {pressed}"

    m.on_release(ord('E'))
    m.on_release(VK_RALT)
    m.on_release(VK_LCONTROL)
    print("PASS altgr_does_not_misfire_ctrl_binding")


def test_unregister():
    m, pressed, _ = make_matcher()
    m.register('dictate', parse_qt_shortcut('Num+'))
    m.unregister('dictate')

    m.on_press(VK_NUM_ADD)
    m.on_release(VK_NUM_ADD)
    assert pressed == []
    print("PASS unregister")


def test_multiple_bindings():
    """Both F9 and Num+ should fire independently."""
    m, pressed, released = make_matcher()
    m.register('dictate_a', parse_qt_shortcut('F9'))
    m.register('dictate_b', parse_qt_shortcut('Num+'))

    m.on_press(VK_F9)
    m.on_release(VK_F9)
    m.on_press(VK_NUM_ADD)
    m.on_release(VK_NUM_ADD)

    assert pressed == ['dictate_a', 'dictate_b']
    assert released == ['dictate_a', 'dictate_b']
    print("PASS multiple_bindings")


if __name__ == "__main__":
    test_parse()
    test_single_key_hold()
    test_chord_with_modifiers()
    test_release_any_modifier_stops()
    test_left_or_right_modifier_works()
    test_altgr_does_not_misfire_ctrl_binding()
    test_unregister()
    test_multiple_bindings()
    print()
    print("All tests passed.")
