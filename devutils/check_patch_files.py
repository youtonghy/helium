#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE.ungoogled_chromium file.
"""Run sanity checking algorithms over ungoogled-chromium's patch files

It checks the following:

    * All patches exist
    * All patches are referenced by the patch order

Exit codes:
    * 0 if no problems detected
    * 1 if warnings or errors occur
"""

import argparse
import sys
from pathlib import Path

from third_party import unidiff

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'utils'))
from _common import ENCODING, get_logger, parse_series # pylint: disable=wrong-import-order

sys.path.pop(0)

# File suffixes to ignore for checking unused patches
_PATCHES_IGNORE_SUFFIXES = {'.md'}

_PERSONA_PATCH_CODE_SUFFIXES = {
    '.cc',
    '.gn',
    '.gni',
    '.grd',
    '.grdp',
    '.h',
    '.html',
    '.js',
    '.mojom',
    '.py',
    '.ts',
}

_PERSONA_RUNTIME_HOOK_GROUPS = {
    'navigator identity and UA-CH': (
        'ApplyPersonaUserAgentMetadata',
        'GetPersonaAwareUserAgentValue',
        'GetPersonaUserAgentMetadata',
        'NavigatorLanguage::EnsureUpdatedLanguage',
        'persona_ua_metadata',
    ),
    'region and request language': (
        'WebTimeZoneOverride::SetOrChange',
        'NavigatorLanguage::EnsureUpdatedLanguage',
        'ReduceAcceptLanguageUtils::Create',
    ),
    'hardware and input devices': (
        'NavigatorBase::hardwareConcurrency',
        'NavigatorBase::deviceMemory',
        'NavigatorEvents::maxTouchPoints',
    ),
    'screen, viewport, DPR, and CSS media': (
        'Screen::width() const',
        'LocalDOMWindow::outerWidth() const',
    ),
    'network, storage, plugins, and speech': ('NetworkInformation::type() const', ),
    'privacy sandbox gates': ('HeliumPersonaAllowsPrivacySandboxApis', ),
    'noise token infra': (
        'HeliumNoiseTokenData::GetTokens',
        'HeliumNoiseFeature::kCanvas',
        'HeliumNoiseFeature::kAudio',
        'HeliumNoiseFeature::kHardware',
        'HeliumNoiseFeature::kFontMetric',
    ),
    'noise token propagation': (
        'GetHeliumNoiseToken',
        'GetHeliumWorkerNoiseToken',
        'AudioNoiseToken',
        'FontMetricNoiseToken',
        'SetAudioNoiseToken',
        'SetFontMetricNoiseToken',
        'helium_canvas_noise_token',
        'helium_audio_noise_token',
        'helium_font_metric_noise_token',
        'SetCanvasNoiseToken',
        'worker_start_data->helium_canvas_noise_token',
        'creation_params->helium_canvas_noise_token',
    ),
    'canvas readback noise': (
        'CanvasNoiseToken',
        'noise_helper.h',
        'NoisePixels',
        '!IsWebGL2()',
    ),
    'audio render noise': (
        'ApplyHeliumAudioNoise',
        'AudioNoiseToken',
        'std::nextafter',
    ),
    'font metric noise': (
        'ApplyFontMetricNoise',
        'FontMetricNoiseToken',
        'kHeliumFontMetricNoiseDelta',
    ),
}

_PERSONA_CONTRACT_GROUPS = {
    'snapshot and schema source of truth': (
        'components/helium_persona/persona_snapshot.h',
        'third_party/blink/public/common/helium_persona/persona_snapshot.h',
        'third_party/blink/public/mojom/helium_persona/persona_snapshot.mojom',
        'PersonaHasRequiredFields',
        'ValidatePersona',
        'SavePersona',
    ),
    'save and clone lifecycle': (
        'GetPersonaState',
        'ClonePresetIntoProfile',
        'SetActivePersona',
        'DeletePersona',
    ),
    'runtime propagation and refresh': (
        'persona_runtime_override.cc',
        'persona_snapshot = browser_client->GetHeliumPersonaSnapshot',
        'ApplyPersonaUserAgentMetadata',
    ),
}

_PERSONA_PROFILE_MANAGEMENT_GROUPS = {
    'profile metadata and lifecycle': (
        'GetPersonaProfiles',
        'CreatePersonaProfile',
        'GetLastUsedPersonaId',
        'SetLastUsedPersonaId',
        'GetLaunchSelectionMode',
        'SetLaunchSelectionMode',
        'displayName',
        'icon',
        'createdAt',
        'modifiedAt',
        'lastUsedAt',
        'helium.persona.last_used_id',
        'helium.persona.launch_selection_mode',
    ),
    'settings profile manager ui': (
        'getPersonaProfiles',
        'createPersonaProfile',
        'getLaunchSelectionMode',
        'setLaunchSelectionMode',
        'profiles_',
        'launchSelectionMode_',
        'onProfileCardClick_',
        'onCreateProfileClick_',
    ),
    'startup persona picker flow': (
        'MaybeLaunchPersonaPickerOnStartup',
        'ResumePendingLaunchWithPersona',
        'ApplyLastUsedPersonaOnStartup',
        'ShowPersonaPickerForStartup',
        'kChromeUIPersonaPickerHost',
        'chrome://persona-picker',
        'continueStartupWithPersona',
        'persona_picker:resources',
    ),
    'session indicator toolbar ui': (
        'PersonaIndicatorButton',
        'PersonaIndicatorMenuModel',
        'VIEW_ID_PERSONA_INDICATOR',
        'SetActivePersonaAndReload',
        'Manage personas',
    ),
}

