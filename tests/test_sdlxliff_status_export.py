"""Guard the Trados SDLXLIFF / SDLRPX export status mapping (v1.10.259).

Regression: the exporter built only ``{segment_id: target_text}`` and then
defaulted every segment's status to ``'draft'`` (``update_translations`` /
``update_segment``), so a fully *confirmed* project shipped to the client with
**all segments marked Draft** when opened in Trados Studio. The
status -> Trados ``conf`` table was correct but never received anything but
``'draft'``.

These tests lock in:

  1. the status -> ``conf`` mapping on the real ``_replace_seg_attributes``
     writer (confirmed -> Translated, approved/proofread -> ApprovedTranslation,
     rejected -> RejectedTranslation, draft -> Draft), case-insensitively;
  2. the exact regression: a *confirmed* segment must never export as Draft;
  3. that ``update_translations`` carries a per-segment status through to the
     segment, and still defaults to ``'draft'`` when none is supplied
     (backward compatibility).

If anyone reverts to hardcoding ``'draft'`` or drops the statuses plumbing, a
confirmed segment exports as Draft again and these fail.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from modules import sdlppx_handler as sdl


class _Seg:
    """Minimal stand-in exposing only the attributes the exporter reads."""

    def __init__(self, status, segment_id=None, target_text="x", modified=True):
        self.status = status
        self.segment_id = segment_id
        self.target_text = target_text
        self.modified = modified


def _conf_for(status: str, current: str) -> str | None:
    """Run the real <sdl:seg> attribute writer for one segment and return the
    resulting ``conf`` value. ``current`` is the conf already in the file, so a
    real mapping shows up as a change."""
    content = f'<sdl:seg id="1" conf="{current}" />'
    out = sdl._replace_seg_attributes(content, None, {"tu_1": _Seg(status)})
    m = re.search(r'conf="([^"]*)"', out)
    return m.group(1) if m else None


@pytest.mark.parametrize("status,current,expected", [
    ("confirmed", "Draft", "Translated"),
    ("translated", "Draft", "Translated"),
    ("approved", "Draft", "ApprovedTranslation"),
    ("proofread", "Draft", "ApprovedTranslation"),
    ("rejected", "Draft", "RejectedTranslation"),
    ("draft", "Translated", "Draft"),
    ("Confirmed", "Draft", "Translated"),  # case-insensitive
])
def test_status_maps_to_conf(status, current, expected):
    assert _conf_for(status, current) == expected


def test_confirmed_segment_never_exports_as_draft():
    # The exact bug this fixes: a confirmed segment must not come out Draft.
    assert _conf_for("confirmed", current="Draft") == "Translated"


def _handler_with(seg: _Seg) -> "sdl.TradosPackageHandler":
    handler = sdl.TradosPackageHandler.__new__(sdl.TradosPackageHandler)

    class _XF:
        segments = [seg]

    class _Pkg:
        xliff_files = [_XF()]

    handler.package = _Pkg()
    return handler


def test_update_translations_carries_status():
    seg = _Seg("draft", segment_id="tu_5", target_text="")
    handler = _handler_with(seg)
    n = handler.update_translations({"tu_5": "hello"}, {"tu_5": "confirmed"})
    assert n == 1
    assert seg.target_text == "hello"
    assert seg.status == "confirmed"


def test_update_translations_defaults_to_draft_without_statuses():
    seg = _Seg("draft", segment_id="tu_6", target_text="")
    handler = _handler_with(seg)
    handler.update_translations({"tu_6": "x"})  # no statuses supplied
    assert seg.status == "draft"
