# -*- coding: UTF-8 -*-
"""Contract checks for the Nitrous hot-tree development skill."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS = ROOT / 'AGENTS.md'
SKILL = ROOT / '.codex' / 'skills' / 'nitrous-dev' / 'SKILL.md'
VALIDATE_SKILL = ROOT / '.codex' / 'skills' / 'nitrous-validate' / 'SKILL.md'


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


def test_all_agent_guidance_requires_pre_build_before_mutating_task_handoff():
    """Every repository-changing task uses the packaging-equivalent preflight."""
    command = 'python3 devutils/agent_patch_guard.py --mode pre-build'
    agents = AGENTS.read_text(encoding='utf-8')
    dev_skill = SKILL.read_text(encoding='utf-8')
    validate_skill = VALIDATE_SKILL.read_text(encoding='utf-8')

    assert '任何产生仓库修改的任务在交付前' in agents
    assert '不要求实际执行 `he auto-package`' in agents
    assert 'Every task that changes repository files MUST run' in dev_skill
    assert 'Every task that changes repository files MUST run' in validate_skill
    assert all(command in content for content in (agents, dev_skill, validate_skill))
