<!-- Recovered from planner subagent 2eb05274-c07c-40e transcript (workflow toolResult). -->
<!-- Source: pi-subagents tasks/2eb05274-c07c-40e.output message #5 -->

> **Status (2026-07-21):** Phases 1–3 implemented and durable in `patches/`.
> Series tops: `persona-webotp-binder-stability`, `persona-interface-binder-fail-closed`,
> `restore-variations-client-data-header-symbol`, `persona-interface-binder-fail-closed-tests`,
> `persona-handwriting-empty-promise-consistency`.
> gtest: WebOTP BindDenied×2 + PersonaInterfaceBinderFailClosed×3 = **5/5 PASS**.
> `build/src` re-synced via pop → merge → push (full series applied).

# Persona Disabled-API Binder Stability — Implementation Plan

**Mode:** `patch-fix` for the 2026-07-22 AIManager follow-up; remaining sections retain the original plan/audit scope  
**SoT:** ground-truth diagnosis + live tree patterns + audit corrections  
**Vendor paths:** keep `patches/helium/**` naming

> **AIManager follow-up (2026-07-22):** request-time persona checks, canonical
> fail-closed resolution, all-method unit coverage, and cached-remote Window/Worker
> regressions are durable in the owner patches. Four targeted
> implementation/test translation units pass `syntax_check`; all 205 patches
> fresh-apply. Runtime tests and object builds remain unexecuted because the
> source archive lacks required Chromium test data and Rust toolchain inputs.

> **Revocation boundary:** this slice authorizes each new `AIManager` request
> against the current persona. It does not cancel requests that were already in
> flight or terminate sessions created before a persona switch; immediate
> capability revocation requires separate lifecycle/teardown work.

---

## Goal

Make intentional persona API denial **fail closed without process death or DCHECK abort**:

1. Intentional disable must **never** cause `ReportBadMessage` / renderer kill.
2. Every renderer-visible async operation must **deterministically settle** by:
   - explicit mojo response / callback, **or**
   - receiver disconnect **only if** Blink settles **every** pending resolver for that remote.
3. Never drop a receiver and leave promises pending through GC (`ScriptPromiseResolverBase::Dispose` → SIGABRT / error 6).

Durable fixes land only in `patches/**` + `patches/series`.

---

## Non-goals

- Turning off `dcheck_always_on`
- Broad privacy-sandbox / persona product rewrite
- Hand-editing `.patch` hunks
- Shipping handwriting promise-style cleanup as blocking work
- Claiming “compiles” from `pre-build` alone
- Manual browsing as primary validation
- Full packaging (`he auto-package`) unless explicitly requested
- **Phase 1 claiming Mode A (omitted binder) kills fixed** — that is Phase 2

---

## Background (ground truth)

Two distinct defect classes:

| Class | Mechanism | Symptom | Priority |
|---|---|---|---|
| **B — Bound-then-dropped** | Binder registered; bind fn bare-`return`s → `PendingReceiver` destroyed | Pipe dies. Safe **only if** Blink settles all pending resolvers | **P0** WebOTP (no settler) |
| **A — Omitted binder** | `if (HeliumPersonaAllowsX) map->Add` with no else | `GetInterface` → `ReportNoBinderForInterface` → `ReportBadMessage` → kill | **P1** |

### Live status (confirmed in tree)

| API / site | Status today |
|---|---|
| **WebOTP** | Always registered via `BindWebOTPServiceReceiver` in `build/src/content/browser/browser_interface_binders.cc`; bind body in `render_frame_host_impl.cc` bare-returns when `IsEnabled() && !allow_web_otp`. Blink `credentials.get({otp})` calls `Receive` with raw `ScriptPromiseResolver` + `OnSmsReceive` only — **no** `ScopedPromiseResolver` / disconnect settler → **error 6** |
| Shape detection, Contacts, Background **Fetch**, WebNN, Gamepads | Conditional `map->Add` → Mode A kill |
| WebXR `VRService` | **Already safe:** allow → real binder; else → `EmptyBinderForFrame` (and `ENABLE_VR` off path also EmptyBinder) |
| AIManager | **Template fixed:** always `map->Add`; the cached manager checks the current persona on every request and completes every denied availability/create request; covered by `AIManagerTest`, the content-browser-client test, and Window/Worker transition + forced-GC browser regressions |
| OneShot/Periodic Background **Sync** | Always registered (not Mode A); product may later want deny stubs — **out of Phase 2** |
| Trust tokens | Bare-return OK at runtime (Blink `TrustTokenQueryAnswererConnectionError`); audit/test only |
| Handwriting | Style inconsistency only; low priority |

