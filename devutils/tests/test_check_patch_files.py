# -*- coding: UTF-8 -*-

# Copyright (c) 2020 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE.ungoogled_chromium file.
"""Test check_patch_files.py"""

import logging
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'utils'))
from _common import ENCODING, get_logger, set_logging_level

sys.path.pop(0)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_patch_files import (
    _PERSONA_BUILD_INTEGRITY_FILE_GROUPS, _PERSONA_PROFILE_MANAGEMENT_GROUPS,
    _PERSONA_CONTRACT_GROUPS, _PERSONA_RUNTIME_HOOK_GROUPS, _PERSONA_SETTINGS_MANUAL_FIELD_GROUPS,
    check_persona_build_integrity, check_persona_contract_coverage,
    check_persona_profile_management_coverage, check_persona_runtime_hook_coverage,
    check_persona_randomization_coverage, check_persona_settings_i18n_key_coverage,
    check_persona_settings_manual_field_coverage, check_series_duplicates,
    check_tracked_patch_backups, check_unused_patches)

sys.path.pop(0)


def test_check_series_duplicates():
    """Test check_series_duplicates"""

    set_logging_level(logging.DEBUG)

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        series_path = Path(tmpdirname, 'series')

        get_logger().info('Check no duplicates')
        series_path.write_text('\n'.join([
            'a.patch',
            'b.patch',
            'c.patch',
        ]), encoding=ENCODING)
        assert not check_series_duplicates(patches_dir)

        get_logger().info('Check duplicates')
        series_path.write_text('\n'.join([
            'a.patch',
            'b.patch',
            'c.patch',
            'a.patch',
        ]),
                               encoding=ENCODING)
        assert check_series_duplicates(patches_dir)


def test_check_unused_patches_ignores_editor_backups():
    """Patch editor backups are not source-of-truth queue entries."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        (patches_dir / 'series').write_text('a.patch\n', encoding=ENCODING)
        (patches_dir / 'a.patch').write_text('', encoding=ENCODING)
        (patches_dir / 'a.patch~').write_text('backup', encoding=ENCODING)

        assert not check_unused_patches(patches_dir)


def test_check_tracked_patch_backups_rejects_indexed_backup():
    """Indexed editor backup files must fail the tracked-backup guard."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        root = Path(tmpdirname)
        patches_dir = root / 'patches'
        patches_dir.mkdir()
        (patches_dir / 'series').write_text('a.patch\n', encoding=ENCODING)
        (patches_dir / 'a.patch').write_text('', encoding=ENCODING)
        (patches_dir / 'a.patch~').write_text('backup', encoding=ENCODING)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run(['git', 'add', 'patches/a.patch~'], cwd=root, check=True)

        assert check_tracked_patch_backups(patches_dir)


def _write_persona_guard_patch(patches_dir, body, patch_name='persona-guard.patch'):
    patch_path = patches_dir / 'helium' / 'core'
    patch_path.mkdir(parents=True, exist_ok=True)
    added_lines = ''.join(f'+{line}\n' for line in body.splitlines())
    (patch_path / patch_name).write_text(
        f'--- /dev/null\n'
        f'+++ b/chrome/browser/resources/settings/persona_page.ts\n'
        f'@@ -0,0 +1,{len(body.splitlines())} @@\n'
        f'{added_lines}',
        encoding=ENCODING)
    (patches_dir / 'series').write_text(f'helium/core/{patch_name}\n', encoding=ENCODING)


def _tokens_from_groups(groups):
    return '\n'.join(token for tokens in groups.values() for token in tokens)


def _write_multi_file_patch(patches_dir, files, patch_name, series_entries=None):
    patch_dir = patches_dir / 'helium' / 'core'
    patch_dir.mkdir(parents=True, exist_ok=True)
    sections = []
    for path, body in files.items():
        body_lines = body.splitlines()
        added_lines = ''.join(f'+{line}\n' for line in body_lines)
        sections.append(f'--- /dev/null\n+++ b/{path}\n'
                        f'@@ -0,0 +1,{len(body_lines)} @@\n{added_lines}')
    (patch_dir / patch_name).write_text(''.join(sections), encoding=ENCODING)
    entries = series_entries or [f'helium/core/{patch_name}']
    (patches_dir / 'series').write_text('\n'.join(entries) + '\n', encoding=ENCODING)


def _build_integrity_files():
    files = {}
    for requirements in _PERSONA_BUILD_INTEGRITY_FILE_GROUPS.values():
        for path, token in requirements:
            files.setdefault(path, []).append(token)
    return {path: '\n'.join(tokens) for path, tokens in files.items()}


def test_check_persona_runtime_hook_coverage():
    """Test persona runtime hook coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_RUNTIME_HOOK_GROUPS)
        _write_persona_guard_patch(patches_dir, full_guard_tokens)
        assert not check_persona_runtime_hook_coverage(patches_dir)

        _write_persona_guard_patch(patches_dir,
                                   full_guard_tokens.replace('HeliumNoiseFeature::kCanvas\n', ''))
        assert check_persona_runtime_hook_coverage(patches_dir)


def test_check_persona_contract_coverage():
    """Test persona contract coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_CONTRACT_GROUPS)
        _write_persona_guard_patch(patches_dir, full_guard_tokens, 'persona-contract-guard.patch')
        assert not check_persona_contract_coverage(patches_dir)

        _write_persona_guard_patch(patches_dir,
                                   full_guard_tokens.replace('ClonePresetIntoProfile\n', ''),
                                   'persona-contract-guard.patch')
        assert check_persona_contract_coverage(patches_dir)


