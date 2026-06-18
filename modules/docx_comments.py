"""
DOCX comment extraction
========================

Reads Word review comments out of a .docx so they can be imported into
Supervertaler as *actual comments* (anchored, author-tagged) rather than
as translatable segments.

A Word comment has three relevant pieces, spread across two XML parts:

* ``word/comments.xml`` – the comment body, author, date and id:
      <w:comment w:id="3" w:author="Jane Roe" w:date="..." w:initials="JR">
          <w:p><w:r><w:t>comment text</w:t></w:r></w:p>
      </w:comment>

* ``word/document.xml`` – where the comment anchors, as a run range:
      <w:commentRangeStart w:id="3"/> ...runs... <w:commentRangeEnd w:id="3"/>
  The text of the runs between start and end is the highlighted span the
  reviewer attached the comment to. We use that span to find the matching
  Supervertaler segment.

This module is read-only and has no Okapi/Qt dependency.
"""

from __future__ import annotations

import re
import zipfile
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

# WordprocessingML main namespace
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _W}


def _q(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def _comment_text(comment_el: ET.Element) -> str:
    """Concatenate the visible text of a <w:comment>, joining paragraphs
    with newlines."""
    paras = []
    for p in comment_el.iter(_q("p")):
        runs = [t.text or "" for t in p.iter(_q("t"))]
        paras.append("".join(runs))
    return "\n".join(part for part in paras).strip()


def _parse_comments_xml(data: bytes) -> Dict[str, Dict[str, str]]:
    """Return {comment_id: {author, date, initials, text}}."""
    out: Dict[str, Dict[str, str]] = {}
    root = ET.fromstring(data)
    for c in root.findall(_q("comment")):
        cid = c.get(_q("id"))
        if cid is None:
            continue
        out[cid] = {
            "author": c.get(_q("author"), ""),
            "date": c.get(_q("date"), ""),
            "initials": c.get(_q("initials"), ""),
            "text": _comment_text(c),
        }
    return out


# How much context to capture from the START of a comment range. We capture
# from the comment's start through the end of its paragraph (capped), NOT just
# the highlighted span: the highlighted word alone is often ambiguous — e.g. a
# word that also appears in the document title — whereas the run of text that
# follows it uniquely identifies the segment. Capturing the whole range is
# unreliable anyway (Word duplicates drawing text via mc:AlternateContent, and
# reviewers sometimes select huge blocks).
_ANCHOR_MAX = 100


def _parse_anchor_spans(data: bytes) -> Dict[str, str]:
    """Return {comment_id: anchor_text} where anchor_text is the run text from
    the START of the comment range to the end of that paragraph (capped at
    ~100 chars).

    We walk document.xml in order. When a comment id's range opens we begin
    accumulating run text and keep going *past* commentRangeEnd until the cap
    or the end of the start paragraph — so even a one-word highlight yields
    enough following context to locate its segment unambiguously. Consecutive
    exact-duplicate runs are skipped to absorb Word's mc:AlternateContent
    (Choice/Fallback) doubling.
    """
    spans: Dict[str, List[str]] = {}
    done: set = set()
    capturing: set = set()

    for _evt, el in ET.iterparse(_BytesReader(data), events=("end",)):
        tag = el.tag
        if tag == _q("commentRangeStart"):
            cid = el.get(_q("id"))
            if cid is not None and cid not in done:
                capturing.add(cid)
                spans.setdefault(cid, [])
        elif tag == _q("t") and capturing:
            txt = el.text or ""
            if not txt:
                continue
            for cid in list(capturing):
                if cid in done:
                    continue
                buf = spans[cid]
                # Skip a run that exactly repeats what we already have
                # (mc:Choice/Fallback duplication of the same drawing text).
                if buf and "".join(buf).endswith(txt):
                    continue
                buf.append(txt)
                if sum(len(p) for p in buf) >= _ANCHOR_MAX:
                    done.add(cid)
        elif tag == _q("p"):
            # End of a paragraph: stop capturing anything that started in it so
            # the anchor context never bleeds into unrelated later text.
            capturing.clear()

    return {cid: "".join(parts).strip()[:_ANCHOR_MAX]
            for cid, parts in spans.items()}


class _BytesReader:
    """Minimal file-like wrapper so ET.iterparse can read a bytes blob."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


def parse_docx_comments(docx_path: str) -> List[Dict[str, Any]]:
    """Extract Word comments from a .docx.

    Returns a list of dicts (in comment-id order) with keys:
        id, author, date, initials, text, anchor_text

    ``anchor_text`` is the highlighted run text the comment is attached to
    (may be empty if the comment has no range, e.g. a whole-paragraph
    comment). Returns [] if the document has no comments.
    """
    try:
        with zipfile.ZipFile(docx_path) as z:
            names = set(z.namelist())
            if "word/comments.xml" not in names:
                return []
            comments = _parse_comments_xml(z.read("word/comments.xml"))
            anchors: Dict[str, str] = {}
            if "word/document.xml" in names:
                try:
                    anchors = _parse_anchor_spans(z.read("word/document.xml"))
                except Exception:
                    anchors = {}
    except (zipfile.BadZipFile, KeyError, OSError):
        return []

    result: List[Dict[str, Any]] = []
    # Sort by numeric id when possible so they import in document order.
    def _key(cid: str):
        m = re.match(r"\d+", cid or "")
        return (0, int(m.group())) if m else (1, cid)

    for cid in sorted(comments.keys(), key=_key):
        info = comments[cid]
        if not info["text"]:
            continue
        result.append({
            "id": cid,
            "author": info["author"],
            "date": info["date"],
            "initials": info["initials"],
            "text": info["text"],
            "anchor_text": anchors.get(cid, ""),
        })
    return result