**Correct in-tree patterns to copy:**

| Pattern | Example | When |
|---|---|---|
| Always register + per-request explicit denial | AI (`persona-ai-binder-stability.patch`) | Cached reply-bearing interfaces where policy can change during the execution context lifetime |
| Always register + EmptyBinder | WebXR else-branch | Kill-fix **only** when no hung promise surface, or settlement proven |
| Explicit deny callback / status | Local fonts `kPermissionDenied`; WebAuthn `NOT_ALLOWED_ERROR`; OTP `SmsStatus` | Request/response methods |
| Drop + Blink disconnect settler | Trust tokens | Bare-return only after proven settler |

**Durable patches involved (series order ~167–181):**

- `patches/helium/core/persona-contacts-background-fetch-runtime-gating.patch`
- `patches/helium/core/persona-privacy-sandbox-runtime-gates.patch`
- `patches/helium/core/persona-web-api-runtime-gates.patch` — WebOTP gate, shape/WebNN/gamepads, many binders
- `patches/helium/core/persona-local-fonts-access.patch` — callback-denial template
- `patches/helium/core/persona-ai-binder-stability.patch` — **reference only**; always-register must win

**Registration vs deny-path distinction:** WebOTP is **always registered** in the binder map; the unsafe deny is in RFH bind, not a missing `map->Add`. Do not “fix” WebOTP by touching map registration alone.

---

## Disabled-API behavioral contract

For any intentional persona disable:

1. **Never omit** a binder that an enabled Blink build can request under default feature/platform flags solely because persona says no.
2. Deny path must **consume** `PendingReceiver` (bind stub, empty-binder drop, or explicit close)—never leave the broker with no binder.
3. If Blink issues an async mojo call that owns a `ScriptPromiseResolver`, deny must either:
   - **respond** on that call (preferred when status/callback exists), or
   - **disconnect** with a Blink handler that rejects/resolves **all** pending resolvers for that remote.
4. Fail closed: no capability leak. Prefer existing error shapes (`NotAllowed` / `NotSupported` / `kPermissionDenied` / terminal `SmsStatus` / cancelled) over new fingerprintable strings.
5. Intentional disable must **never** become `ReportBadMessage` / process kill.
6. **Forbidden:** empty success that pretends the API worked; hanging forever as “denial.”

| Strategy | Stops BadMessage? | Settles JS? | Fail-closed? | Use when |
|---|---|---|---|---|
| Explicit error / `callback.Run(deny)` / terminal status | Yes | Yes | Yes | Request/response (fonts, WebAuthn, OTP `Receive`, Contacts `Select`, haptics) |
| Always-on binder + drop / EmptyBinder | Yes | **Only if** Blink disconnect settles all resolvers | Yes | Service interfaces after settlement proof |
| Neutral empty success | Yes | Yes | **No** | Forbidden |

**Critical:** Do not assume “close receiver ⇒ promise rejects.” Verify per API.  
**`is_connected()==false` alone is never sufficient acceptance** for promise-bearing surfaces.

---

## Phase 1 — WebOTP error-6 (first PR, independently shippable)

### Objective

Eliminate SIGABRT/error 6 when `allow_web_otp=false`: OTP `credentials.get` must **settle** without abandoned `ScriptPromiseResolver` GC DCHECK. No capability leak; no renderer kill.

**Explicit Phase 1 non-goals:** omitted-binder Mode A kills (contacts/shape/WebNN/bg-fetch/gamepads) remain until Phase 2.

### Recommended implementation

**Primary (ship in PR1): browser-side Receive-settling deny stub**

Bare-return is wrong for WebOTP because Blink has **no** disconnect settler today. AI-style drop alone is insufficient unless Blink is fixed in the same PR.

