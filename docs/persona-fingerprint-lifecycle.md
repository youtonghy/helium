# Persona fingerprint lifecycle

Nitrous separates rendering fingerprint refresh from complete browser identity
rotation. The operations use the same Persona seed lineage, but they have
different scopes and reload behavior.

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
fingerprint generation. Canvas, font metrics, Audio, hardware readbacks, and
other generation-aware rendering surfaces receive new deterministic tokens
after pages are reloaded. The selected complete browser identity, UA, UA-CH,
and platform remain unchanged. Within that identity, Profile refresh may select
another verified network variant, so an individual TLS hash can change without
switching to a different complete identity template.

Use **Refresh fingerprints for this site** in the Persona indicator menu to
increment only the active HTTP(S) origin's rendering generation. The command
is available only when a Persona is active and reloads only the active tab.
Site refresh never installs a site-specific TLS, HTTP/2, or HTTP/3 template;
network identity remains Profile-scoped so connection reuse cannot mix
identities between origins.

Within one Persona and generation, repeated reads are stable. Automatic
rotation also includes its configured time bucket in the seed. A manual
refresh increments generation independently of that bucket, so it changes the
tokens even when the current time bucket is still zero.

## Complete identity rotation

**Rotate complete identity** stages a verified identity template containing a
correlated browser version, UA, UA-CH, platform, TLS, HTTP/2, and HTTP/3
identity. Nitrous commits the template only after every NetworkContext accepts
it, rejects concurrent rotations, rolls back partial failures, closes sockets
and protocol sessions from the old generation, clears TLS session state, stops
workers, and reloads the Profile's open tabs.

Complete identity rotation requires at least two verified complete templates.
The production catalog currently contains one complete Chrome 149/macOS arm64
identity, so the control is intentionally unavailable. Tests use an injected
second template to verify the transaction and rollback mechanism; that test
fixture is not a production identity.

## WebRTC

Under an active Persona, **WebRTC is disabled by default**
(`advanced.allowWebRtc = false`). `RTCPeerConnection` construction fails with
a standard `NotAllowedError` so sites cannot use ICE host candidates to learn
local network topology. Users may opt in from Persona advanced settings when
browser-based calling is required. VPN does not replace this control.

`getUserMedia` / `enumerateDevices` are separate surfaces and are not controlled
solely by the WebRTC toggle.

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

`helium.persona/v1` exports editable Persona configuration. Runtime Profile
generation, per-origin generation epochs, active network sessions, and TLS
session state are stored separately and are not transferred with an exported
Persona. Importing a Persona therefore does not clone the source Profile's
live fingerprint generation. Imported Personas still must bind a verified
Device Pack before activation.