_PERSONA_SETTINGS_MANUAL_FIELD_GROUPS = {
    'manual identity fields': (
        'editablePersona_.userAgent',
        'editablePersona_.platform',
        'editablePersona_.navigatorVendor',
        'editablePersona_.navigatorProductSub',
        'editablePersona_.uaCh.platform',
        'editablePersona_.uaCh.fullVersion',
        'uaChBrandsText_',
        'uaChFullVersionListText_',
        'uaChFormFactorsText_',
    ),
    'manual region and language fields': (
        'editablePersona_.region.timezone',
        'editablePersona_.region.locale',
        'editablePersona_.region.acceptLanguage',
        'navigatorLanguagesText_',
    ),
    'manual GPU and capability fields': (
        'editablePersona_.gpu.vendor',
        'editablePersona_.gpu.renderer',
        'editablePersona_.gpu.webgpuAdapter',
        'webgpuFeaturesText_',
    ),
    'manual hardware and touch fields': (
        'editablePersona_.hardware.hardwareConcurrency',
        'editablePersona_.hardware.deviceMemory',
        'editablePersona_.hardware.maxTouchPoints',
    ),
    'manual display and media preference fields': (
        'editablePersona_.screen.width',
        'editablePersona_.screen.availLeft',
        'editablePersona_.screen.outerWidth',
        'editablePersona_.screen.deviceScaleFactor',
    ),
    'manual font and font rendering fields': (
        'editablePersona_.fonts.id',
        'fontFamiliesText_',
        'fontAliasesText_',
        'editablePersona_.fontRendering.engine',
    ),
    'manual media device fields': ('editablePersona_.mediaDevices.audioBaseLatency', ),
    'manual network fields': (
        'editablePersona_.network.type',
        'editablePersona_.network.downlinkMax',
    ),
}

_PERSONA_RANDOMIZATION_FIELD_GROUPS = {}


def _is_persona_randomization_patch(relative_path):
    """Return whether a persona patch participates in settings randomization."""
    patch_name = Path(str(relative_path)).name
    return 'random' in patch_name


def _read_series_file(patches_dir, series_file, join_dir=False):
    """
    Returns a generator over the entries in the series file

    patches_dir is a pathlib.Path to the directory of patches
    series_file is a pathlib.Path relative to patches_dir

    join_dir indicates if the patches_dir should be joined with the series entries
    """
    for entry in parse_series(patches_dir / series_file):
        if join_dir:
            yield patches_dir / entry
        else:
            yield entry


def check_patch_readability(patches_dir, series_path=Path('series')):
    """
    Check if the patches from iterable patch_path_iter are readable.
        Patches that are not are logged to stdout.

    Returns True if warnings occured, False otherwise.
    """
    warnings = False
    for patch_path in _read_series_file(patches_dir, series_path, join_dir=True):
        if patch_path.exists():
            with patch_path.open(encoding=ENCODING) as file_obj:
                try:
                    unidiff.PatchSet(file_obj.read())
                except unidiff.errors.UnidiffParseError:
                    get_logger().exception('Could not parse patch: %s', patch_path)
                    warnings = True
                    continue
        else:
            get_logger().warning('Patch not found: %s', patch_path)
            warnings = True
    return warnings


def check_unused_patches(patches_dir, series_path=Path('series')):
    """
    Checks if there are unused patches in patch_dir from series file series_path.
        Unused patches are logged to stdout.

    patches_dir is a pathlib.Path to the directory of patches
    series_path is a pathlib.Path to the series file relative to the patches_dir

    Returns True if there are unused patches; False otherwise.
    """
    unused_patches = set()
    for path in patches_dir.rglob('*'):
        if path.is_dir():
            continue
        if path.suffix in _PATCHES_IGNORE_SUFFIXES:
            continue
        unused_patches.add(str(path.relative_to(patches_dir)))
    unused_patches -= set(_read_series_file(patches_dir, series_path))
    unused_patches.remove(str(series_path))
    logger = get_logger()
    for entry in sorted(unused_patches):
        logger.warning('Unused patch: %s', entry)
    return bool(unused_patches)


def check_series_duplicates(patches_dir, series_path=Path('series')):
    """
    Checks if there are duplicate entries in the series file

    series_path is a pathlib.Path to the series file relative to the patches_dir

    returns True if there are duplicate entries; False otherwise.
    """
    entries_seen = set()
    for entry in _read_series_file(patches_dir, series_path):
        if entry in entries_seen:
            get_logger().warning('Patch appears more than once in series: %s', entry)
            return True
        entries_seen.add(entry)
    return False