1. Keep WebOTP **always registered** in `browser_interface_binders.cc` (already true at ~line 1368).
2. Replace bare-return in `RenderFrameHostImpl::BindWebOTPServiceReceiver` with a **bound deny path**:
   - Tiny self-owned deny/`WebOTPService` stub (local helper near bind site **or** small addition beside `content/browser/sms/webotp_service.{cc,h}` — choose lower patch conflict; do not force DocumentService)
   - Implements:
     - `Receive()` → terminal `SmsStatus` handled by Blink `OnSmsReceive`  
       **Preferred default:** `kUnhandledRequest` (“OTP retrieval request not handled.”) or `kCancelled`  
       Avoid defaulting to `kBackendNotAvailable` without metrics review (that status is tied to GMS backend failure + UKM/histograms in `webotp_service.cc`)
     - `Abort()` no-op / complete as needed
   - Do **not** construct real `SmsFetcher` / side effects
   - Do **not** set `document_used_web_otp_` on deny
3. Fail-closed: never grant OTP success when flag is false

**Optional same-PR hardening (only if small and low-conflict):**

4. Blink: wrap OTP resolver in `ScopedPromiseResolver` + disconnect path (mirrors Trust Tokens)
5. Optional: `CredentialManagerProxy::WebOTPService` disconnect handler

Do **not** ship drop-only AI-style WebOTP without (4). Prefer (2) alone for minimal first PR.

### Ordered tasks

1. Confirm live gate in `build/src/content/browser/renderer_host/render_frame_host_impl.cc` (`BindWebOTPServiceReceiver`) and `OnSmsReceive` status mapping in `authentication_credentials_container.cc`.
2. Implement deny stub + wire bind path for `!allow_web_otp`.
3. Add automated unit test proving settlement under disabled persona (see test design below).
4. Preserve enabled-path regression (`WebOTPServiceTest` / create path when allowed).
5. Export into durable patch; run gates.

### Likely files

| Role | Path |
|---|---|
| Gate | `content/browser/renderer_host/render_frame_host_impl.cc` (+ `.h` only if needed) |
| Stub helper | tiny local helper near bind site **or** `content/browser/sms/webotp_service.{cc,h}` |
| Tests | Prefer **chrome-level** persona injection (AI pattern) or content test with **explicit** test `ContentBrowserClient` snapshot override — discovery step, not free RFH injection |
| Optional Blink | `third_party/blink/renderer/modules/credentialmanagement/authentication_credentials_container.cc`, `scoped_promise_resolver.{h,cc}`, `credential_manager_proxy.{cc,h}` |

### Durable patch + workflow

**Default: `patch-fix`** of `helium/core/persona-web-api-runtime-gates.patch` when only existing-layer files change (confirmed BindWebOTP owner).

Correct patch-fix sequence (audit-corrected — `quilt-fix.sh` is **refresh**, not the edit entrypoint):

```bash
python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
# prepare disposable patchwork if needed (rebuild if dirty / series mismatch)
# then in codex_tmp/patchwork_src:
#   quilt push helium/core/persona-web-api-runtime-gates.patch
#   quilt edit / quilt add as needed
#   edit sources at that layer only
NITROUS_QUILT_SRC=codex_tmp/patchwork_src \
  ./devutils/quilt-fix.sh helium/core/persona-web-api-runtime-gates.patch
python3 devutils/agent_patch_guard.py --mode patch-source
```

**Alternate: `hot-dev` → new thin top patch** when adding new helper/test files or quilt layering is painful:

```bash
# --patch is a NEW root-stack patch name; export-hotfix publishes a new top.
# Never hot-start an existing owner patch name.
python3 devutils/agent_patch_guard.py --mode hot-start \
  --patch helium/core/persona-webotp-binder-stability.patch \
  --file content/browser/renderer_host/render_frame_host_impl.cc
# hot-add BEFORE editing any extra file
python3 devutils/agent_patch_guard.py --mode hot-add --file content/browser/sms/<new_or_extra>.cc
# ... implement in build/src only on declared files ...
python3 devutils/agent_patch_guard.py --mode export-hotfix
# After export: root queue advanced → rebuild/re-apply build/src before next hot-dev.
# Do not reuse dirty codex_tmp/patchwork_src or patchcheck_src.
```

Never hand-edit patch hunks; never treat hot tree as SoT after export.  
**Do not present hot-dev as “amend web-api.”** Amend = patch-fix only.

