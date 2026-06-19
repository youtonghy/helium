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

_PERSONA_RUNTIME_HOOK_GROUPS = {
    'navigator identity and UA-CH': (
        'ApplyPersonaUserAgentMetadata',
        'NavigatorUAData* NavigatorUA::userAgentData',
        'NavigatorLanguage::EnsureUpdatedLanguage',
    ),
    'region and request language': (
        'TimeZoneController::SetTimeZoneOverride',
        'LocaleController::instance().SetLocaleOverride',
        'WorkerFetchContext::AddAdditionalRequestHeaders',
        'GenerateAcceptLanguageHeader',
    ),
    'hardware and input devices': (
        'NavigatorBase::hardwareConcurrency',
        'NavigatorBase::deviceMemory',
        'NavigatorEvents::maxTouchPoints',
        'ApplyHeliumPersonaInputDeviceSettings',
    ),
    'screen, viewport, DPR, and CSS media': (
        'Screen::width() const',
        'LocalDOMWindow::outerWidth() const',
        'DOMVisualViewport::width() const',
        'MediaValues::CalculateDeviceWidth',
        'Document::DevicePixelRatio',
        'PaintWorkletGlobalScope::devicePixelRatio',
        'SetMediaFeatureOverride',
    ),
    'GPU and rendering surfaces': (
        'WebGLRenderingContextBase::getParameter',
        'GPUAdapter::CreateAdapterInfoForAdapter',
        'GPUAdapter::GPUAdapter',
        'GPUDevice::Initialize',
        'BaseRenderingContext2D::measureText',
        'BaseAudioContext::JitterAudioData',
    ),
    'fonts and media devices': (
        'FontAccessManager::DidRequestPermission',
        'CSSFontSelectorBase::FamilyNameFromSettings',
        'LocalFontFaceSource::IsLocalFontAvailable',
        'MediaDevices::getUserMedia',
        'AudioContext::baseLatency',
        'AudioContext::outputLatency',
    ),
    'network, storage, plugins, and speech': (
        'NetworkInformation::type() const',
        'NavigatorOnLine::onLine',
        'DOMPluginArray::DOMPluginArray',
        'NavigatorPlugins::pdfViewerEnabled',
        'StorageManager::persist',
        'SpeechSynthesis::getVoices',
    ),
    'residual high-risk browser services': (
        'HeliumPersonaAllowsAiApis',
        'HeliumPersonaAllowsWebNn',
        'HeliumPersonaAllowsPrivacySandboxApis',
        'HeliumPersonaAllowsPrivateStateTokens',
        'HeliumPersonaAllowsSpeechSynthesis',
        'HeliumPersonaAllowsHandwritingRecognition',
    ),
}

_PERSONA_CONTRACT_GROUPS = {
    'snapshot and schema source of truth': (
        'components/helium_persona/persona_snapshot.cc',
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
        'Runtime consumers should read this single normalized snapshot',
    ),
    'runtime propagation and refresh': (
        'persona_runtime_override.cc',
        'PersonaRuntimeOverride::ApplyGlobal',
        'PersonaRuntimeOverride::ClearGlobal',
        'persona_snapshot = browser_client->GetHeliumPersonaSnapshot',
        'SetHeliumPersonaSnapshot(creation_params->persona_snapshot)',
        'ApplyPersonaUserAgentMetadata',
    ),
}

