# Persona fingerprint lifecycle

Nitrous separates rendering fingerprint refresh from complete browser identity
rotation. The operations use the same Persona seed lineage, but they have
different scopes and reload behavior.

Preset protection version 1, portable fonts, explicit route intent, legacy
upgrade behavior, and their verification limits are documented in
[Persona preset privacy policy](persona-preset-privacy-policy.md).

## Success standard: controlled browser cohort

The product goal is **not** perfect hardware cloning of an arbitrary Windows or
Linux machine (font rasterization, GPU drivers, TCP stack, and platform
authenticators cannot be reproduced 100% on a macOS Chromium host).

The goal **is** that every Profile using the same **Device Pack** presents the
same **controlled browser cohort**: correlated claim (UA / UA-CH / platform /
normalized defaults), verified network wire profile (TLS / HTTP/2 / HTTP/3),
and fail-closed local bypasses (for example WebRTC off by default). Within a
cohort, rendering noise seeds provide per-profile diversity without inventing
illegal wire fingerprints.

## Device Pack and network identity

An enabled non-default Persona must bind a verified **Device Pack**
(`devicePackId` → complete identity template with non-empty network variants).

| Field | Meaning |
| --- | --- |
| `devicePackId` | Catalog id of the complete identity (for example `149000`) |
| `networkReady` | True when a Device Pack with network variants is bound |

Activation rules:

1. Selecting or activating a Persona **without** a complete network identity is
   **rejected** (`network_identity_unavailable`). Nitrous never activates a
   Windows/Linux **claim** while TLS/H2/H3 remain the host stack.
2. Runtime snapshot resolution is **fail-closed**: an enabled Persona that loses
   its Device Pack does not expose spoofed navigator claims.
3. Network config resolution order: explicit `devicePackId` → exact claim match
   → cohort-compatible match (same OS / arch / bitness / Chrome major with a
   verified network catalog entry).

Presets for OS families that lack captured network variants ship with
`networkReady: false` until authentic captures are checked in.

## Fingerprint refresh

Use **Refresh fingerprints** in Persona settings to increment the Profile's
fingerprint generation. Canvas, font metrics, Audio, geometry readbacks, and
other generation-aware rendering surfaces receive new deterministic tokens
after pages are reloaded. The selected complete browser identity, UA, UA-CH,
and platform remain unchanged. Within that identity, Profile refresh may select
another verified network variant, so an individual TLS hash can change without
switching to a different complete identity template.

Use **Refresh fingerprints for this site** in the Persona indicator menu to
increment only the active HTTP(S) origin's rendering generation. The command
is available only when a Persona is active with `site_profile` rotation scope,
and reloads only the active tab. The service returns `unsupported_scope` for a
site refresh under `profile` or `global` scope, and `invalid_origin` for a
non-HTTP(S) origin. An empty origin never falls through to Profile refresh.
Site refresh never installs a site-specific TLS, HTTP/2, or HTTP/3 template;
network identity remains Profile-scoped so connection reuse cannot mix
identities between origins.

Within one Persona and generation, repeated reads are stable. Automatic
rotation also includes its configured time bucket in the seed. A manual
refresh increments generation independently of that bucket, so it changes the
tokens even when the current time bucket is still zero.

Rendering token derivation uses the `persona-noise-v2` domain and includes
Profile generation and site generation as separate inputs. A missing or legacy
string-only site record has site generation zero. Refreshing site A advances
only A's site generation; a later Profile refresh advances the Profile generation
for A and every other origin, even if A has its own epoch record. Existing
Profile seeds, Persona ids and site epoch records are retained.

This derivation change produces a one-time change in rendering tokens, including
for fixed seeds. It does not rewrite the seed shown in Settings. A fixed seed
still participates in manual generation changes and the configured rotation
bucket; it is not a promise that outputs remain unchanged across those events.

## Daily seed lifecycle

Daily random-seed rotation is evaluated on the first successful enabled Persona
activation in each browser session. Seed preparation belongs to the activation
candidate: the old seed and date remain persisted until network acceptance, and
rollback restores them. Failed activation does not consume the session check,
so a retry can evaluate the stale day again.

