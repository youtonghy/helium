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
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from third_party import unidiff

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'utils'))
from _common import ENCODING, get_logger, parse_series # pylint: disable=wrong-import-order

sys.path.pop(0)

# File suffixes to ignore for checking unused patches
_PATCHES_IGNORE_SUFFIXES = {'.md', '.patch~'}

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
        'snapshot->navigator_languages',
        'const blink::HeliumPersonaSnapshot* persona_snapshot',
    ),
    'region and request language': (
        'WebTimeZoneOverride::SetOrChange',
        'snapshot->navigator_languages',
        '->GetHeliumPersonaSnapshot(browser_context)',
    ),
    'hardware and input devices': (
        'snapshot->hardware_concurrency',
        'snapshot->device_memory',
        'snapshot.max_touch_points',
    ),
    'screen, viewport, DPR, and CSS media': (
        'snapshot->screen_width',
        'snapshot->outer_width',
        'snapshot->device_scale_factor',
    ),
    'network, storage, plugins, and speech': (
        'ParsePersonaConnectionType(snapshot->network_type)',
        'snapshot->network_downlink_max',
    ),
    'privacy sandbox gates': ('HeliumPersonaAllowsPrivacySandboxApis', ),
    'permission type gates': (
        'HeliumPersonaAllowsPermissionType',
        'PermissionDescriptorToPermissionType',
        'PermissionStatus::DENIED',
        'allow_geolocation',
        'allow_clipboard',
        'allow_notifications',
        'allow_midi',
        'allow_idle_detection',
        'allow_window_management',
        'allow_sensor_apis',
        'allow_web_nfc',
        'allow_payment_handler',
    ),
    'noise token infra': (
        'HeliumNoiseTokenData::GetTokens',
        'HeliumNoiseTokenData::GetFeatureToken',
        'HeliumNoiseFeature::kCanvas',
        'HeliumNoiseFeature::kAudio',
        'HeliumNoiseFeature::kHardware',
        'HeliumNoiseFeature::kFontMetric',
    ),
    'noise token propagation': (
        'GetHeliumNoiseToken',
        'GetHeliumWorkerNoiseToken',
        'AudioNoiseToken',
        'HardwareNoiseToken',
        'FontMetricNoiseToken',
        'SetAudioNoiseToken',
        'SetHardwareNoiseToken',
        'SetFontMetricNoiseToken',
        'helium_canvas_noise_token',
        'helium_audio_noise_token',
        'helium_hardware_noise_token',
        'helium_font_metric_noise_token',
        'SetCanvasNoiseToken',
        'worker_start_data->helium_canvas_noise_token',
        'creation_params->helium_canvas_noise_token',
    ),
    'canvas readback noise': (
        'CanvasNoiseToken',
        'noise_helper.h',
        'NoisePixels',
        # WebGL1 and WebGL2 ArrayBufferView readPixels (not PIXEL_PACK GPU path).
        'format == GL_RGBA && type == GL_UNSIGNED_BYTE && width > 0',
    ),
    'hardware webgl noise': (
        'HardwareNoiseToken',
        'GetHardwareNoiseHash',
        'ApplyHardwareFloatNoise',
        'ApplyHardwareIntNoise(precision',
        'GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT',
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
        'persona_runtime_override.h',
        'PersonaRuntimeOverride::GetGlobal',
        'PersonaRuntimeOverride::ApplyGlobal',
        'PersonaRuntimeOverride::ClearGlobal',
        'persona_snapshot = browser_client->GetHeliumPersonaSnapshot',
        'ApplyPersonaUserAgentMetadata',
    ),
}

