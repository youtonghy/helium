# Persona fingerprint coverage

This matrix covers the consistency repair. Paths in the consumer column are
relative to the Chromium source root. The patch queue is the durable source of
truth; local `build/src` is disposable.

The subsequent [preset privacy policy](persona-preset-privacy-policy.md) adds
versioned upgrades, explicit network intent, portable fonts, speech denial, and
fixed media preferences. Its regression evidence extends this matrix.

| Field or operation | State and actual consumers | Regression evidence |
| --- | --- | --- |
| Daily random seed | `chrome/browser/helium_persona/persona_service.cc`: candidate preparation, successful-activation session flag; read getters do not write prefs | `DailyRotationIsTransactionalAndStableAcrossMidnight`, `DailyRotationRetriesAfterRejectedActivation`, `FingerprintReadsNeverInitializeSeedState` |
| Fixed seed | Same service, explicit seed setter and activation candidate | `FixedSeedSurvivesActivationAndSessionRestart` |
| Profile/site generation and time bucket | `content/browser/helium_noise/noise_token_data.cc`: v2 seed includes both generations; site generation defaults to zero | `FirstSiteThenProfileRefreshChangesBothOrigins`, `ProfileScopeIgnoresSiteGeneration`, `SiteRefreshMigratesLegacyStringEpoch` |
| Site refresh scope | Service validates active Persona, rotation scope and HTTP(S) origin; indicator menu checks scope and result before reload | `SiteRefreshRejectsUnsupportedScopeAndInvalidOrigin`, existing indicator browser tests |
| Active identity save | Settings handler → `SavePersonaAndApply` → activation gate/ACK/CAS/restart | `ActiveSaveWaitsForNetworkAndExecutionContextRestart`, `ActiveSaveRollsBackRejectedCandidate`, `ActiveSaveRollsBackRestartDispatchFailure`, `ActiveSavePreservesConcurrentPrefChanges` |
| Name/display name/icon | Service permits metadata-only save; audit compares identity independently of snapshot name | `ActiveMetadataSaveSkipsRestart`, `MetadataSaveKeepsLiveIdentityAuditConsistent` |
| `screen.width`, `screen.height`, `colorDepth` | Shared `LocalFrame::GetHeliumPersonaSnapshot`; `core/frame/screen.cc` and `core/css/media_values.cc` | `PersonaScreenAndDprIgnoreHostDisplayChanges`, `ScreenMediaAndDprAgreeInMainAndCrossOriginFrames` |
| `screen.deviceScaleFactor` | `LocalFrame::DevicePixelRatio` replaces host scale while retaining zoom; LocalDOMWindow, Document, media values and FrameFetchContext consume that result | Same screen tests, including disabled Persona and host scale changes |
| DPR navigation Client Hints | `content/browser/client_hints/client_hints.cc` multiplies the Persona baseline by page zoom | `AddNavigationRequestUsesPersonaMemoryAndDpr`, including zoomed headers |
| Off-thread PaintWorklet DPR | `core/css/css_paint_value.cc` → `CSSPaintWorkletInput::DevicePixelRatio` → `PaintWorkletProxyClient`; painting retains `EffectiveZoom` | `RunPaintTestOnWorklet` checks exposed DPR separately from effective zoom |
| WebGL capability ranges/precision | `modules/webgl/webgl_rendering_context_base.cc` returns native caps without hardware-token perturbation | `WebGLPreservesNativeCapsAndKeepsPixelNoise` compares native caps before/after activation and pixel readback separately |
| `advanced.clientRectNoise` | Token propagation → shared helper in `core/canvas_interventions/noise_helper.cc` → Element and Range binding methods | `PersonaClientRectNoisePreservesUnionAndDegenerateRects`, `PersonaClientRectNoiseIsBoundedMonotoneAndMeasurementKeyed`, `ElementRangeAndFragmentUnionShareReadbackTransform` |
| `advanced.fontMetricNoise` | Token propagation → `core/html/canvas/text_metrics.cc`; raw shaping data stays unchanged, getters and extended readbacks share measurement-keyed scales | `FontMetricNoiseIsStableForSameMeasurementInput`, `FontMetricNoiseSeparatesMeasurementInput`, `FontMetricNoisePreservesRelatedExtendedMeasurements`, `FontMetricNoiseSeparatesFontSizeAndKeepsEmptyWidth` |
| Worker identity and font measurements | Existing worker snapshot/token propagation and restart path | `ActiveSaveRecreatesDocumentAndWorkerWithMatchingIdentity` checks locale and matching Window/Worker text measurements after save |
| `fontRendering.*`, WebGL capability profile records, `advanced.hardwareNoise` | Stored/imported for compatibility; no effective rendering capability; save rejects changes; contract/effective/import expose diagnostics | `LegacyUnsupportedFieldsRoundTripButCannotBeEdited`, `LegacyHardwareNoiseNeverIssuesAToken`, PersonaConfig legacy round-trip test |
| Device Pack-constrained UA/UA-CH | Requested record → verified identity template → effective snapshot; Settings displays differences | PersonaConfig saved/effective difference test and existing service effective-snapshot tests |

## Guard boundary

`devutils/check_patch_files.py` scans final added code across every patch in
series, including patches without `persona` or `random` in the filename. Its
fingerprint checks require tokens in specific consumer and test files, and
reject reintroduction of the removed read-time seed mutator and WebGL hardware
perturbation helpers. Comments and patch metadata do not satisfy those checks;
later removals by any patch name are accounted for.

The Python guard tests include a missing CSS consumer, a consumer placed in the
wrong file, comments/metadata in place of code, a later removal, and forbidden
WebGL perturbation. This remains a structural guard. A test name being present
does not prove the test passed or that the browser can compile.

## Validation boundary

The repository CI validation and final `agent_patch_guard --mode pre-build`
must pass before delivery. They check patch fresh-apply and source-backed
repository invariants without compiling Chromium. The C++ unit/browser tests
above are authored for the user's unified build and must be run after that
build; no C++ build or browser-test execution is performed during agent work.
TypeScript configuration logic can additionally be type-checked without emit
and exercised independently of a Chromium build.