def test_check_persona_build_integrity():
    """Test persona source-of-truth compile contract guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        files = _build_integrity_files()
        _write_multi_file_patch(patches_dir, files, 'persona-build-integrity-guard.patch')
        assert not check_persona_build_integrity(patches_dir)

        files.pop('third_party/blink/renderer/core/execution_context/navigator_base.h')
        _write_multi_file_patch(patches_dir, files, 'persona-build-integrity-guard.patch')
        assert check_persona_build_integrity(patches_dir)


def test_check_persona_build_integrity_requires_owning_file():
    """Tokens must remain in their owning file, not a substitute path."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        files = _build_integrity_files()
        token = files.pop('third_party/blink/renderer/core/execution_context/navigator_base.h')
        files['chrome/browser/resources/settings/persona_page.ts'] = token
        _write_multi_file_patch(patches_dir, files, 'persona-build-integrity-guard.patch')

        assert check_persona_build_integrity(patches_dir)


def test_check_persona_build_integrity_observes_later_removals():
    """Later series patches can remove earlier integrity tokens."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        files = _build_integrity_files()
        first_patch = 'persona-build-integrity-guard.patch'
        second_patch = 'persona-remove-device-memory.patch'
        entries = [f'helium/core/{first_patch}', f'helium/core/{second_patch}']
        _write_multi_file_patch(patches_dir, files, first_patch, entries)
        removed_path = 'third_party/blink/renderer/core/execution_context/navigator_base.h'
        patch_dir = patches_dir / 'helium' / 'core'
        (patch_dir / second_patch).write_text(
            f'--- a/{removed_path}\n+++ b/{removed_path}\n'
            '@@ -1,1 +0,0 @@\n-float deviceMemory() const;\n',
            encoding=ENCODING)

        assert check_persona_build_integrity(patches_dir)


def test_check_persona_settings_i18n_key_coverage():
    """UI persona i18n keys must map 1:1 to provider string entries."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        ui_patch = 'persona-settings-ui.patch'
        provider_patch = 'services-prefs.patch'
        entries = [f'helium/core/{provider_patch}', f'helium/core/{ui_patch}']
        ui_html = 'chrome/browser/resources/settings/privacy_page/persona_page.html'
        provider_cc = ('chrome/browser/ui/webui/settings/'
                       'settings_localized_strings_provider.cc')
        _write_multi_file_patch(patches_dir, {
            ui_html: '<div>$i18n{personaTitle}</div>',
        }, ui_patch, entries)
        _write_multi_file_patch(patches_dir, {
            provider_cc: '{"personaTitle", IDS_SETTINGS_PERSONA_TITLE},',
        }, provider_patch, entries)
        assert not check_persona_settings_i18n_key_coverage(patches_dir)

        _write_multi_file_patch(patches_dir, {
            provider_cc: '{"personaOther", IDS_SETTINGS_PERSONA_OTHER},',
        }, provider_patch, entries)
        assert check_persona_settings_i18n_key_coverage(patches_dir)


def test_check_persona_settings_i18n_key_coverage_accepts_later_provider_mapping():
    """Later Persona patches may add their UI key and provider mapping together."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        patch_name = 'persona-late-settings.patch'
        ui_html = 'chrome/browser/resources/settings/privacy_page/persona_page.html'
        provider_cc = ('chrome/browser/ui/webui/settings/'
                       'settings_localized_strings_provider.cc')
        _write_multi_file_patch(
            patches_dir, {
                ui_html: '<div>$i18n{personaLater}</div>',
                provider_cc: '{"personaLater", IDS_SETTINGS_PERSONA_LATER},',
            }, patch_name)

        assert not check_persona_settings_i18n_key_coverage(patches_dir)


def test_check_persona_profile_management_coverage():
    """Test persona profile management coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_PROFILE_MANAGEMENT_GROUPS)
        _write_persona_guard_patch(patches_dir, full_guard_tokens,
                                   'persona-profile-management-guard.patch')
        assert not check_persona_profile_management_coverage(patches_dir)

        _write_persona_guard_patch(patches_dir,
                                   full_guard_tokens.replace('PersonaIndicatorButton\n', ''),
                                   'persona-profile-management-guard.patch')
        assert check_persona_profile_management_coverage(patches_dir)


def test_check_persona_settings_manual_field_coverage():
    """Test persona settings manual field coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_SETTINGS_MANUAL_FIELD_GROUPS)

        _write_persona_guard_patch(patches_dir, full_guard_tokens)
        assert not check_persona_settings_manual_field_coverage(patches_dir)

        _write_persona_guard_patch(
            patches_dir, full_guard_tokens.replace('editablePersona_.fontRendering.engine\n', ''))
        assert check_persona_settings_manual_field_coverage(patches_dir)


def test_check_persona_randomization_coverage_requires_configured_tokens():
    """Test randomization patches cannot silently bypass coverage checks."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)

        _write_persona_guard_patch(patches_dir, 'SavePersona();', 'persona-settings-ui.patch')
        assert not check_persona_randomization_coverage(patches_dir)

        _write_persona_guard_patch(patches_dir, 'SavePersona();',
                                   'persona-consistent-randomize-ui.patch')
        assert check_persona_randomization_coverage(patches_dir)


if __name__ == '__main__':
    test_check_series_duplicates()
    test_check_unused_patches_ignores_editor_backups()
    test_check_tracked_patch_backups_rejects_indexed_backup()
    test_check_persona_build_integrity()
    test_check_persona_build_integrity_requires_owning_file()
    test_check_persona_build_integrity_observes_later_removals()
    test_check_persona_settings_i18n_key_coverage()
    test_check_persona_contract_coverage()
    test_check_persona_profile_management_coverage()
    test_check_persona_runtime_hook_coverage()
    test_check_persona_randomization_coverage_requires_configured_tokens()
    test_check_persona_settings_manual_field_coverage()
