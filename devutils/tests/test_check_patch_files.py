# -*- coding: UTF-8 -*-

# Copyright (c) 2020 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE.ungoogled_chromium file.
"""Test check_patch_files.py"""

import logging
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'utils'))
from _common import ENCODING, get_logger, set_logging_level

sys.path.pop(0)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_patch_files import (_PERSONA_RANDOMIZATION_FIELD_GROUPS,
                               _PERSONA_CONTRACT_GROUPS,
                               _PERSONA_RUNTIME_HOOK_GROUPS,
                               _PERSONA_SETTINGS_MANUAL_FIELD_GROUPS,
                               check_persona_contract_coverage,
                               check_persona_randomization_coverage,
                               check_persona_runtime_hook_coverage,
                               check_persona_settings_manual_field_coverage,
                               check_series_duplicates)

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


def _write_persona_guard_patch(patches_dir, body,
                               patch_name='persona-guard.patch'):
    patch_path = patches_dir / 'helium' / 'core'
    patch_path.mkdir(parents=True, exist_ok=True)
    (patch_path / patch_name).write_text(body, encoding=ENCODING)
    (patches_dir / 'series').write_text(
        f'helium/core/{patch_name}\n', encoding=ENCODING)


def _tokens_from_groups(groups):
    return '\n'.join(token for tokens in groups.values() for token in tokens)


def test_check_persona_runtime_hook_coverage():
    """Test persona runtime hook coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_RUNTIME_HOOK_GROUPS)
        _write_persona_guard_patch(patches_dir, full_guard_tokens)
        assert not check_persona_runtime_hook_coverage(patches_dir)

        _write_persona_guard_patch(
            patches_dir, full_guard_tokens.replace(
                'HeliumPersonaAllowsWebNn\n', ''))
        assert check_persona_runtime_hook_coverage(patches_dir)


def test_check_persona_contract_coverage():
    """Test persona contract coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(_PERSONA_CONTRACT_GROUPS)
        _write_persona_guard_patch(
            patches_dir, full_guard_tokens, 'persona-contract-guard.patch')
        assert not check_persona_contract_coverage(patches_dir)

        _write_persona_guard_patch(
            patches_dir,
            full_guard_tokens.replace('PersonaRuntimeOverride::ApplyGlobal\n', ''),
            'persona-contract-guard.patch')
        assert check_persona_contract_coverage(patches_dir)


def test_check_persona_randomization_coverage():
    """Test persona randomization coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(
            _PERSONA_RANDOMIZATION_FIELD_GROUPS)

        _write_persona_guard_patch(
            patches_dir, full_guard_tokens, 'persona-random-guard.patch')
        assert not check_persona_randomization_coverage(patches_dir)

        _write_persona_guard_patch(
            patches_dir,
            full_guard_tokens.replace('applyRandomMediaDevices_\n', ''),
            'persona-random-guard.patch')
        assert check_persona_randomization_coverage(patches_dir)


def test_check_persona_settings_manual_field_coverage():
    """Test persona settings manual field coverage guard."""

    with tempfile.TemporaryDirectory() as tmpdirname:
        patches_dir = Path(tmpdirname)
        full_guard_tokens = _tokens_from_groups(
            _PERSONA_SETTINGS_MANUAL_FIELD_GROUPS)

        _write_persona_guard_patch(patches_dir, full_guard_tokens)
        assert not check_persona_settings_manual_field_coverage(patches_dir)

        _write_persona_guard_patch(
            patches_dir,
            full_guard_tokens.replace(
                'editablePersona_.fontRendering.profileVersion\n', ''))
        assert check_persona_settings_manual_field_coverage(patches_dir)


if __name__ == '__main__':
    test_check_series_duplicates()
    test_check_persona_contract_coverage()
    test_check_persona_runtime_hook_coverage()
    test_check_persona_randomization_coverage()
    test_check_persona_settings_manual_field_coverage()
