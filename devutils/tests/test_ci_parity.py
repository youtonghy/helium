# -*- coding: UTF-8 -*-
"""Checks that local validation stays equivalent to the CI workflow.

Every gap covered here produced a red CI job that a local run had reported as
green, so the parity mechanisms need regression protection of their own.
"""

import configparser
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNNER = ROOT / '.codex' / 'skills' / 'nitrous-validate' / 'scripts' / 'run_validation.py'
GUARD = ROOT / 'devutils' / 'agent_patch_guard.py'
CI_SETUP = ROOT / '.github' / 'actions' / 'ci-setup' / 'action.yml'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
SYSTEM_PACKAGES = ROOT / '.ci_system_packages.txt'
REQUIREMENTS = ROOT / '.cirrus_requirements.txt'


def parse_system_packages():
    """Return (package, binary) rows declared for CI runners."""
    rows = []
    for raw_line in SYSTEM_PACKAGES.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if line:
            rows.append(tuple(line.split()))
    return rows


def test_system_package_manifest_is_well_formed():
    """The manifest is the single source of truth for both sides."""
    rows = parse_system_packages()
    assert rows, 'expected at least one declared package'
    for row in rows:
        assert len(row) == 2, f'expected "<package> <binary>", got {row}'


def test_ci_setup_installs_from_the_shared_package_manifest():
    """CI must not hardcode a package list that local checks cannot see."""
    content = CI_SETUP.read_text(encoding='utf-8')

    assert '.ci_system_packages.txt' in content
    # A hardcoded apt list would drift from the manifest silently.
    assert 'install -y --no-install-recommends xz-utils' not in content


def test_quilt_is_declared_because_tests_shell_out_to_it():
    """Regression: CI lacked quilt while the export tests invoked it."""
    binaries = {binary for _, binary in parse_system_packages()}
    assert 'quilt' in binaries
    assert 'patch' in binaries


def test_runner_checks_system_tools_and_source_freshness():
    """Both reverse-drift gaps are wired into the runner."""
    content = RUNNER.read_text(encoding='utf-8')

    assert 'def check_system_tools(' in content
    assert 'def check_source_tree_freshness(' in content
    assert 'def report_version_drift(' in content


def test_runner_refuses_to_call_an_empty_scope_a_pass():
    """Regression: a committed change made auto-scope select nothing."""
    content = RUNNER.read_text(encoding='utf-8')

    assert 'This is not a pass' in content
    assert '--require-checks' in content
    assert 'def default_changed_from(' in content


def test_delivery_gate_requires_checks_and_reports_every_failure():
    """pre-build must never pass without inspecting the gated files."""
    content = GUARD.read_text(encoding='utf-8')

    assert '--require-checks' in content
    assert '--keep-going' in content
    assert 'def default_changed_from(' in content


def test_neither_scope_default_is_bare_head():
    """HEAD as a diff base hides committed work from the gate."""
    for path in (RUNNER, GUARD):
        content = path.read_text(encoding='utf-8')
        assert "'--changed-from',\n                        default='HEAD'" not in content
        assert "default='HEAD', help='Git ref" not in content


def test_pinned_requirements_cover_every_tool_the_ci_jobs_run():
    """Version drift silently breaks equivalence, so the pins must be complete."""
    pins = set()
    for raw_line in REQUIREMENTS.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if '==' in line:
            pins.add(line.partition('==')[0].strip().lower())

    workflow = CI_WORKFLOW.read_text(encoding='utf-8')
    if 'yapf' in workflow:
        assert 'yapf' in pins
    if 'pylint' in workflow:
        assert 'pylint' in pins
    assert 'pytest' in pins


def test_runner_help_exposes_the_parity_flags():
    """The flags are the documented interface, so they must actually parse."""
    result = subprocess.run([sys.executable, str(RUNNER), '--help'],
                            cwd=ROOT,
                            check=False,
                            stdout=subprocess.PIPE,
                            text=True)

    assert result.returncode == 0
    for flag in ('--ci-env', '--keep-going', '--require-checks', '--skip-system-tools'):
        assert flag in result.stdout


def test_declared_download_components_have_output_paths_to_verify():
    """Freshness checking relies on output_path being present per component."""
    checked = 0
    for manifest in ('downloads.ini', 'deps.ini'):
        parser = configparser.ConfigParser()
        parser.read(ROOT / manifest, encoding='utf-8')
        for component in parser.sections():
            output_path = parser[component].get('output_path', fallback='')
            if output_path.strip() not in ('', './', '.'):
                checked += 1
    assert checked >= 4, 'expected the bundled dependencies to be verifiable'