Series note: if hot-export is used, `persona-webotp-binder-stability.patch` lands **after** `persona-ai-binder-stability.patch` (new top), not inside the contacts→privacy→web-api→fonts→ai block.

### Tests (automated only)

| Test | Intent |
|---|---|
| **Mandatory:** disabled-persona WebOTP settlement | Bind with `allow_web_otp=false`; `Receive`; expect chosen terminal `SmsStatus`; remote usable for reply; no hang after Mojo flush |
| **Mandatory regression:** enabled path | Existing WebOTP create/receive when allowed |
| Test harness design | Prefer chrome unit modeled on `DisabledPersonaClosesAIManagerReceiver` (`PersonaService` + active snapshot), **or** content unit with a test `ContentBrowserClient` that returns a snapshot with `allow_web_otp=false`. Treat harness choice as a discovery/implementation step |
| Optional content browser | `credentials.get({otp:{transport:["sms"]}})` under persona — **stretch** (SMS mock / flags / secure origin harness) |
| Optional forced-GC | Death/insurance only after deny + `CollectAllGarbageForTesting` — **not** Phase 1 acceptance |

### Verification commands

```bash
# compile feedback (not delivery gate)
python3 devutils/syntax_check.py \
  content/browser/renderer_host/render_frame_host_impl.cc
# include any new stub .cc as well
# if gen headers missing first:
#   resolve real ninja label (discovery), e.g. often content_unittests / unit_tests
#   python3 devutils/build_targets.py <resolved_label>
#   re-run syntax_check

# focused gtest (exact binary path + new names TBD when written)
# out/Default/content_unittests --gtest_filter='...'
# out/Default/unit_tests --gtest_filter='*WebOTP*Persona*:*DisabledPersona*'

# delivery gate (repo + fresh apply + source-backed validation — NOT full C++ compile proof)
python3 devutils/agent_patch_guard.py --mode pre-build
```

**Target labels:** treat `content/test:content_unittests` / `chrome/test:unit_tests` as **candidates only** — resolve real ninja labels / binary paths under `out/Default` before claiming test run success.

**Distinguish:** `syntax_check` / `build_targets` = compile evidence; `pre-build` = repository/patch validation only. `patch-source` is intermediate feedback, not delivery.

### Acceptance criteria

- `allow_web_otp=false` never leaves OTP `ScriptPromiseResolver` pending on the broken path (settled via `Receive` status at minimum)
- No SIGABRT/error 6 from abandoned OTP resolver under DCHECK builds for this path
- No SMS side effects / no success when disabled
- No `ReportBadMessage` for WebOTP interface name
- Enabled path unchanged
- Changes durable in `patches/**` + series; `pre-build` green; compile evidence reported separately
- **PR1 does not require Phase 2 binder-map work and does not claim Mode A fixed**

### Phase 1 risks

| Risk | Mitigation |
|---|---|
| Sites relied on hung OTP promises | Explicit reject/cancel is correct fail-closed |
| Wrong `SmsStatus` metrics/UKM | Prefer `kUnhandledRequest` / `kCancelled`; don’t set `document_used_web_otp_` |
| Drop-only without Blink settler | Forbidden as sole fix |
| Persona snapshot injection cost in content tests | Prefer chrome PersonaService pattern or explicit test CBC override |
| Forced-GC hard to automate | Mandatory bar = settled Receive; GC optional |
| Patch ownership conflict | Prefer patch-fix of web-api gates; else new thin top only |
| Metric pollution | Status choice is the main open product preference; settlement first |

### Rollback

Revert only WebOTP deny-stub (+ test) hunks (in web-api gates **or** thin top patch). Leaves omitted-binder work intact. Never “fix” by disabling DCHECKs.

---

## Phase 2 — Omitted binders (ReportBadMessage / renderer kill)

### Objective

Every persona-gated interface Blink can request is **always registered**. Disabled path never hits `ReportNoBinderForInterface`. Capability remains fail-closed. Settlement is **API-specific**.

### API inventory / matrix