_PERSONA_RANDOMIZATION_FIELD_GROUPS = {
    'randomize entrypoint and sequencing': (
        'onRandomizePersonaClick_',
        'makeRandomNoiseSeed_',
        'applyRandomRegion_',
        'applyRandomHardware_',
        'applyRandomGpu_',
        'applyRandomUaVersion_',
        'applyRandomScreen_',
        'applyRandomMediaDevices_',
        'applyRandomDisplayPreferences_',
        'applyRandomNetwork_',
        'applyRandomAdvancedSurface_',
        'applyConsistentRandomFonts_',
        'applyConsistentRandomDeviceLabel_',
    ),
    'UA, UA-CH, and navigator identity': (
        'applyConsistentRandomUaChIdentity_',
        'randomChromePlatformVersion_',
        'makeRandomChromeFullVersion_',
        'makeRandomUaChGreaseBrand_',
        'deriveUaChFullVersionList_',
        'fullVersionList',
        'navigatorVendor',
    ),
    'region and language': (
        'timezone',
        'locale',
        'acceptLanguage',
        'source.region',
    ),
    'hardware and touch': (
        'hardwareConcurrency',
        'deviceMemory',
        'maxTouchPoints',
        'touchEnabled',
    ),
    'GPU, WebGL, and WebGPU capabilities': (
        'makeGpuProfile_',
        'makeWebGlProfile_',
        'makeWebGl2Profile_',
        'makeWebGpuProfile_',
        'webglProfile',
        'webgl2Profile',
        'webgpuProfile',
        'webgpuFeatures',
    ),
    'screen and CSS media': (
        'makeScreenProfile_',
        'outerWidth',
        'windowScreenX',
        'deviceScaleFactor',
        'orientationType',
        'colorGamut',
        'dynamicRange',
        'monochromeDepth',
    ),
    'font pack and font rendering profiles': (
        'fontPackProfiles_',
        'fontRenderingProfiles_',
        'localeScopedFontPredicates_',
        'fontRendering',
        'persona.fontRendering = JSON.parse(JSON.stringify(rendering));',
    ),
    'media device profile': (
        'applyRandomMediaDevices_',
        'makePersonaDeviceToken_',
        'videoFrameRate',
        'audioBaseLatency',
        'audioOutputLatency',
        'voiceIsolation',
    ),
    'network information': (
        'applyRandomNetwork_',
        'effectiveType',
        'downlinkMax',
        'saveData',
        'online',
    ),
    'advanced exposed APIs': (
        'allowGeolocation',
        'allowMediaCapture',
        'allowLocalFonts',
        'allowWebSockets',
        'allowWebTransport',
        'allowAiApis',
        'allowWebNn',
        'allowPrivacySandboxApis',
        'allowPrivateStateTokens',
        'allowSpeechSynthesis',
        'allowHandwritingRecognition',
        'storageQuotaGb',
        'webdriverEnabled',
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
        'editablePersona_.gpu.webglProfile.maxCombinedTextureImageUnits',
        'editablePersona_.gpu.webgl2Profile.uniformBufferOffsetAlignment',
        'editablePersona_.gpu.webgpuProfile.maxComputeInvocationsPerWorkgroup',
    ),
    'manual hardware and touch fields': (
        'editablePersona_.hardware.hardwareConcurrency',
        'editablePersona_.hardware.deviceMemory',
        'editablePersona_.hardware.maxTouchPoints',
        'editablePersona_.hardware.touchEnabled',
    ),
    'manual display and media preference fields': (
        'editablePersona_.screen.width',
        'editablePersona_.screen.availLeft',
        'editablePersona_.screen.outerWidth',
        'editablePersona_.screen.windowScreenX',
        'editablePersona_.screen.deviceScaleFactor',
        'editablePersona_.screen.orientationType',
        'editablePersona_.screen.reducedMotion',
        'editablePersona_.screen.colorGamut',
        'editablePersona_.screen.dynamicRange',
        'editablePersona_.screen.monochromeDepth',
    ),
    'manual font and font rendering fields': (
        'editablePersona_.fonts.id',
        'fontFamiliesText_',
        'fontAliasesText_',
        'editablePersona_.fontRendering.profileVersion',
        'editablePersona_.fontRendering.engine',
        'editablePersona_.fontRendering.textGamma',
        'editablePersona_.fontRendering.useAutohinter',
    ),
    'manual media device fields': (
        'editablePersona_.mediaDevices.audioInputDeviceId',
        'editablePersona_.mediaDevices.videoWidth',
        'editablePersona_.mediaDevices.audioBaseLatency',
        'editablePersona_.mediaDevices.voiceIsolation',
    ),
    'manual network fields': (
        'editablePersona_.network.type',
        'editablePersona_.network.downlinkMax',
        'editablePersona_.network.saveData',
        'editablePersona_.network.online',
    ),
    'manual advanced core and noise fields': (
        'editablePersona_.advanced.clientHintsEnabled',
        'editablePersona_.advanced.reduceSystemInfo',
        'editablePersona_.advanced.canvasNoise',
        'editablePersona_.advanced.audioNoise',
        'editablePersona_.advanced.fontMetricNoise',
        'editablePersona_.advanced.cookieEnabled',
        'editablePersona_.advanced.pdfViewerEnabled',
        'editablePersona_.advanced.doNotTrackEnabled',
        'editablePersona_.advanced.webdriverEnabled',
        'editablePersona_.advanced.storageQuotaGb',
    ),
    'manual advanced media and speech fields': (
        'editablePersona_.advanced.virtualMediaDevices',
        'editablePersona_.advanced.allowDisplayCapture',
        'editablePersona_.advanced.allowMediaCapture',
        'editablePersona_.advanced.allowMediaSession',
        'editablePersona_.advanced.allowPictureInPicture',
        'editablePersona_.advanced.allowRemotePlayback',
        'editablePersona_.advanced.allowSpeechSynthesis',
        'editablePersona_.advanced.speechVoiceName',
        'editablePersona_.advanced.speechVoiceLang',
        'editablePersona_.advanced.speechVoiceUri',
        'editablePersona_.advanced.speechVoiceLocalService',
        'editablePersona_.advanced.speechVoiceDefault',
    ),
    'manual advanced device and sensor fields': (
        'editablePersona_.advanced.allowDeviceApis',
        'editablePersona_.advanced.allowGamepads',
        'editablePersona_.advanced.allowGeolocation',
        'editablePersona_.advanced.allowKeyboardLayout',
        'editablePersona_.advanced.allowLocalFonts',
        'editablePersona_.advanced.allowLocalNetworkApis',
        'editablePersona_.advanced.allowManagedDevice',
        'editablePersona_.advanced.allowMidi',
        'editablePersona_.advanced.allowPersistentDeviceId',
        'editablePersona_.advanced.allowPlatformCredentials',
        'editablePersona_.advanced.allowRealBatteryStatus',
        'editablePersona_.advanced.allowSensorApis',
        'editablePersona_.advanced.allowWebNfc',
        'editablePersona_.advanced.allowWebXr',
        'editablePersona_.advanced.allowWindowManagement',
    ),
    'manual advanced permission and storage fields': (
        'editablePersona_.advanced.allowBackgroundSync',
        'editablePersona_.advanced.allowClipboard',
        'editablePersona_.advanced.allowFileSystemAccess',
        'editablePersona_.advanced.allowFullscreen',
        'editablePersona_.advanced.allowIdleDetection',
        'editablePersona_.advanced.allowNotifications',
        'editablePersona_.advanced.allowPaymentHandler',
        'editablePersona_.advanced.allowPersistentStorage',
        'editablePersona_.advanced.allowProtectedMediaIdentifier',
        'editablePersona_.advanced.allowStorageAccess',
        'editablePersona_.advanced.allowWakeLock',
        'editablePersona_.advanced.allowWebAppInstallation',
        'editablePersona_.advanced.allowWebPrinting',
    ),
    'manual advanced browser service fields': (
        'editablePersona_.advanced.allowBadging',
        'editablePersona_.advanced.allowContacts',
        'editablePersona_.advanced.allowEyeDropper',
        'editablePersona_.advanced.allowInstalledApps',
        'editablePersona_.advanced.allowPresentationApis',
        'editablePersona_.advanced.allowPointerLock',
        'editablePersona_.advanced.allowShapeDetection',
        'editablePersona_.advanced.allowWebLocks',
        'editablePersona_.advanced.allowWebOtp',
        'editablePersona_.advanced.allowWebShare',
        'editablePersona_.advanced.allowWebSockets',
        'editablePersona_.advanced.allowWebTransport',
    ),
    'manual advanced residual experimental fields': (
        'editablePersona_.advanced.allowAiApis',
        'editablePersona_.advanced.allowHandwritingRecognition',
        'editablePersona_.advanced.allowPrivacySandboxApis',
        'editablePersona_.advanced.allowPrivateStateTokens',
        'editablePersona_.advanced.allowWebNn',
    ),
}