_PERSONA_BUILD_INTEGRITY_FILE_GROUPS = {
    'component ownership and linkage': (
        ('components/helium_persona/BUILD.gn', 'source_set("helium_persona")'),
        ('chrome/browser/BUILD.gn', '"//components/helium_persona"'),
    ),
    'generated contract closures': (
        ('third_party/blink/public/common/helium_persona/persona_snapshot.h',
         '#endif  // THIRD_PARTY_BLINK_PUBLIC_COMMON_HELIUM_PERSONA_PERSONA_SNAPSHOT_H_'),
        ('third_party/blink/public/common/helium_persona/persona_snapshot_mojom_traits.h',
         '}  // namespace mojo'),
        ('third_party/blink/public/common/helium_persona/persona_snapshot_mojom_traits.h',
         '#endif  // THIRD_PARTY_BLINK_PUBLIC_COMMON_HELIUM_PERSONA_'
         'PERSONA_SNAPSHOT_MOJOM_TRAITS_H_'),
        ('third_party/blink/public/mojom/helium_persona/persona_snapshot.mojom',
         'array<HeliumPersonaFingerprintRotationEpoch> '
         'fingerprint_rotation_site_epochs;\n};'),
    ),
    'renderer declarations': (
        ('third_party/blink/renderer/core/execution_context/navigator_base.h',
         'float deviceMemory() const;'),
        ('third_party/blink/renderer/core/workers/worker_global_scope.h',
         'const HeliumPersonaSnapshot helium_persona_snapshot_;'),
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
        'editablePersona_.uaCh.platformVersion',
        'editablePersona_.uaCh.architecture',
        'editablePersona_.uaCh.model',
        'editablePersona_.uaCh.bitness',
        'editablePersona_.uaCh.fullVersion',
        'editablePersona_.uaCh.mobile',
        'editablePersona_.uaCh.wow64',
        'uaChBrandsText_',
        'uaChFormFactorsText_',
    ),
    'manual region and language fields': (
        'editablePersona_.region.timezone',
        'editablePersona_.region.locale',
        'editablePersona_.region.acceptLanguage',
    ),
    'manual GPU and capability fields': (
        'editablePersona_.gpu.vendor',
        'editablePersona_.gpu.renderer',
        'editablePersona_.gpu.webgpuAdapter',
    ),
    'manual hardware and touch fields': (
        'editablePersona_.hardware.hardwareConcurrency',
        'editablePersona_.hardware.deviceMemory',
        'editablePersona_.hardware.maxTouchPoints',
    ),
    'manual display and media preference fields': (
        'editablePersona_.screen.width',
        'editablePersona_.screen.height',
        'editablePersona_.screen.availLeft',
        'editablePersona_.screen.availTop',
        'editablePersona_.screen.availWidth',
        'editablePersona_.screen.availHeight',
        'editablePersona_.screen.outerWidth',
        'editablePersona_.screen.outerHeight',
        'editablePersona_.screen.deviceScaleFactor',
    ),
    'manual font and font rendering fields': (
        'editablePersona_.fonts.id',
        'fontFamiliesText_',
        'fontAliasesText_',
        'editablePersona_.fontRendering.engine',
    ),
    'manual noise toggles': (
        'editablePersona_.advanced.canvasNoise',
        'editablePersona_.advanced.audioNoise',
        'editablePersona_.advanced.hardwareNoise',
        'editablePersona_.advanced.fontMetricNoise',
    ),
    'manual media device fields': (
        'editablePersona_.mediaDevices.audioBaseLatency',
        'editablePersona_.mediaDevices.audioOutputLatency',
    ),
    'manual network fields': (
        'editablePersona_.network.type',
        'editablePersona_.network.downlinkMax',
    ),
    'manual client hints and permission gates': (
        'editablePersona_.advanced.clientHintsEnabled',
        'editablePersona_.advanced.allowBackgroundSync',
        'editablePersona_.advanced.allowContacts',
        'editablePersona_.advanced.allowLocalFonts',
        'editablePersona_.advanced.allowPrivacySandboxApis',
        'editablePersona_.advanced.allowGamepads',
        'editablePersona_.advanced.allowClipboard',
        'editablePersona_.advanced.allowGeolocation',
        'editablePersona_.advanced.allowNotifications',
        'editablePersona_.advanced.allowMidi',
        'editablePersona_.advanced.allowIdleDetection',
        'editablePersona_.advanced.allowWindowManagement',
        'editablePersona_.advanced.allowWebNfc',
        'editablePersona_.advanced.allowWebXr',
        'editablePersona_.advanced.allowSensorApis',
        'editablePersona_.advanced.allowRealBatteryStatus',
        'editablePersona_.advanced.allowPlatformCredentials',
        'editablePersona_.advanced.allowPaymentHandler',
        'editablePersona_.advanced.allowSpeechSynthesis',
        'editablePersona_.advanced.allowWebPrinting',
        'editablePersona_.advanced.allowShapeDetection',
        'editablePersona_.advanced.allowWebOtp',
        'editablePersona_.advanced.allowAiApis',
        'editablePersona_.advanced.allowHandwritingRecognition',
        'editablePersona_.advanced.allowWebNn',
        'editablePersona_.advanced.allowPrivateStateTokens',
    ),
    'manual fingerprint rotation': (
        'editablePersona_.advanced.fingerprintRotation.scope',
        'editablePersona_.advanced.fingerprintRotation.rotationIntervalDays',
    ),
    'typed settings serialization': (
        'preparePersonaForSave',
        'parsePersonaImportPayload',
        'PERSONA_EXPORT_SCHEMA',
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


def check_tracked_patch_backups(patches_dir):
    """Reject editor backup patches if they have entered the Git index."""
    repo_root = patches_dir.parent
    try:
        relative_patches_dir = patches_dir.relative_to(repo_root)
        result = subprocess.run(
            ['git', '-C', str(repo_root), 'ls-files', '--',
             str(relative_patches_dir)],
            check=False,
            capture_output=True,
            encoding=ENCODING)
    except (OSError, ValueError):
        return False
    if result.returncode:
        return False
    backups = sorted(path for path in result.stdout.splitlines() if Path(path).suffix == '.patch~')
    for path in backups:
        get_logger().warning('Tracked patch editor backup: %s', path)
    return bool(backups)


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


def _normalize_patched_path(path):
    """Return a repository-relative path from a unified diff path."""
    if not path or path == '/dev/null':
        return None
    if path.startswith(('a/', 'b/')):
        return path[2:]
    return path


def _should_include_persona_patch(relative_path, include_patch=None):
    """Return True when a series entry should be scanned for persona tokens."""
    if include_patch:
        return include_patch(relative_path)
    return str(relative_path).startswith('helium/core/persona-')


def _apply_persona_patch_line(lines_by_path, line, source_path, target_path):
    """Apply one added/removed code line to the final persona patch snapshot."""
    if not (line.is_added or line.is_removed):
        return
    value = line.value.strip()
    if not value or value.startswith(('//', '/*', '*')):
        return
    line_path = target_path if line.is_added else source_path
    if not line_path:
        return
    final_lines = lines_by_path.setdefault(line_path, [])
    if line.is_added:
        final_lines.append(value)
        return
    try:
        final_lines.remove(value)
    except ValueError:
        pass


def _apply_persona_patched_file(lines_by_path, patched_file):
    """Merge one unified-diff file into the final persona patch snapshot."""
    source_path = _normalize_patched_path(patched_file.source_file)
    target_path = _normalize_patched_path(patched_file.target_file)
    effective_path = target_path or source_path
    if not effective_path or Path(effective_path).suffix not in _PERSONA_PATCH_CODE_SUFFIXES:
        return
    for hunk in patched_file:
        for line in hunk:
            _apply_persona_patch_line(lines_by_path, line, source_path, target_path)


def _collect_persona_patch_lines(patches_dir, series_path=Path('series'), include_patch=None):
    """Return final added code lines by target path after the patch queue."""
    lines_by_path = {}
    for patch_path in _read_series_file(patches_dir, series_path, join_dir=True):
        try:
            relative_path = patch_path.relative_to(patches_dir)
        except ValueError:
            relative_path = patch_path
        if not _should_include_persona_patch(relative_path, include_patch):
            continue
        if not patch_path.exists():
            continue
        patch_set = unidiff.PatchSet(patch_path.read_text(encoding=ENCODING))
        for patched_file in patch_set:
            _apply_persona_patched_file(lines_by_path, patched_file)
    return lines_by_path


def _collect_persona_patch_text(patches_dir, series_path=Path('series'), include_patch=None):
    """Return final added code text from persona patches referenced by series."""
    lines_by_path = _collect_persona_patch_lines(patches_dir, series_path, include_patch)
    return '\n'.join(line for lines in lines_by_path.values() for line in lines)


def _check_persona_token_groups(patches_dir,
                                group_label,
                                groups,
                                series_path=Path('series'),
                                include_patch=None):
    """Check that persona patches contain each token group."""
    patch_text = _collect_persona_patch_text(patches_dir, series_path, include_patch)
    if not patch_text:
        get_logger().warning('Persona %s guard found no final patch additions', group_label)
        return True

    warnings = False
    for group_name, required_tokens in groups.items():
        missing_tokens = [token for token in required_tokens if token not in patch_text]
        if missing_tokens:
            get_logger().warning('Persona %s group missing %s token(s): %s', group_label,
                                 group_name, ', '.join(missing_tokens))
            warnings = True
    return warnings


def _check_persona_file_token_groups(patches_dir, group_label, groups, series_path=Path('series')):
    """Check tokens against final additions in their owning files."""
    lines_by_path = _collect_persona_patch_lines(patches_dir, series_path)
    if not lines_by_path:
        get_logger().warning('Persona %s guard found no final patch additions', group_label)
        return True

    warnings = False
    for group_name, requirements in groups.items():
        missing = []
        for path, token in requirements:
            if token not in '\n'.join(lines_by_path.get(path, [])):
                missing.append(f'{path}: {token}')
        if missing:
            get_logger().warning('Persona %s group missing %s requirement(s): %s', group_label,
                                 group_name, ', '.join(missing))
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


def check_persona_build_integrity(patches_dir, series_path=Path('series')):
    """Check declarations, generated closures, and component linkage."""
    return _check_persona_file_token_groups(patches_dir, 'build integrity',
                                            _PERSONA_BUILD_INTEGRITY_FILE_GROUPS, series_path)


def check_persona_settings_i18n_key_coverage(patches_dir, series_path=Path('series')):
    """Check that every Persona settings key has one provider mapping."""
    ui_lines = _collect_persona_patch_lines(patches_dir, series_path)
    ui_text = '\n'.join(line for path, lines in ui_lines.items()
                        if path.startswith('chrome/browser/resources/settings/') for line in lines)
    ui_keys = set(re.findall(r'\$i18n\{(persona[A-Za-z0-9]+)\}', ui_text))
    ui_keys.update(re.findall(r"\bi18n\(\s*['\"](persona[A-Za-z0-9]+)['\"]", ui_text))
    ui_keys.update(
        re.findall(r"(?:labelKey|tooltipKey)\s*:\s*['\"](persona[A-Za-z0-9]+)['\"]", ui_text))

    provider_lines = _collect_persona_patch_lines(
        patches_dir, series_path, lambda path: str(path) == 'helium/core/services-prefs.patch' or
        str(path).startswith('helium/core/persona-'))
    provider_text = '\n'.join(
        provider_lines.get(
            'chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc', []))
    provider_keys = re.findall(
        r'\{\s*"(persona[A-Za-z0-9]+)"\s*,\s*IDS_SETTINGS_PERSONA_[A-Z0-9_]+\s*\}', provider_text)
    missing = sorted(ui_keys - set(provider_keys))
    duplicates = sorted(key for key, count in Counter(provider_keys).items() if count > 1)
    if missing:
        get_logger().warning('Persona settings i18n keys missing provider mappings: %s',
                             ', '.join(missing))
    if duplicates:
        get_logger().warning('Persona settings i18n provider keys are duplicated: %s',
                             ', '.join(duplicates))
    return bool(missing or duplicates)


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
    warnings |= check_tracked_patch_backups(args.patches)
    warnings |= check_persona_contract_coverage(args.patches)
    warnings |= check_persona_build_integrity(args.patches)
    warnings |= check_persona_profile_management_coverage(args.patches)
    warnings |= check_persona_runtime_hook_coverage(args.patches)
    warnings |= check_persona_randomization_coverage(args.patches)
    warnings |= check_persona_settings_manual_field_coverage(args.patches)
    warnings |= check_persona_settings_i18n_key_coverage(args.patches)

    if warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