| API family | Gate helper | Registration sites | Defect today | Preferred disable action | Settlement requirement |
|---|---|---|---|---|---|
| **Contacts** `ContactsManager` | `HeliumPersonaAllowsContacts` | Frame map | Conditional `map->Add` | **Always `Add` + Select-denying stub/callback** (live Blink has **no** `set_disconnect_handler`; `Select()` parks resolver until `OnContactsSelected`) | Must settle `Select` (and any other reply-bearing methods). Drop/EmptyBinder **forbidden** unless Blink disconnect settler lands in the **same** change |
| **Background Fetch** | `HeliumPersonaAllowsBackgroundFetch` (`allow_background_sync` flag name) | Frame + service worker | Conditional `map->Add` | **Always `Add` + deny-register/unregister/fetch callbacks / stub** | Verify **each** promise-bearing method. Soft “drop or deny” **not allowed** until settlement proven |
| **Shape detection** (Barcode/Face/Text) | `HeliumPersonaAllowsShapeDetection` | Frame + dedicated/shared/service worker maps | Conditional `map->Add` | Always `Add`; drop / empty-bind may be OK for **detect** paths that already have disconnect handlers — **verify**, don’t assume full coverage (esp. Face provider create) | Pair pipe test + at least one async detect settlement test per provider class |
| **WebNN** (+ weights provider) | `HeliumPersonaAllowsWebNn` ∧ Chromium feature | Frame + workers | Persona in `map->Add` condition | Keep feature/platform guards; remove **persona** from Add condition; gate inside bind | One settlement test for `createContext` / related; don’t claim all ops covered by provider disconnect alone |
| **Gamepads** monitor/haptics | `HeliumPersonaAllowsGamepads` | Frame (monitor + haptics) | Conditional `map->Add` | Always `Add`. **Haptics:** deny stub that completes `PlayVibrationEffectOnce` / `ResetVibrationActuator` callbacks (no disconnect settler in `GamepadDispatcher`). Monitor may be kill-fix-only only after confirming no hung promises | Pipe-close alone **does not** finish Phase 2 for gamepads |
| **WebXR** `VRService` | `HeliumPersonaAllowsWebXr` | Frame | **Already** EmptyBinder else | **Keep**; do not reintroduce omit | Existing XR disconnect paths; regression only |
| **AIManager** | N/A (always on) | Frame + workers + SW | Fixed with dynamic request-time denial | **Do not re-gate registration, cache the persona decision, or drop the receiver** | Unit coverage for every method; cached-remote Window/Worker transition, settlement, and forced-GC browser regressions |
| **WebOTP** | `allow_web_otp` | Always registered | Phase 1 | Out of Phase 2 | Phase 1 |
| **Background Sync** OneShot/Periodic | — | Always registered | Not Mode A | Optional later product decision | N/A for this phase |

### Worker deny pattern (required language)

`EmptyBinderForFrame` is **frame-only**. For dedicated/shared/service worker maps, use one of:

1. bind lambda that drops `PendingReceiver` without constructing real service, or  
2. self-owned empty/deny impl bound on that worker map.

Every shape / WebNN / background-fetch registration site (frame + all worker maps that currently gate) must change together.

### Ordered tasks

1. For each Mode A row: change to **always `map->Add`** at every registration site.
2. Move persona check into bind lambda / impl with the matrix strategy above.
3. Prefer AI always-register + proven settlement model; use EmptyBinder only where settlement-safe or non-promise.
4. Preserve Chromium feature/platform guards (`ENABLE_VR`, WebNN feature, etc.); persona is an **extra** fail-closed layer.
5. Tests per family.
6. Export via **patch-fix of the owning patch** (mandatory split below).

### Durable patches + PR split (mandatory)

| PR | Patch | Owns |
|---|---|---|
| **2a** | `persona-contacts-background-fetch-runtime-gating.patch` | Contacts + Background Fetch deny stubs (hang class) |
| **2b** | `persona-web-api-runtime-gates.patch` | Shape, WebNN, gamepads; WebXR regression only |
| — | `persona-ai-binder-stability.patch` | Dynamic AI request denial + regressions; must not reintroduce conditional AI `map->Add` or bind-time-only policy caching |

**Default workflow:** **`patch-fix`** each owner patch (prepare patchwork → quilt push owner → edit → `quilt-fix.sh` → `patch-source`).  
**Alternate:** `hot-dev` with **new** top patch names only if quilt-fix of the owner is conflict-heavy — never hot-start existing owner names.

### Likely files