def _is_persona_randomization_patch(relative_path):
    """Return whether a persona patch participates in settings randomization."""
    patch_name = Path(str(relative_path)).name
    return 'random' in patch_name or patch_name in {
        'persona-consistent-randomize-ui.patch',
        'persona-settings-media-device-ui.patch',
        'persona-settings-font-rendering-profile-version-ui.patch',
        'persona-uach-grease-randomization.patch',
        'persona-custom-random-seed-ui.patch',
        'persona-noise-seed-regenerate-ui.patch',
    }


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
    """Return the concatenated text of persona patches referenced by series."""
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
        patch_text_parts.append(patch_path.read_text(encoding=ENCODING))
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


def check_persona_randomization_coverage(patches_dir, series_path=Path('series')):
    """
    Checks that the settings randomize flow still touches the full persona
    snapshot surface rather than only rotating a device label or UA version.

    Returns True if required randomization tokens are missing; False otherwise.
    """
    return _check_persona_token_groups(patches_dir,
                                       'randomization',
                                       _PERSONA_RANDOMIZATION_FIELD_GROUPS,
                                       series_path,
                                       include_patch=_is_persona_randomization_patch)


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
    warnings |= check_persona_runtime_hook_coverage(args.patches)
    warnings |= check_persona_randomization_coverage(args.patches)
    warnings |= check_persona_settings_manual_field_coverage(args.patches)

    if warnings:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
