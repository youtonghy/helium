# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Tests for i18n_lint.py."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from i18n_lint import (find_missing_persona_translations, get_translation_message_errors)

sys.path.pop(0)


def test_find_missing_persona_translations():
    """Required locales must cover every current Persona source string."""

    source = [{
        'name': 'IDS_SETTINGS_PERSONA_TITLE',
        'message': 'Persona',
    }, {
        'name': 'IDS_SETTINGS_OTHER_TITLE',
        'message': 'Other',
    }]
    with tempfile.TemporaryDirectory() as tmpdirname:
        translations_dir = Path(tmpdirname)
        (translations_dir / 'zh-CN.json').write_text(json.dumps([{
            'name': 'IDS_SETTINGS_PERSONA_TITLE',
            'source': 'Persona',
            'message': '人格配置',
        }]),
                                                     encoding='utf-8')
        (translations_dir / 'de.json').write_text('[]', encoding='utf-8')

        missing = find_missing_persona_translations(source, translations_dir, ('zh-CN', 'de'))

    assert missing == {'de': ['IDS_SETTINGS_PERSONA_TITLE']}


def test_translation_message_rejects_empty_content():
    """Blank translation messages are rejected."""
    assert 'empty translation message' in get_translation_message_errors('Persona', '   ')


def test_translation_message_preserves_placeholder_subtrees():
    """Placeholder tags must keep names, indexes, and examples."""
    source = 'Imported <ph name="COUNT">$1<ex>3</ex></ph> profiles.'
    assert not get_translation_message_errors(source,
                                              'Importiert: <ph name="COUNT">$1<ex>3</ex></ph>.')
    assert 'placeholder mismatch' in get_translation_message_errors(
        source, 'Importiert: <ph name="WRONG">$1<ex>3</ex></ph>.')
    assert 'placeholder mismatch' in get_translation_message_errors(
        source, 'Importiert: <ph name="COUNT">$2<ex>3</ex></ph>.')
    assert 'placeholder mismatch' in get_translation_message_errors(
        source, 'Importiert: <ph name="COUNT">$1<ex>4</ex></ph>.')
    assert 'placeholder mismatch' in get_translation_message_errors(source,
                                                                    'Importiert: drei Profile.')


def test_translation_message_allows_placeholder_reordering():
    """Translations may reorder placeholders without changing content."""
    source = ('<ph name="FIRST">$1<ex>A</ex></ph> and '
              '<ph name="SECOND">$2<ex>B</ex></ph>')
    translated = ('<ph name="SECOND">$2<ex>B</ex></ph> und '
                  '<ph name="FIRST">$1<ex>A</ex></ph>')
    assert not get_translation_message_errors(source, translated)


if __name__ == '__main__':
    test_find_missing_persona_translations()
    test_translation_message_rejects_empty_content()
    test_translation_message_preserves_placeholder_subtrees()
    test_translation_message_allows_placeholder_reordering()
