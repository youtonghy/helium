# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Tests for applying translations to Chromium XTB resources."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'utils'))
import i18n_apply # pylint: disable=wrong-import-position

sys.path.pop(0)


def _write_translation_inputs(tmp_path, monkeypatch):
    i18n_dir = tmp_path / 'i18n'
    translations_dir = i18n_dir / 'translations'
    translations_dir.mkdir(parents=True)
    source_path = i18n_dir / 'source.gen.json'
    source_path.write_text('[]\n', encoding='utf-8')
    (i18n_dir / 'languages.json').write_text(json.dumps({'zh-CN': 'Chinese (Simplified)'}),
                                             encoding='utf-8')
    translation_path = translations_dir / 'zh-CN.json'
    translation_path.write_text('[]\n', encoding='utf-8')
    monkeypatch.setattr(i18n_apply, 'I18N_DIR', i18n_dir)
    monkeypatch.setattr(i18n_apply, 'SOURCE_PATH', source_path)
    monkeypatch.setattr(i18n_apply, 'TRANSLATIONS_DIR', translations_dir)
    return translation_path


def test_translation_inputs_digest_changes_with_translation(tmp_path, monkeypatch):
    """Changing a translation invalidates the generated-resource state."""
    translation_path = _write_translation_inputs(tmp_path, monkeypatch)
    before = i18n_apply.get_translation_inputs_digest()

    translation_path.write_text('[{"message": "人格配置"}]\n', encoding='utf-8')

    assert i18n_apply.get_translation_inputs_digest() != before


def test_apply_translations_if_needed_uses_current_stamp(tmp_path, monkeypatch):
    """Current inputs skip XTB writes while changed inputs apply again."""
    translation_path = _write_translation_inputs(tmp_path, monkeypatch)
    applications = []
    monkeypatch.setattr(i18n_apply, 'apply_translations', applications.append)
    tree = tmp_path / 'chromium'
    stamp_path = tree / '.nitrous_i18n_stamp'

    assert i18n_apply.apply_translations_if_needed(tree, stamp_path)
    assert not i18n_apply.apply_translations_if_needed(tree, stamp_path)
    translation_path.write_text('[{"message": "人格配置"}]\n', encoding='utf-8')
    assert i18n_apply.apply_translations_if_needed(tree, stamp_path)

    assert applications == [tree, tree]


def test_failed_translation_application_does_not_write_stamp(tmp_path, monkeypatch):
    """A failed XTB update must be retried on the next preparation attempt."""
    _write_translation_inputs(tmp_path, monkeypatch)

    def fail_application(_tree):
        raise RuntimeError('invalid XTB')

    monkeypatch.setattr(i18n_apply, 'apply_translations', fail_application)
    stamp_path = tmp_path / 'chromium' / '.nitrous_i18n_stamp'

    with pytest.raises(RuntimeError, match='invalid XTB'):
        i18n_apply.apply_translations_if_needed(tmp_path / 'chromium', stamp_path)

    assert not stamp_path.exists()
