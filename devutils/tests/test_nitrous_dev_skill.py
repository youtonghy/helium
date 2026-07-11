# -*- coding: UTF-8 -*-
"""Contract checks for the Nitrous hot-tree development skill."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKILL = ROOT / '.codex' / 'skills' / 'nitrous-dev' / 'SKILL.md'


def test_skill_requires_baseline_before_hot_tree_edit_and_staged_export_after():
    """The documented workflow preserves the two-phase export invariant."""
    content = SKILL.read_text(encoding='utf-8')
    start = content.index('--mode hot-start')
    edit = content.index('Edit only the declared')
    export = content.index('--mode export-hotfix')

    assert start < edit < export
    assert '--mode hot-add' in content


def test_skill_forbids_unsafe_existing_patch_export_paths():
    """Existing patch repair stays separate from hot-tree automatic export."""
    content = SKILL.read_text(encoding='utf-8')

    assert 'Automatic export creates a new root-stack top patch only' in content
    assert 'Do not copy whole files from build/src into an earlier patch' in content
    assert '--mode after-hotfix' not in content
