# Fingerprint Control Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone Privacy and security Settings page that lets a Profile owner view and manage its fingerprint seed and automatic rotation policy.

**Architecture:** `PersonaService` remains the sole owner of the effective seed and existing generation state. A dedicated Settings route and WebUI page call the existing `PersonaHandler`; new Profile prefs store mode and lifecycle policy while `fingerprint_profile_salt` remains the renderer and network contract.

**Tech Stack:** Chromium C++ keyed services and preferences, Settings WebUI Polymer/TypeScript, GRIT localization, GoogleTest.

## Global Constraints

- Fixed seeds are exactly 64 hexadecimal characters and are normalized to lowercase.
- Fixed mode clears and disables automatic policy; automated rotation applies only to random mode.
- Daily rotation is lazy: evaluate it once on first Profile use after startup, never via a live-session timer.
- Seed changes must reuse `fingerprint_profile_salt` and increment the existing global generation.
- Do not send seeds to metrics, logs, Persona import, or Persona export.
- Modify only declared `build/src` files during hot development; export as a new top-level patch.

---

### Task 1: Model and verify fingerprint seed lifecycle

**Files:**
- Modify: `build/src/chrome/browser/helium_persona/persona_pref_names.h`
- Modify: `build/src/chrome/browser/helium_persona/persona_service.h`
- Modify: `build/src/chrome/browser/helium_persona/persona_service.cc`
- Modify: `build/src/chrome/browser/helium_persona/persona_service_unittest.cc`

**Interfaces:**
- Produces: `GetFingerprintSettings()`, `SetFixedFingerprintSeed()`, `GenerateRandomFingerprintSeed()`, `SetFingerprintAutomation()`, and `Shutdown()` on `PersonaService`.
- Consumes: the existing `fingerprint_profile_salt` and `fingerprint_rotation_epoch` Profile prefs.

- [ ] **Step 1: Write failing service tests for fixed and random seed changes**

```cpp
TEST_F(PersonaServiceTest, FixedSeedIsValidatedAndDisablesAutomation) {
  const base::DictValue rejected = service_->SetFixedFingerprintSeed("bad");
  EXPECT_FALSE(rejected.FindBool("ok").value_or(true));

  const base::DictValue accepted = service_->SetFixedFingerprintSeed(
      "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF");
  EXPECT_TRUE(accepted.FindBool("ok").value_or(false));
  EXPECT_EQ("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            prefs_.GetString(kPersonaFingerprintProfileSaltPref));
}
```

- [ ] **Step 2: Run the test to verify it fails because the new service API is absent**

Run: `python3 devutils/build_targets.py chrome/test:unit_tests`

Expected: the target fails at compile time with `SetFixedFingerprintSeed` not found.

- [ ] **Step 3: Add the dedicated preferences and minimal lifecycle API**

```cpp
base::DictValue PersonaService::SetFixedFingerprintSeed(
    const std::string& seed) {
  if (!IsValidFingerprintSeed(seed)) {
    return MakeFingerprintSettingsResponse(false, "seed", "invalid");
  }
  prefs_->SetString(kFingerprintSeedModePref, kFingerprintSeedModeFixed);
  prefs_->SetString(kFingerprintFixedSeedPref, base::ToLowerASCII(seed));
  prefs_->SetBoolean(kFingerprintClearOnExitPref, false);
  prefs_->SetBoolean(kFingerprintRotateDailyPref, false);
  ReplaceFingerprintSeed(base::ToLowerASCII(seed));
  return MakeFingerprintSettingsResponse(true);
}
```

- [ ] **Step 4: Add tests for daily lazy rotation and random-only exit cleanup**

```cpp
TEST_F(PersonaServiceTest, DailyRotationRunsOnceWhenTheStoredDayIsStale) {
  prefs_.SetBoolean(kFingerprintRotateDailyPref, true);
  prefs_.SetString(kFingerprintLastRotationDayPref, "1970-01-01");
  const std::string before = service_->GetFingerprintSettings()
                                 .FindString("seed").value_or("");
  const std::string after = service_->GetFingerprintSettings()
                                .FindString("seed").value_or("");
  EXPECT_FALSE(before.empty());
  EXPECT_EQ(before, after);
}
```

- [ ] **Step 5: Implement lazy daily evaluation, generation updates, and shutdown cleanup**

```cpp
void PersonaService::Shutdown() {
  if (IsRandomFingerprintMode() &&
      prefs_->GetBoolean(kFingerprintClearOnExitPref)) {
    prefs_->ClearPref(kPersonaFingerprintProfileSaltPref);
    prefs_->ClearPref(kPersonaFingerprintRotationEpochPref);
    prefs_->ClearPref(kFingerprintLastRotationDayPref);
  }
}
```

- [ ] **Step 6: Run the focused unit target and preserve the green result**

Run: `python3 devutils/build_targets.py chrome/test:unit_tests`

Expected: target completes successfully and the new lifecycle tests pass.

### Task 2: Expose seed management through the existing Settings handler

**Files:**
- Modify: `build/src/chrome/browser/ui/webui/settings/persona_handler.h`
- Modify: `build/src/chrome/browser/ui/webui/settings/persona_handler.cc`

**Interfaces:**
- Consumes: `PersonaService` fingerprint settings APIs from Task 1.
- Produces: `getFingerprintSettings`, `setFixedFingerprintSeed`, `generateRandomFingerprintSeed`, and `setFingerprintAutomation` WebUI messages.

- [ ] **Step 1: Add a failing handler-facing expectation to the service tests for structured invalid-seed results**