`GetFingerprintSettings`, `GetActiveSnapshot` and `ResolveActivePersona` are
read-only. They do not initialize or replace a seed. A browser session that
crosses local midnight keeps its committed seed and remains available; switching
Personas during that session does not trigger another daily replacement. There
is no daily timer, midnight reload, or midnight request block. A fresh Profile
gets its initial seed through activation or an explicit seed operation. Fixed
seed mode disables daily and exit-cleanup automation.

## Editing an active Persona

Settings uses `SavePersonaAndApply`. An inactive Persona is saved immediately.
For an active Persona, changes to identity fields use the same request gate,
network acknowledgement, state compare-and-set, execution-context restart and
rollback path as activation. Settings waits for that result and labels the
action **Save and apply**, with an inline notice about reloading Profile tabs
and restarting workers.

Changes confined to name, display name and icon do not restart execution
contexts. Runtime identity audits ignore the presentation-only snapshot name
when comparing frame and worker evidence. The legacy synchronous `SavePersona`
entry rejects active identity edits with `requires_activation`; it cannot bypass
the transaction. Changing the active named network route through this save path
remains rejected by its existing reactivation rule.

## Rendering consistency and field support

Screen width/height, CSS `device-width`/`device-height`, and color depth resolve
the same active Persona. The configured device scale factor is a baseline:
page zoom continues to affect `window.devicePixelRatio`, CSS resolution, document
DPR, DPR Client Hints and PaintWorklet readbacks. Actual viewport dimensions and
layout zoom remain Chromium's values. Off-thread PaintWorklet carries the
exposed DPR separately from the effective zoom used for painting.

WebGL line-width ranges, point-size ranges and shader precision are returned
unchanged from the driver. Independent perturbation of these capabilities could
turn a valid range such as Metal's `[1, 1]` into an invalid range. Canvas and
WebGL pixel-readback noise remain enabled independently.

Element and Range rectangle bindings share a bounded, monotone coordinate map
keyed by the client-rectangle token and coordinate. The map preserves zero
dimensions, ordering and bounding unions, and applies only when returning web
readbacks. Identical raw geometry maps to identical exposed geometry. Font
metrics use HMAC-derived scales keyed by the text, font description and raw
metrics; related scalar fields, selection rectangles, bounding boxes, clusters
and hit-test offsets share those scales. Neither approach changes layout or
claims that arbitrary adversarial measurements are indistinguishable from a
different physical device.

The following fields are retained as legacy metadata and reported as
`unsupported` in contract/effective/import diagnostics:

- `fontRendering.id`, `engine`, `antialiasing`, `subpixelRendering`, `lcdText`
- `gpu.webglProfile`, including `maxCombinedTextureImageUnits`
- `gpu.webgl2Profile`, including `uniformBufferOffsetAlignment`
- `advanced.hardwareNoise`

Old imports and unchanged saves preserve these values. New changes to them are
rejected, and the corresponding Settings controls are disabled. No hardware
noise token is issued. Device Pack-constrained UA and UA-CH fields remain
editable as requested values; the active editor shows saved/effective
differences without expanding the verified identity catalog.

The [fingerprint coverage matrix](persona-fingerprint-coverage.md) records the
configuration-to-consumer mapping and regression tests. Source coverage checks
and patch fresh-apply validation do not execute those Chromium tests.

## Complete identity rotation

**Rotate complete identity** stages a verified identity template containing a
correlated browser version, UA, UA-CH, platform, TLS, HTTP/2, and HTTP/3
identity. Nitrous commits the template only after every NetworkContext accepts
it, rejects concurrent rotations, rolls back partial failures, closes sockets
and protocol sessions from the old generation, clears TLS session state, stops
workers, and reloads the Profile's open tabs.

Complete identity rotation requires at least two verified complete templates.
Availability follows the catalog described below. Transaction tests also use
injected templates to exercise acceptance and rollback independently of the
production catalog.

## WebRTC

WebRTC behavior is expressed by `advanced.webrtcMode` and the explicit
`advanced.allowWebRtc` permission:

| Mode | Behavior |
| --- | --- |
| `disabled` | `RTCPeerConnection` is blocked; `allowWebRtc` must be false |
| `altered` | WebRTC is available, but non-proxied UDP is disabled |
| `real` | WebRTC uses Chromium's normal policy; `allowWebRtc` still gates use |

Under a new Persona, WebRTC remains disabled by default because
`advanced.allowWebRtc` is false. An enforced network route also disables
non-proxied UDP at the browser preference read point, regardless of the
Persona mode, so ICE cannot bypass the configured HTTP or SOCKS route. VPN
does not replace this control.

`getUserMedia` / `enumerateDevices` are separate surfaces and are not controlled
solely by the WebRTC toggle.

## Media devices

An enabled Persona always replaces the host's audio-input, video-input, and
audio-output enumeration with a synthetic list. The default `1/1/1` counts are
one synthetic device of each kind; they do not mean passthrough. Custom counts
and labels are applied only to the requested device kinds, and audio input and
output use distinct ids, labels, and groups. Synthetic raw ids are scoped by
Persona id and profile fingerprint generation before Chromium applies its
normal origin-specific media-device hashing, so a Persona switch or profile
refresh does not preserve a cross-Persona device identifier. The disabled
system-real snapshot continues to use Chromium's normal device enumeration.

Synthetic enumeration is resolved before Chromium starts AudioService or video
capture enumeration, and Persona-backed device-change listeners do not start
the host device monitors. Real microphone/camera `getUserMedia`,
`selectAudioOutput`, preferred-sink selection, and reuse of a previously saved
nondefault sink id fail closed while an enabled Persona is active. Default
speaker playback remains system-backed so ordinary page audio continues to
work. Display and tab capture are separate surfaces and keep their normal
Chromium behavior. To use real local capture devices or select a physical
output device, switch to the disabled system-real snapshot rather than relying
on a synthetic count or label combination.

The audit does not call `enumerateDevices` because doing so can trigger
permissions and observable hardware work. `getEffective` includes the resolved
media counts, labels, and audio latency values, while contract and audit
surfaces describe the configured synthetic/fail-closed policy. Physical device
enumeration therefore remains a configured implementation guarantee rather
than an audit-time observation. Separately, the passive runtime probe records
when default speaker playback reaches the real-time Web Audio render callback;
that evidence proves output activity, not physical-device anonymization.

## Current network support

| Chrome | Platform claim | Complete identities | Network variants | Status |
| --- | --- | ---: | ---: | --- |
| 149.0.7827.114 | macOS arm64 | 1 (`149000`) | 2 shared desktop | Production |
| 149.0.7827.114 | Windows x64 | 1 (`149100`) | same desktop cohort | Production (cohort) |
| 149.0.7827.114 | Linux x64 | 1 (`149200`) | same desktop cohort | Production (cohort) |
| 147-148 | any | 0 | 0 | Awaiting captures |

The two Chrome 149 network variants (`149001` / `149002`) are host
SSLClientSocket goldens with ML-DSA off/on. They are **shared** by all three
complete identities. Independent Chrome-for-Testing 149.0.7827.115 captures on
macOS arm64 and Linux x86_64 show matching structural TLS fields (ciphers,
groups, signature algorithms, ALPN); extension order is seed-steered.
Reference captures live under `net/data/network_persona/reference/`.

Ordinary fingerprint refresh may select between verified variants or change
legal order seeds, but it does not promise that every order-insensitive JA4
value changes. Complete identity rotation can now switch among the three
Chrome 149 desktop identities (macOS / Windows / Linux claims) while keeping
the same desktop network cohort.

New templates must come from a real Chromium build and include source version,
platform, feature state, capture method, and protocol fixtures. Do not assemble
JA3, JA4, HTTP/2, or HTTP/3 fields by hand into combinations the current
Chromium, BoringSSL, and QUIC stacks cannot emit. Captures should be replayed
and golden-tested on the shipping Nitrous host build before a Device Pack is
marked `networkReady`.

## Import and export