- `content/browser/browser_interface_binders.cc` (primary; all map sites)
- Small empty/deny helpers colocated if needed
- Contacts / Background Fetch impl create paths as needed for deny stubs  
  (exact helper file names = discovery when implementing)
- Tests: content binder / chrome unit tests modeled on `DisabledPersonaSettlesAIManagerRequests`

### Tests

Per family (at least Contacts, shape trio, BackgroundFetch, WebNN; Gamepads if changed; VRService regression; AI always-register invariant):

1. **No-BadMessage / pipe test:** disabled persona → bind interface remote → `FlushForTesting` → either `!is_connected()` **or** bound deny stub answers; never ReportBadMessage.
2. **Settlement test:** one async API surface proves promise/callback settles (**not** pipe-only). Mandatory for Contacts, BG Fetch, Gamepad haptics, WebNN create, shape detect.

### Verification

```bash
python3 devutils/syntax_check.py content/browser/browser_interface_binders.cc
# resolve real ninja labels first, then:
python3 devutils/build_targets.py <resolved content unittests label>
python3 devutils/build_targets.py <resolved chrome unit_tests label>
python3 devutils/agent_patch_guard.py --mode pre-build
```

### Acceptance criteria

- With persona on and flags false, requesting contacts / shape / WebNN / background-fetch / gamepads **never** hits `ReportNoBinderForInterface`
- No privacy capability grant when disabled
- WebXR empty-binder preserved; AI always-register invariant preserved (hard acceptance)
- Each changed family has kill-fix proof **and** API-specific settlement proof where promises exist
- Durable patches + `pre-build` green; compile evidence separate
- PR 2a and 2b ship separately by owner patch

### Phase 2 risks

| Risk | Mitigation |
|---|---|
| EmptyBinder stops kills but leaves hangs | Settlement pass required; Contacts/BG Fetch/Gamepads default to stubs |
| `allow_background_sync` naming vs Fetch-only | Don’t silently gate OneShot/Periodic Sync without product decision |
| Fail-open / late filter after real service construct | Gate before service construction |
| web-api vs AI both touch binders map | Edit applied stack; series order; pre-build; never re-conditionalize AI |
| Feature flags confused with persona | Keep `#if` / feature guards; persona only extra deny |
| Worker sites missed | Checklist every map registration site in `browser_interface_binders.cc` |

### Rollback

Revert always-register/deny-stub changes in contacts + web-api patches independently. AI stability remains independent.

---

## Phase 3 — Remaining bare-return audit

### Objective

Inventory every persona bare-return / early-return on mojo Bind **and** callback-bearing methods. Fix only paths that can hang, BadMessage, or abandon resolvers. Trust tokens stay disconnect model unless proven broken.

### Ordered tasks (main deliverable = inventory table)

1. Inventory `if (!HeliumPersonaAllows…) return;` / equivalent across:
   - `content/browser/renderer_host/render_frame_host_impl.cc`
   - `chrome/browser/chrome_content_browser_client.cc`
   - `content/browser/webauth/authenticator_common_impl.cc`
   - privacy-sandbox associated binds / method gates
   - fonts, speech, print, handwriting, gamepads leftovers
2. **Primary Phase 3 deliverable:** scan privacy-sandbox **OnceCallback** early-returns around `HeliumPersonaAllowsPrivacySandboxApis` (and related RFH methods) for “return without `callback.Run`”.
3. Classify each: **callback denial** | **drop + proven Blink settler** | **unsafe (fix)** | **sync UI / N/A**.
4. **Trust tokens:** keep bare-return; optional explicit close is cosmetics only; add/adjust persona-focused unit only if coverage gap.
5. **SharedStorage / Attribution** associated binds: confirm disconnect vs hang per method.
6. **Handwriting:** optional unify empty-promise styles — **non-blocking**.
7. Deliver short inventory table in PR description; change only unsafe rows.

### Likely files / patches

| Site | Patch | Action |
|---|---|---|
| TrustToken bare-return | `persona-privacy-sandbox-runtime-gates.patch` | Keep + test/comment only if needed |
| Shared storage / attribution / OnceCallback gates | same | Fix only unsafe callback drops |
| AI bare-return | `persona-ai-binder-stability.patch` | Keep |
| Gamepads if not done in P2 | `persona-web-api-runtime-gates.patch` | Deny-stub/settlement as in P2 |
| Handwriting | privacy-sandbox gates | Optional style |