```cpp
const base::DictValue response = service_->SetFixedFingerprintSeed("not-a-seed");
EXPECT_FALSE(response.FindBool("ok").value_or(true));
EXPECT_EQ("invalid", response.FindString("error").value_or(""));
```

- [ ] **Step 2: Run the focused test and verify the response field is missing**

Run: `python3 devutils/build_targets.py chrome/test:unit_tests`

Expected: the focused assertion fails until the response shape is added.

- [ ] **Step 3: Register and implement handler messages with strict argument checks**

```cpp
web_ui()->RegisterMessageCallback(
    "setFingerprintAutomation",
    base::BindRepeating(&PersonaHandler::HandleSetFingerprintAutomation,
                        base::Unretained(this)));

void PersonaHandler::HandleSetFingerprintAutomation(
    const base::ListValue& args) {
  CHECK_EQ(3U, args.size());
  CHECK(args[1].is_bool());
  CHECK(args[2].is_bool());
  ResolveJavascriptCallback(
      args[0], GetPersonaService(profile_)->SetFingerprintAutomation(
                   args[1].GetBool(), args[2].GetBool()));
}
```

- [ ] **Step 4: Re-run the focused service target**

Run: `python3 devutils/build_targets.py chrome/test:unit_tests`

Expected: all Persona service tests pass; the handler compiles with the Settings UI target in Task 3.

### Task 3: Add the independent Settings page, navigation, and localization

**Files:**
- Create: `build/src/chrome/browser/resources/settings/privacy_page/fingerprint_browser_proxy.ts`
- Create: `build/src/chrome/browser/resources/settings/privacy_page/fingerprint_page.html`
- Create: `build/src/chrome/browser/resources/settings/privacy_page/fingerprint_page.ts`
- Modify: `build/src/chrome/browser/resources/settings/privacy_page/privacy_page.html`
- Modify: `build/src/chrome/browser/resources/settings/privacy_page/privacy_page.ts`
- Modify: `build/src/chrome/browser/resources/settings/privacy_page/privacy_page_index.html`
- Modify: `build/src/chrome/browser/resources/settings/route.ts`
- Modify: `build/src/chrome/browser/resources/settings/router.ts`
- Modify: `build/src/chrome/browser/resources/settings/lazy_load.ts`
- Modify: `build/src/chrome/browser/resources/settings/BUILD.gn`
- Modify: `build/src/chrome/app/settings_strings.grdp`
- Modify: `build/src/chrome/browser/ui/webui/settings/settings_localized_strings_provider.cc`

**Interfaces:**
- Consumes: Task 2 WebUI messages and responses shaped as `{ok, seed, mode, clearOnExit, rotateDaily, lastChanged, error?}`.
- Produces: `routes.FINGERPRINT` and `<settings-fingerprint-page>`.

- [ ] **Step 1: Add the proxy contract before the component implementation**

```ts
export interface FingerprintSettings {
  ok: boolean;
  seed: string;
  mode: 'random'|'fixed';
  clearOnExit: boolean;
  rotateDaily: boolean;
  lastChanged: string;
  error?: string;
}

getFingerprintSettings(): Promise<FingerprintSettings> {
  return sendWithPromise<FingerprintSettings>('getFingerprintSettings');
}
```

- [ ] **Step 2: Add the route and lazy view, then run the Settings TypeScript target to verify the missing page fails**

Run: `python3 devutils/build_targets.py chrome/browser/resources/settings:build_ts`

Expected: build fails until `fingerprint_page.ts` and its template are registered.

- [ ] **Step 3: Implement the small standalone page and disable automatic controls in fixed mode**

```html
<cr-toggle checked="[[settings_.clearOnExit]]"
    disabled="[[isFixedMode_(settings_.mode)]]"
    on-change="onAutomationChanged_">
</cr-toggle>
```

```ts
private async onFixedSeedApply_() {
  const result = await this.proxy_.setFixedFingerprintSeed(this.fixedSeed_);
  this.applySettings_(result);
}
```

- [ ] **Step 4: Add GRIT strings and their Settings localized-string mappings**

```xml
<message name="IDS_SETTINGS_FINGERPRINT_TITLE" desc="Title of the fingerprint settings page">
  Fingerprints
</message>
```

```cpp
{"fingerprintTitle", IDS_SETTINGS_FINGERPRINT_TITLE},
```

- [ ] **Step 5: Build the Settings WebUI target and inspect TypeScript and GRIT diagnostics**

Run: `python3 devutils/build_targets.py chrome/browser/resources/settings:build_ts chrome/browser/ui:ui`

Expected: both targets compile without TypeScript, GRIT, or C++ handler errors.

### Task 4: Export and validate the isolated patch

**Files:**
- Create: `patches/helium/core/fingerprint-control-settings.patch` via `agent_patch_guard --mode export-hotfix`
- Modify: `patches/series` via the guard only

- [ ] **Step 1: Re-run focused C++ and Settings targets after all changes**

Run: `python3 devutils/build_targets.py chrome/test:unit_tests chrome/browser/resources/settings:build_ts chrome/browser/ui:ui`

Expected: the relevant targets compile and unit tests pass.

- [ ] **Step 2: Export the declared hot-tree delta**

Run: `python3 devutils/agent_patch_guard.py --mode export-hotfix`

Expected: a new top patch is staged, replayed against a fresh patchwork tree, and published without modifying existing Persona patches.

- [ ] **Step 3: Run the mandatory repository handoff gate**

Run: `python3 devutils/agent_patch_guard.py --mode pre-build`

Expected: patch queue, fresh application, and repository validation pass. Report this separately from compile evidence.
