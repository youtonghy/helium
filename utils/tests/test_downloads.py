# -*- coding: UTF-8 -*-
"""Pinned individual resources must survive cache corruption and URL globbing."""

import hashlib

import pytest

from .. import downloads


def resource_info(tmp_path, extra=''):
    """Create a small pinned font manifest without requiring network access."""
    manifest = tmp_path / 'downloads.ini'
    digest = hashlib.sha512(b'font data').hexdigest()
    manifest.write_text(
        '[font]\nurl = https://example.test/Noto[wght].ttf\n'
        'download_filename = font.ttf\noutput_path = third_party/fonts\n'
        f'extractor = file\nsha512 = {digest}\n{extra}',
        encoding='utf-8')
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'font.ttf').write_bytes(b'font data')
    return downloads.DownloadInfo([manifest]), cache


def test_unpack_individual_file_preserves_bytes_and_destination(tmp_path):
    info, cache = resource_info(tmp_path)
    output = tmp_path / 'source'
    downloads.unpack_downloads(info, cache, ['font'], output)
    assert (output / 'third_party/fonts/font.ttf').read_bytes() == b'font data'
    assert (cache / 'font.ttf').read_bytes() == b'font data'


def test_corrupt_resource_never_overwrites_installed_file(tmp_path):
    info, cache = resource_info(tmp_path)
    output = tmp_path / 'source'
    destination = output / 'third_party/fonts/font.ttf'
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b'previous verified font')
    (cache / 'font.ttf').write_bytes(b'corrupt')
    with pytest.raises(downloads.HashMismatchError):
        downloads.unpack_downloads(info, cache, ['font'], output)
    assert destination.read_bytes() == b'previous verified font'


def test_component_selection_does_not_install_unselected_font(tmp_path):
    info, cache = resource_info(tmp_path)
    output = tmp_path / 'source'
    downloads.unpack_downloads(info, cache, ['another-component'], output)
    assert not output.exists()


def test_file_extractor_rejects_archive_strip_option(tmp_path):
    info, cache = resource_info(tmp_path, 'strip_leading_dirs = archive\n')
    with pytest.raises(ValueError, match='strip_leading_dirs'):
        downloads.unpack_downloads(info, cache, ['font'], tmp_path / 'source')


def test_curl_receives_literal_variable_font_url(tmp_path, monkeypatch):
    info, _ = resource_info(tmp_path)
    commands = []
    monkeypatch.setattr(downloads.shutil, 'which', lambda _: '/usr/bin/curl')

    def run(command, **_):
        commands.append(command)
        (tmp_path / 'download.ttf.partial').write_bytes(b'font data')

    monkeypatch.setattr(downloads.subprocess, 'run', run)
    downloads._download_if_needed(tmp_path / 'download.ttf', info['font'].url, False)
    assert '--globoff' in commands[0]
    assert commands[0][-1] == 'https://example.test/Noto[wght].ttf'