`Nitrous.persona/v3` is the current export schema. `Nitrous.persona/v2` and
`helium.persona/v1` remain accepted as legacy import formats. New exports retain
the protection policy version and any original configuration backup.
Runtime Profile generation, per-origin generation epochs, active network
sessions, and TLS session state are stored separately and are not transferred
with an exported Persona. Importing a Persona therefore does not clone the
source Profile's live fingerprint generation. Imported Personas still must
bind a verified Device Pack before activation.

## Named network routes

A Persona references a Profile-scoped proxy through `network.routeId` with
`network.routeMode = proxy`, or explicitly permits direct access with
`routeMode = direct`. An empty route id alone does not authorize direct access.
New preset copies inherit a valid active proxy or remain inactive with
`routeMode = unset` until the user chooses a route.
Routes are stored separately from Personas and contain a stable id, display
name, mode, host, port, optional SOCKS5 credentials, and enforcement setting.
Credentials are never returned to Settings, CDP, export, effective, or audit
responses. HTTP and HTTPS routes do not accept stored credentials because
Chromium does not pre-bind them; transaction-bound credentials are supported
only for SOCKS5.

Activation treats the Persona and route as one barrier-checked transaction:

1. Validate the Persona, Device Pack, route existence, credential availability,
   and native proxy ownership before quiescing execution contexts.
2. Block Persona network requests in the Profile and shared system
   NetworkContexts. Blocking cancels active URLLoaders, WebSockets,
   WebTransports, direct sockets, DNS and proxy lookups, and OHTTP requests
   before acknowledgement. Existing URLLoader factory and child resolver pipes
   are invalidated so queued messages cannot cross the identity generation
   boundary. P2P sockets, P2P DNS/default-address probes, and mDNS responders
   are made inert without emitting mDNS goodbye packets; their old pipes are
   retired at release. PAC/WPAD initialization, polling, retry, and system
   proxy requests are suspended. Reporting and Domain Reliability uploads are
   cancelled and their web-origin state is reset for the new generation. New
   covered requests, preconnects, and explicit proxy-config reloads are
   rejected; browser-side certificate verifications and their AIA/OCSP
   URLLoader factories are also cancelled or rejected. New contexts inherit
   the gate.
3. Pin the candidate proxy config for current and newly created Profile
   NetworkContexts, propagate SOCKS credentials and network Persona config,
   and wait for every available acknowledgement.
4. Compare-and-set the Persona state, fingerprint seed, last-used id, and
   active route id.
5. Re-apply the committed state, restart Profile execution contexts, then
   release the request gate with a second convergence pass for contexts created
   during the first release. Certificate verification moves to a fresh
   CertNetFetcher for each epoch; the old fetcher remains shut down, and the new
   generation's factory is bound while requests are still blocked. The local
   gate opens only after the CertVerifierService acknowledges that factory.
   Return success only for
   `commitState=committed` and `restartResult=restarted`.
6. On failure, restore the old Persona and route together while the request
   gate remains closed. If convergence cannot be proved, keep Persona
   resolution unavailable instead of silently falling back.

This is not a claim of an instantaneous atomic update inside NetworkService:
proxy, SOCKS credentials, and protocol identity travel over separate Mojo
calls. The request gate creates a verifiable old/new epoch boundary for HTTP(S)
URLLoaders, WebSockets, WebTransports, direct TCP/UDP sockets, direct DNS and
proxy lookups, OHTTP requests, P2P/mDNS work, PAC/WPAD resolution, reporting,
Domain Reliability, new preconnects, and certificate AIA/OCSP fetches in the
affected Profile and shared system NetworkContexts while those calls converge.
Profile and system gate acknowledgements are serialized, and a newly created
NetworkContext starts blocked during the transaction.

The boundary cannot retract a datagram already accepted by the kernel before
the block acknowledgement, and it does not cover traffic owned by unrelated
NetworkContexts. Runtime audit evidence also does not prove that every
observable output is indistinguishable. These limits must not be described as
instantaneous process-wide atomicity. The system route rejects credentialed
routes and route changes while enabled.

Active routes cannot be edited or deleted in place. Create a replacement route,
then bind it through Persona activation or the active profile's Save and Apply
transaction. A plain save cannot change an active Persona's route; the Settings
save action uses the transaction and rolls back a failed route switch.

