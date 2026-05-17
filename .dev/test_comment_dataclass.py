"""Quick smoke test for the new Comment + Segment data model (v1.10.57).

Run from the repo root with:
    python .dev/test_comment_dataclass.py

Verifies:
 - Brand-new segments start with empty notes + comments.
 - Legacy projects with notes-only round-trip into a single Comment.
 - add_comment / update_comment / remove_comment / get_comment work
   and keep the legacy notes mirror in sync.
 - replace_all_comments_with_text preserves the comment id when
   editing a single existing segment-level comment in place.
 - to_dict/from_dict serialise comments[] correctly (List[Comment]
   serialises to a list of dicts; nested Comment.from_dict on load).
"""
from __future__ import annotations
import sys, importlib.util, os
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

# Loading Supervertaler.py as a module would pull PyQt6 and many other
# heavy deps. Instead, extract just the Comment + Segment class bodies
# and a few helpers via a clean re-exec into a minimal namespace.
src = (repo_root / 'Supervertaler.py').read_text(encoding='utf-8')

# Pull out everything from "@dataclass\nclass Comment:" up to the start of
# the Project class. That window contains Comment + Segment + their helpers.
start = src.index('@dataclass\nclass Comment:')
end = src.index('@dataclass\nclass Project:')
window = src[start:end]

# Build a namespace with the deps these classes reference.
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime

ns: dict = {
    'dataclass': dataclass,
    'field': field,
    'asdict': asdict,
    'Dict': Dict,
    'List': List,
    'Any': Any,
    'Optional': Optional,
    'datetime': datetime,
    # A stand-in for the DEFAULT_STATUS the real Segment references.
    'DEFAULT_STATUS': type('S', (), {'key': 'untranslated'})(),
    # Pass-through for invisible-marker stripping; not what we're testing.
    'strip_invisible_markers': lambda s: s,
}
exec(window, ns)

Comment = ns['Comment']
Segment = ns['Segment']

# --- Test 1: brand-new segment, no notes, no comments ---
s1 = Segment(id=1, source='Hello')
assert s1.notes == ''
assert s1.comments == []
print('TEST 1 (new segment): OK')

# --- Test 2: legacy load (notes only, comments missing) ---
s2 = Segment.from_dict({'id': 2, 'source': 'Hello', 'notes': 'My old note text'})
assert s2.notes == 'My old note text'
assert len(s2.comments) == 1
assert s2.comments[0].text == 'My old note text'
assert s2.comments[0].id
assert s2.comments[0].anchor_field == ''
print(f'TEST 2 (legacy migration): OK (uuid {s2.comments[0].id[:8]}…)')

# --- Test 3: add_comment keeps notes in sync; anchor field works ---
s3 = Segment(id=3, source='Hello')
s3.add_comment('First comment', author='Michael')
s3.add_comment('Second comment', author='Michael',
                anchor_field='source', anchor_start=0, anchor_end=5)
assert len(s3.comments) == 2
assert s3.notes == 'First comment\n\nSecond comment'
assert s3.comments[1].is_anchored
print('TEST 3 (add_comment + sync): OK')

# --- Test 4: round-trip via to_dict/from_dict ---
d3 = s3.to_dict()
assert isinstance(d3['comments'], list)
assert isinstance(d3['comments'][0], dict)
s3b = Segment.from_dict(d3)
assert len(s3b.comments) == 2
assert s3b.comments[0].text == 'First comment'
assert isinstance(s3b.comments[0], Comment)
assert s3b.comments[1].is_anchored
assert s3b.comments[1].anchor_end == 5
print('TEST 4 (round-trip): OK')

# --- Test 5: legacy bridge — edit in place preserves the id ---
s4 = Segment(id=4, source='Hello', notes='original')
assert len(s4.comments) == 1
original_id = s4.comments[0].id
s4.replace_all_comments_with_text('edited', author='M')
assert len(s4.comments) == 1
assert s4.comments[0].text == 'edited'
assert s4.comments[0].id == original_id, 'in-place edit should preserve id'
print('TEST 5 (legacy bridge in-place edit): OK')

# --- Test 6: legacy bridge collapses multi -> one ---
s5 = Segment(id=5, source='Hello')
s5.add_comment('a')
s5.add_comment('b')
s5.replace_all_comments_with_text('merged', author='M')
assert len(s5.comments) == 1
assert s5.comments[0].text == 'merged'
print('TEST 6 (legacy bridge collapses multi -> one): OK')

# --- Test 7: empty string clears the list ---
s5.replace_all_comments_with_text('')
assert s5.comments == []
assert s5.notes == ''
print('TEST 7 (empty string clears): OK')

# --- Test 8: update / get / remove ---
s6 = Segment(id=6, source='Hello')
c = s6.add_comment('foo')
assert s6.get_comment(c.id) is c
assert s6.update_comment(c.id, 'bar')
assert s6.comments[0].text == 'bar'
assert s6.notes == 'bar'
assert s6.remove_comment(c.id)
assert s6.comments == []
print('TEST 8 (update / get / remove): OK')

# --- Test 9: legacy ⚠️ PROOFREAD migration still works ---
s7 = Segment.from_dict({
    'id': 7, 'source': 'x',
    'notes': 'user note ⚠️ PROOFREAD: AI flagged this --- more user text',
})
# The proofread-block migration runs BEFORE comments migration, and
# the cleaned-up notes that survive should land in the comment.
assert '⚠️ PROOFREAD:' not in s7.notes
assert s7.proofreading_notes.get('legacy') == 'AI flagged this'
assert len(s7.comments) == 1
print('TEST 9 (PROOFREAD migration still works): OK')

print()
print('ALL TESTS PASSED')