### Workflow

- `explore` inventory first (read-only)
- **`patch-fix`** privacy-sandbox (+ web-api leftovers)
- New cross-cutting helper patch only if necessary (prefer not)

### Tests

- Trust-token: disabled PST → disconnect rejects pending query (extend only if gap)
- Any fixed method: assert callback ran or promise rejected
- No broad retest of handwriting unless changed

### Verification

```bash
# after patchwork edit of owner:
NITROUS_QUILT_SRC=codex_tmp/patchwork_src \
  ./devutils/quilt-fix.sh helium/core/persona-privacy-sandbox-runtime-gates.patch
python3 devutils/agent_patch_guard.py --mode patch-source
python3 devutils/syntax_check.py <touched .cc>
python3 devutils/build_targets.py <resolved labels>
python3 devutils/agent_patch_guard.py --mode pre-build
```

### Acceptance criteria

- No known persona-disable path drops a receiver/callback without either a fail response or a **proven** Blink disconnect settler
- Trust-token disable still rejects via connection error; existing Blink disconnect tests remain valid
- Handwriting not blocking
- Inventory published; only unsafe paths changed

### Phase 3 risks

| Risk | Mitigation |
|---|---|
| “Fixing” Trust Tokens by forbidding without settler | Keep proven Blink connection-error model |
| Scope creep into full privacy rewrite | Inventory + fix unsafe only |
| False safety from comments without tests | Require settlement proof for any changed path |

---

## Phase 4 — Validation / export / rollout

### Objective

Ship durable patches only; every PR independently gated; compile evidence never confused with `pre-build`.

### Ordered tasks

1. **Ship Phase 1 as first PR** (WebOTP only).
2. After any `export-hotfix`: root queue advanced → **rebuild/re-apply `build/src`** before next hot-dev; discard/rebuild dirty `codex_tmp/patchwork_src` and `codex_tmp/patchcheck_src` when state diverges.
3. Phase 2 as **two PRs**: **2a** contacts/bg-fetch patch, **2b** web-api patch.
4. Phase 3 PR: audit + residual fixes / tests.
5. Per PR final sequence:

```bash
# after hot-dev:
python3 devutils/agent_patch_guard.py --mode export-hotfix
# or after quilt edit + refresh:
#   NITROUS_QUILT_SRC=codex_tmp/patchwork_src ./devutils/quilt-fix.sh <owner.patch>
python3 devutils/agent_patch_guard.py --mode patch-source

# compile evidence (separate; resolve labels first)
python3 devutils/syntax_check.py <touched .cc files>
python3 devutils/build_targets.py <resolved content unittests label>
python3 devutils/build_targets.py <resolved chrome unit_tests label>
# optional if gen headers missing:
# python3 devutils/build_targets.py <smallest owning target>
# then re-run syntax_check

# delivery gate
python3 devutils/agent_patch_guard.py --mode pre-build
```

6. Automated tests only: content/chrome unit + browser tests; forced-GC for WebOTP if its harness exists and for AI Promise-abandonment coverage. **No** random manual browsing as sign-off.
7. Confirm series hygiene:
   - Existing block: contacts → privacy-sandbox → web-api → local-fonts → **ai-binder-stability**
   - Any hot-export top patch sits **after** that block
8. No hand-edited hunks; no hot-tree-only delivery.

### Acceptance criteria (rollout)

| Phase | Must prove |
|---|---|
| 1 | WebOTP settles; no error-6 path; Mode A **not** claimed fixed; pre-build + focused compile/tests |
| 2a | Contacts + BG Fetch always registered; deny stubs settle; no BadMessage; fail-closed |
| 2b | Shape/WebNN/gamepads always registered; settlement per matrix; WebXR/AI invariants; no BadMessage |
| 3 | Bare-return + OnceCallback inventory complete; unsafe paths fixed |
| 4 | Durable SoT only; pre-build mandatory; compile evidence separate |

### What each command proves

