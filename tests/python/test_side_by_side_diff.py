"""Slice K side-by-side diff parsing + DiffView smoke."""

from __future__ import annotations

from labdesk_ui.widgets.diff_view import DiffView, parse_unified_to_sides


SAMPLE = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,3 @@
 context
-old
+new
 more
"""


def test_parse_unified_pairs_delete_insert():
    left, right = parse_unified_to_sides(SAMPLE)
    assert len(left) == len(right)
    kinds = [(a.kind, b.kind) for a, b in zip(left, right)]
    assert ("delete", "insert") in kinds
    assert ("context", "context") in kinds
    assert ("meta", "meta") in kinds


def test_parse_unified_insert_only_aligns_empty_left():
    left, right = parse_unified_to_sides("@@ -0,0 +1 @@\n+only\n")
    assert any(r.kind == "insert" and r.text == "only" for r in right)
    assert any(l.kind == "empty" for l in left)


def test_diff_view_modes(qapp):
    view = DiffView(placeholder="test")
    view.set_diff(SAMPLE)
    assert view.stack.currentIndex() == DiffView.MODE_UNIFIED
    view.set_mode(DiffView.MODE_SIDE)
    assert view.stack.currentIndex() == DiffView.MODE_SIDE
    assert view.left.toPlainText()
    assert view.right.toPlainText()
    view.clear()
    assert view.left.toPlainText() == ""
    view.close()
