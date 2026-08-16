# -*- coding: UTF-8 -*-
"""Tests for macOS hot-tree quilt state checks."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = ROOT / 'platform' / 'macos' / 'build.sh'


def _write(path, content=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _run_metadata_check(tmp_path, recorded_queue):
    build_dir = tmp_path / 'build'
    source_dir = build_dir / 'src'
    merged_queue = build_dir / 'platform_macos_patches'
    _write(merged_queue / 'series', 'base.patch\n')
    _write(source_dir / '.pc' / '.quilt_patches', f'{recorded_queue}\n')
    _write(source_dir / '.pc' / '.quilt_series', 'series\n')
    _write(source_dir / '.pc' / 'applied-patches', 'base.patch\n')
    env = os.environ.copy()
    env['NITROUS_BUILD_DIR'] = str(build_dir)
    command = f'source "{BUILD_SCRIPT}"; ___helium_validate_hot_tree_metadata'
    return subprocess.run(['bash', '-c', command],
                          cwd=ROOT,
                          env=env,
                          check=False,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True), merged_queue


def _run_syntax_smoke(tmp_path):
    build_dir = tmp_path / 'build'
    source_dir = build_dir / 'src'
    out_dir = source_dir / 'out' / 'Default'
    _write(source_dir / 'third_party' / 'blink' / 'common' / 'navigation' / 'navigation_params.cc')
    _write(out_dir / 'compile_commands.json', '[]\n')
    env = os.environ.copy()
    env['NITROUS_BUILD_DIR'] = str(build_dir)
    command = f'source "{BUILD_SCRIPT}"; ___helium_syntax_smoke'
    return subprocess.run(['bash', '-c', command],
                          cwd=ROOT,
                          env=env,
                          check=False,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True)


def _run_configure_order_check(tmp_path):
    build_dir = tmp_path / 'build'
    env = os.environ.copy()
    env['NITROUS_BUILD_DIR'] = str(build_dir)
    command = (f'source "{BUILD_SCRIPT}"; '
               '___helium_ensure_patches_applied() { echo patches; }; '
               '___helium_ensure_i18n() { echo i18n; }; '
               '___helium_out_ready() { return 0; }; '
               '___helium_config_ready() { return 0; }; '
               '___helium_ensure_configured')
    return subprocess.run(['bash', '-c', command],
                          cwd=ROOT,
                          env=env,
                          check=False,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True)


def test_hot_tree_metadata_accepts_current_merged_queue(tmp_path):
    """The complete current merged stack is a valid hot-tree state."""
    build_dir = tmp_path / 'build'
    result, _queue = _run_metadata_check(tmp_path, build_dir / 'platform_macos_patches')

    assert result.returncode == 0, result.stdout


def test_hot_tree_metadata_rejects_stale_queue_path(tmp_path):
    """A moved checkout fails with a rebuild instruction."""
    result, _queue = _run_metadata_check(tmp_path, tmp_path / 'old' / 'patches')

    assert result.returncode != 0
    assert 'quilt metadata is stale' in result.stdout
    assert 'rebuild build/src' in result.stdout


def test_syntax_smoke_skips_when_generated_headers_are_not_ready(tmp_path):
    """A cold GN output must reach Ninja so it can generate Mojo headers."""
    result = _run_syntax_smoke(tmp_path)

    assert result.returncode == 0, result.stdout
    assert 'generated dependencies are not ready' in result.stdout


def test_i18n_is_applied_after_patches_before_gn_state_check(tmp_path):
    """Localized XTB resources are prepared before existing GN output is reused."""
    result = _run_configure_order_check(tmp_path)

    assert result.returncode == 0, result.stdout
    assert result.stdout.splitlines()[:2] == ['patches', 'i18n']
