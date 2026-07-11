#!/usr/bin/env python3
# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Validate i18n translation files."""

import json
import sys
import xml.etree.ElementTree as xml
from collections import Counter
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parent.parent / 'i18n'
_REQUIRED_PERSONA_LANGUAGES = (
    'zh-CN',
    'zh-TW',
    'ja',
    'ko',
    'de',
    'fr',
    'es',
    'pt-BR',
    'ru',
)


def _parse_message(message):
    return xml.fromstring(f'<t>{message}</t>')


def _element_signature(element):
    return (element.tag, tuple(sorted(element.attrib.items())), element.text
            or '', tuple((_element_signature(child), child.tail or '') for child in element))


def _placeholder_signatures(root):
    return Counter(_element_signature(element) for element in root.iter('ph'))


def get_translation_message_errors(source_message, translated_message):
    """Return semantic XML errors for one translated message."""
    try:
        source_root = _parse_message(source_message)
    except xml.ParseError as exc:
        return [f'invalid source xml: {exc}']
    try:
        translated_root = _parse_message(translated_message)
    except xml.ParseError as exc:
        return [f'invalid xml: {exc}']

    errors = []
    if not ''.join(translated_root.itertext()).strip():
        errors.append('empty translation message')
    if _placeholder_signatures(source_root) != _placeholder_signatures(translated_root):
        errors.append('placeholder mismatch')
    return errors


def find_missing_persona_translations(source,
                                      translations_dir,
                                      required_languages=_REQUIRED_PERSONA_LANGUAGES):
    """Return required locales missing current Persona source strings."""
    persona_sources = {(entry['name'], entry['message'])
                       for entry in source if entry['name'].startswith('IDS_SETTINGS_PERSONA_')}
    missing_by_language = {}
    for language in required_languages:
        path = translations_dir / f'{language}.json'
        translations = []
        if path.exists():
            with open(path, encoding='utf-8') as file:
                translations = json.load(file)
        translated_sources = {(entry['name'], entry['source']) for entry in translations if entry}
        missing = sorted(name for name, message in persona_sources
                         if (name, message) not in translated_sources)
        if missing:
            missing_by_language[language] = missing
    return missing_by_language


def main():
    """Validate all translation files."""
    errors = 0

    with open(I18N_DIR / 'source.gen.json', encoding='utf-8') as file:
        source = json.load(file)
    source_keys = {(s['name'], s['message']) for s in source}

    for path in sorted((I18N_DIR / 'translations').glob('*.json')):
        with open(path, encoding='utf-8') as file:
            entries = json.load(file)

        for i, entry in enumerate(entries):
            if not entry:
                continue
            message_errors = get_translation_message_errors(entry['source'], entry['message'])
            for message_error in message_errors:
                print(f'{path.name}[{i}] ({entry["name"]}): {message_error}', file=sys.stderr)
            errors += len(message_errors)

            key = (entry['name'], entry['source'])
            if key not in source_keys:
                print(f'{path.name}[{i}] ({entry["name"]}): '
                      f'no matching source string',
                      file=sys.stderr)
                errors += 1

    missing_persona_translations = find_missing_persona_translations(source,
                                                                     I18N_DIR / 'translations')
    for language, names in missing_persona_translations.items():
        print(
            f'{language}.json: missing {len(names)} required Persona '
            f'translation(s): {", ".join(names)}',
            file=sys.stderr)
        errors += len(names)

    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
