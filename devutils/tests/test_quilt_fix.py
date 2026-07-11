# -*- coding: UTF-8 -*-
"""Behavioral tests for quilt-fix.sh failure handling."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / 'devutils' / 'quilt-fix.sh'


def _write_fake_quilt(bin_dir, body):
    quilt = bin_dir / 'quilt'
    quilt.parent.mkdir(parents=True)
    quilt.write_text(f'#!/bin/bash\n{body}\n', encoding='utf-8')
    quilt.chmod(0o755)


def _run_script(tmp_path):
    source_tree = tmp_path / 'source'
    source_tree.mkdir()
    env = os.environ.copy()
    env['PATH'] = f'{tmp_path / "bin"}:{env["PATH"]}'
    env['NITROUS_QUILT_SRC'] = str(source_tree)
    return subprocess.run([str(SCRIPT), 'helium/core/test.patch'],
                          cwd=ROOT,
                          env=env,
                          check=False,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True)


def test_quilt_fix_propagates_push_failure(tmp_path):
    """A failed push stops before refresh and preserves its exit status."""
    marker = tmp_path / 'refresh-called'
    _write_fake_quilt(
        tmp_path / 'bin', f'if [[ "$*" == *" push "* ]]; then exit 17; fi\n'
        f'if [[ "$*" == *" refresh"* ]]; then touch "{marker}"; fi')

    result = _run_script(tmp_path)

    assert result.returncode == 17
    assert not marker.exists()


def test_quilt_fix_rejects_wrong_top_patch(tmp_path):
    """Refresh is forbidden unless quilt top exactly matches the target."""
    marker = tmp_path / 'refresh-called'
    _write_fake_quilt(
        tmp_path / 'bin', f'if [[ "$*" == *" top"* ]]; then echo other.patch; exit 0; fi\n'
        f'if [[ "$*" == *" refresh"* ]]; then touch "{marker}"; fi\n'
        'exit 0')

    result = _run_script(tmp_path)

    assert result.returncode != 0
    assert 'other.patch' in result.stdout
    assert not marker.exists()