| Command | Proves | Does **not** prove |
|---|---|---|
| `agent_patch_guard --mode pre-build` | Repo checks, patch fresh-apply, source-backed validation | Chromium C++ full compile |
| `agent_patch_guard --mode patch-source` | Intermediate patch-source validation | Delivery / full pre-build |
| `syntax_check.py` | Touched TUs compile given existing gen deps | Full target graph / all gen files |
| `build_targets.py` | Named ninja targets build | Unrelated targets / packaging |
| `quilt-fix.sh` | Refresh + path-normalize of already-edited quilt layer | Edit entrypoint / full validation |

---

## Recommended first PR (small)

**Phase 1 only — WebOTP stability**

- Browser deny stub that binds and answers `Receive` with `SmsStatus::kUnhandledRequest` or `kCancelled` (metrics-safer default than `kBackendNotAvailable`)
- Unit test proving settlement under `allow_web_otp=false` (chrome PersonaService pattern preferred)
- Durable amend of `helium/core/persona-web-api-runtime-gates.patch` via **patch-fix**, **or** new top `helium/core/persona-webotp-binder-stability.patch` via hot-dev if new files force it
- Do **not** bundle binder-map rewrite, contacts, WebNN, gamepads, or handwriting
- Explicitly state: **error-6 fixed; ReportBadMessage for omitted binders not fixed**

**Follow-ups:** Phase 2a (contacts/bg-fetch), Phase 2b (web-api omitted binders), Phase 3 audit PR.

---

## Cross-cutting risks

| Risk | Mitigation |
|---|---|
| Sites detecting reject vs hang | Settling is required for process stability |
| Pipe tests alone | Always pair OTP/contacts/fetch/WebNN/haptics with resolver/callback tests |
| Fail-open | Never bind real capability service then filter late; stubs must not forward |
| AI pattern inconsistency | Always-register invariant; deny semantics may be disconnect vs status — document per API |
| Patch conflicts (web-api / contacts / AI) | Amend owners via patch-fix; hot-export only as new top; rebuild trees after export |
| Build flags | Preserve feature/platform guards; persona is extra deny |
| Security regression | Default flags remain false; tests assert deny |
| Worker empty-bind hand-waving | Name drop/self-owned pattern; change every map site |
| Test-injection cost | Prefer proven chrome PersonaService pattern over inventing RFH injection |
| UKM/histogram pollution on OTP status | Prefer `kUnhandledRequest` / `kCancelled` |

---

## Mode cheat-sheet

| Phase | Default mode | Why |
|---|---|---|
| 1 WebOTP | **patch-fix** `persona-web-api-runtime-gates.patch` (or hot-dev **new** `persona-webotp-binder-stability.patch` if new helpers) | Existing BindWebOTP owner; independently shippable |
| 2a Contacts/BG Fetch | **patch-fix** contacts patch | Hang-class stubs; separate PR |
| 2b shape/WebNN/gamepads | **patch-fix** web-api patch | Separate PR; AI invariant |
| 3 bare-return audit | **patch-fix** privacy-sandbox (+ web-api leftovers) | Existing gates |
| 4 delivery | `export-hotfix` / `patch-source` + **`pre-build`** + separate `syntax_check`/`build_targets` | Durable SoT + dual evidence |

---

## Evidence anchors (do not claim re-run)

- Live `browser_interface_binders.cc`: conditional Adds for contacts/shape/WebNN/gamepads/bg-fetch; WebXR EmptyBinder else; always AI + WebOTP registration
- `render_frame_host_impl.cc`: WebOTP bare-return when `!allow_web_otp`
- Blink OTP `Receive` → `OnSmsReceive` without `ScopedPromiseResolver`
- AI request-time denial + `DisabledPersonaSettlesAIManagerRequests` in `chrome_content_browser_client_unittest.cc`; all AIManager availability/create methods and cached-remote policy transitions in `ai_manager_unittest.cc`; Window/Worker cached-remote settlement and forced-GC coverage in `ai_on_device_interactive_uitest.cc`
- `agent_patch_guard.py`: `--patch` is **new root-stack patch** for `hot-start`; `export-hotfix` publishes a **new top**
- `quilt-fix.sh`: push (if needed) + refresh + path normalize — not the edit entrypoint
- Series: contacts (167) → privacy (168) → web-api (169) → local-fonts (179) → ai-binder-stability (181)

**The original synthesis pass ran no tests. Current AIManager execution evidence
is recorded in the status block above; it does not claim runtime-test or object-build success.**