def _collect_persona_patch_text(patches_dir, series_path=Path('series'), include_patch=None):
    """Return added code text from persona patches referenced by series."""
    patch_text_parts = []
    for patch_path in _read_series_file(patches_dir, series_path, join_dir=True):
        try:
            relative_path = patch_path.relative_to(patches_dir)
        except ValueError:
            relative_path = patch_path
        if not str(relative_path).startswith('helium/core/persona-'):
            continue
        if include_patch and not include_patch(relative_path):
            continue
        if not patch_path.exists():
            continue
        patch_set = unidiff.PatchSet(patch_path.read_text(encoding=ENCODING))
        for patched_file in patch_set:
            target_path = Path(patched_file.target_file)
            if target_path.suffix not in _PERSONA_PATCH_CODE_SUFFIXES:
                continue
            for hunk in patched_file:
                for line in hunk:
                    if not (line.is_added or line.is_context):
                        continue
                    value = line.value.strip()
                    if not value or value.startswith(('//', '/*', '*')):
                        continue
                    patch_text_parts.append(value)
    return '\n'.join(patch_text_parts)


def _check_persona_token_groups(patches_dir,
                                group_label,
                                groups,
                                series_path=Path('series'),
                                include_patch=None):
    """Check that persona patches contain each token group."""
    patch_text = _collect_persona_patch_text(patches_dir, series_path, include_patch)
    if not patch_text:
        return False

    warnings = False
    for group_name, required_tokens in groups.items():
        missing_tokens = [token for token in required_tokens if token not in patch_text]
        if missing_tokens:
            get_logger().warning('Persona %s group missing %s token(s): %s', group_label,
                                 group_name, ', '.join(missing_tokens))
            warnings = True
    return warnings


def check_persona_runtime_hook_coverage(patches_dir, series_path=Path('series')):
    """
    Checks that Helium persona runtime patches still contain the expected
    high-entropy exposed-surface hooks.

    This is a patch-queue guard, not a Chromium compile/runtime test. It catches
    accidental removal or omission of broad hook groups while keeping the normal
    patch validation flow source-free.

    Returns True if required hook tokens are missing; False otherwise.
    """
    return _check_persona_token_groups(patches_dir, 'runtime hook', _PERSONA_RUNTIME_HOOK_GROUPS,
                                       series_path)


def check_persona_contract_coverage(patches_dir, series_path=Path('series')):
    """Check that persona snapshot/schema/propagation still share one contract."""
    return _check_persona_token_groups(patches_dir, 'contract', _PERSONA_CONTRACT_GROUPS,
                                       series_path)


def check_persona_profile_management_coverage(patches_dir, series_path=Path('series')):
    """Check that persona profile metadata and launch-selection prefs are covered."""
    return _check_persona_token_groups(patches_dir, 'profile management',
                                       _PERSONA_PROFILE_MANAGEMENT_GROUPS, series_path)


def check_persona_randomization_coverage(patches_dir, series_path=Path('series')):
    """
    Checks settings randomization coverage when a randomization patch exists.

    Returns True if required randomization tokens are missing; False otherwise.
    """
    randomization_patches = [
        entry for entry in _read_series_file(patches_dir, series_path)
        if str(entry).startswith('helium/core/persona-') and _is_persona_randomization_patch(entry)
    ]
    if not randomization_patches:
        return False

    if not _PERSONA_RANDOMIZATION_FIELD_GROUPS:
        get_logger().warning(
            'Persona randomization patch(es) present without configured coverage token groups: %s',
            ', '.join(randomization_patches))
        return True

    return _check_persona_token_groups(patches_dir, 'randomization',
                                       _PERSONA_RANDOMIZATION_FIELD_GROUPS, series_path,
                                       _is_persona_randomization_patch)


def check_persona_settings_manual_field_coverage(patches_dir, series_path=Path('series')):
    """
    Checks that settings still exposes manual controls for high-entropy persona
    field groups.

    Returns True if required settings tokens are missing; False otherwise.
    """
    return _check_persona_token_groups(patches_dir, 'settings manual fields',
                                       _PERSONA_SETTINGS_MANUAL_FIELD_GROUPS, series_path)


def main():
    """CLI entrypoint"""

    root_dir = Path(__file__).resolve().parent.parent
    default_patches_dir = root_dir / 'patches'

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p',
                        '--patches',
                        type=Path,
                        default=default_patches_dir,
                        help='Path to the patches directory to use. Default: %(default)s')
    args = parser.parse_args()

    warnings = False
    warnings |= check_patch_readability(args.patches)
    warnings |= check_series_duplicates(args.patches)
    warnings |= check_unused_patches(args.patches)
    warnings |= check_persona_contract_coverage(args.patches)
    warnings |= check_persona_profile_management_coverage(args.patches)
    warnings |= check_persona_runtime_hook_coverage(args.patches)
    warnings |= check_persona_randomization_coverage(args.patches)
    warnings |= check_persona_settings_manual_field_coverage(args.patches)

    if warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
