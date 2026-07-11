# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Tests for the repository lint checks."""
# pylint: disable=protected-access

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _lint_tests

sys.path.pop(0)


def test_patch_tree_lint_ignores_non_source_backups():
    """Editor backups and patch notes are not queue entries."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        root = Path(tmpdirname)
        patches_dir = root / 'patches'
        patches_dir.mkdir()
        (patches_dir / 'series').write_text('a.patch\n', encoding='utf-8')
        (patches_dir / 'a.patch').write_text('', encoding='utf-8')
        (patches_dir / 'a.patch~').write_text('backup', encoding='utf-8')
        (patches_dir / 'README.md').write_text('notes', encoding='utf-8')
        _lint_tests._init(root)

        _lint_tests.a_all_patches_in_tree_are_in_series()


if __name__ == '__main__':
    test_patch_tree_lint_ignores_non_source_backups()
