# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Bundled CJK collections must survive source binary pruning."""

from pathlib import Path

from devutils import update_lists


def test_portable_font_collection_is_kept_but_unrelated_binary_is_pruned(tmp_path):
    """The exception must be limited to the bundled portable font directory."""
    resource = tmp_path / 'font.ttc'
    resource.write_bytes(b'ttcf\x00\x01\x00\x00' * 16)
    assert not update_lists.should_prune(
        resource, Path('third_party/nitrous_fonts/portable/persona-cjk-pinned.ttc'), set(), set())
    assert update_lists.should_prune(resource, Path('third_party/unrelated/data.bin'), set(), set())
