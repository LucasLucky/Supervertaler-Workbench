"""Input-device enumeration + name → index resolution for the Voice surface.

The dictation engines (push-to-talk, Always-On) and the Voice tab's
microphone picker all need to ask sounddevice the same two questions:

  1. What input devices does the user have? – for the dropdown
  2. Given a saved device name, what's the current device index? – at
     record time, because indices can shuffle between sessions (USB
     devices added / removed, default device changed, etc.)

This module centralises both calls so the engines and the UI agree on
device identity and on what "default" means.
"""
from __future__ import annotations

from typing import List, Optional


# Sentinel value the Voice tab uses for "let the OS pick" – stored in
# dictation_settings.mic_device when the user wants the system default.
# Resolving this to ``None`` at record time tells sounddevice to use
# whichever input is currently the OS default.
DEFAULT_SENTINEL = "__default__"


def list_input_devices() -> List[str]:
    """Return the list of available *input* devices' names.

    Empty list on any sounddevice failure (no PortAudio host, etc.) –
    the UI then just shows "System default" as the only option.
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return []

    seen = set()
    names: List[str] = []
    for dev in devices:
        try:
            if dev.get('max_input_channels', 0) <= 0:
                continue
        except Exception:
            continue
        name = dev.get('name')
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def resolve_device_index(saved_name: Optional[str]) -> Optional[int]:
    """Map a saved device name to the current sounddevice device index.

    Returns:
        - ``None`` if ``saved_name`` is empty, the default sentinel, or
          the named device is no longer attached. In all of those cases
          sounddevice falls back to the OS default input, which is the
          right thing.
        - An integer index suitable for the ``device=`` kwarg of
          ``sd.rec`` / ``sd.InputStream`` otherwise.
    """
    if not saved_name or saved_name == DEFAULT_SENTINEL:
        return None
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return None
    for idx, dev in enumerate(devices):
        try:
            if dev.get('max_input_channels', 0) <= 0:
                continue
            if dev.get('name') == saved_name:
                return idx
        except Exception:
            continue
    # Saved device is gone – fall back to OS default rather than raising.
    return None