## Introspection and automation

Settings and the trusted browser-target `NitrousPersona` CDP domain expose the
same service operations:

| Operation | Purpose |
| --- | --- |
| `getContract` | Return schema version, supported modes, outcomes, and capability metadata |
| `validate` | Validate and normalize input without persistence |
| `resolve` | Resolve a saved Persona and its active status |
| `getEffective` | Return requested/effective values, differences, assurance, and transition state |
| `getAudit` | Return a conservative surface and route-binding audit |
| `activate` | Run the complete activation transaction |

The domain is available only to trusted browser-target clients. Its optional
`browserContextId` currently accepts only `default`, which selects the
last-used original Profile. It does not address arbitrary regular or
off-the-record Profiles.

ChromeDriver accepts `nitrous:personaId` and an optional
`nitrous:browserContextId` capability. For a launched browser the context
defaults to `default`; attaching to an existing browser requires it explicitly.
Android Chrome and `chrome-headless-shell` reject the capability. Session
creation succeeds only after activation reports both a committed state and a
completed execution-context restart. Startup selection and automation use the
same continuation, so an `always_ask` picker cannot remain as the session's
first tab after successful activation.

`getAudit` is intentionally conservative. It queries every live frame in the
active primary frame trees and compares the renderer-held snapshot plus Canvas,
Audio, hardware, font-metric, and ClientRect token presence with the expected
Persona. Dedicated, shared, and service workers report their actual startup
snapshot plus Canvas, Audio, hardware, and font-metric token presence through
their BrowserInterfaceBroker; ClientRect is not applicable to workers. The
audit enumerates all live workers in loaded StoragePartitions, so an existing
worker without an attestation is reported as `unreported` rather than silently
omitted. Frame and worker results distinguish verified, mismatched,
unreachable/unreported, partially verified, and not applicable states.

An enabled Persona also exposes a deterministic WebGPU capability profile:
core mode exposes only the mandatory `core-features-and-limits` feature while
compatibility mode exposes no optional features; adapter limits use the WebGPU
portable baseline plus the configured compute-invocation limit, and `requestDevice`
rejects features or limits outside that public profile. The passive probe
records the final adapter identity, complete feature-name and limit-value
collections, compatibility mode, subgroup bounds, fallback status, and
successful device creation. Audit compares all Persona-controlled adapter
identity fields and every capability value without returning the values
themselves. Workers replace their startup report when later passive evidence
appears. Default speaker playback reaches `runtime_output_verified` only after
the same execution context has observed both Persona latency getters and its
real-time audio render callback has run.

The overall probe remains `partial`: this evidence verifies runtime propagation
of the snapshot and token state, not the resulting Canvas/Audio/font values.
Canvas readback paths consume the propagated token before 8-bit, F16, and F32
`getImageData`, Blob/Data URL export, ImageBitmap transfer, WebGL/WebGPU source
uploads, WebCodecs source reads, and `captureStream` delivery, including worker
`OffscreenCanvas`. Ordinary canvas composition such as `drawImage` remains
unmodified, so a copied canvas receives noise only when its pixels reach a
script-visible readback boundary. Protected readback fails closed if the
snapshot cannot be copied. Direct floating-point `getImageData` retains its
requested representation; exported floating-point bitmap sources use the
supported F16 representation while retaining normalized-range,
premultiplied-alpha, and color-space semantics. Persona-protected WebGL
readback is limited to tightly packed RGBA8 output, and WebGL pixel-pack-buffer
readback fails closed. The experimental WebGL-on-WebGPU backend is bypassed
while Persona canvas protection is active so the protected implementation
remains authoritative; a dedicated browser regression runs with
`WebGLOnWebGPU` enabled and verifies the protected readback policy. WebGPU
canvas usages that permit script readback
(`COPY_SRC`, `TEXTURE_BINDING`, or `STORAGE_BINDING`) also fail closed.
`getAudit` does not invoke those APIs itself. Physical media-device behavior,
WebRTC ICE, WebGPU shader execution and subgroup behavior, and other
permission- or hardware-dependent output surfaces still require separate,
opt-in observation. The overall probe therefore remains `partial`.
