# Persona preset privacy policy

The 19 regional presets use protection version 1 and the `portable-v1` font
pack. They are privacy profiles with explicit UA/region/hardware fields. They
do not reproduce a real Windows, macOS, or Linux installation. Windows device
templates remain inferred without an independent Windows capture; macOS/Linux
reference captures still require runtime verification. WebGL capability limits
and shader precision remain native so advertised capabilities stay usable.

## Profile and network lifecycle

Each new preset-derived profile stores `sourcePresetId`, `presetRevision`, and
`protectionVersion`. New profiles and preset copies inherit the currently active
proxy only when that proxy still validates. Otherwise they remain inactive
with `network.routeMode = unset`. Activating a profile requires selecting a
valid proxy or explicitly selecting direct access. A deleted or invalid proxy
never becomes direct access implicitly. Quick preset activation without a valid
proxy creates a draft and opens it for route selection.

Legacy profiles remain readable and exportable. Opening an old profile does
not write settings or rotate identity. The upgrade action prepares a reviewable
draft; it recognizes an old preset from identity fields rather than its name.
Saving the upgrade retains the original record once in
`legacyProtectionSettings`. Custom profiles require the same explicit review.
Old protection versions cannot activate or produce an effective Persona
snapshot. Saving an active identity uses the existing network/snapshot/restart
transaction, including rollback on failure.

Exports use `Nitrous.persona/v3`; imports still accept v2 and the legacy Helium
v1 format. Stored historical speech voice arrays and unsupported fields survive
round trips, but they do not become effective capabilities.

## Portable fonts and rendering

`downloads.ini` is the resource catalog and hash authority. Font files are
pinned to immutable upstream commits with SHA-512; each is accompanied by its
SIL Open Font License 1.1 text, also pinned and packaged in Blink resources.
The nine font files and nine licenses total about 32 MiB before compression.
The resource installer verifies hashes before replacing individual files, and
source freshness validation checks every font/license, even when they share a
directory. The bundled CJK `.ttc` collection is explicitly excluded from source
binary pruning.

| Family | Resource | Style/locale behavior |
| --- | --- | --- |
| Noto Sans | Google Fonts variable regular and italic | Latin/Cyrillic and default sans-serif |
| Noto Serif | Google Fonts variable regular and italic | Serif aliases |
| Noto Sans Mono | Google Fonts variable | Monospace aliases |
| Noto Sans Devanagari | Google Fonts variable | Hindi fallback |
| Noto Sans Symbols 2 | Google Fonts regular | Symbol fallback |
| Noto Emoji | Google Fonts variable, monochrome | Fixed emoji fallback |
| Noto Sans CJK | Noto CJK regular TTC | JP=0, KR=1, SC=2, TC=3, HK=4 |

Fontations reads these bytes on all platforms. Persona fonts use fixed
antialiasing, subpixel positioning, linear metrics, no hinting, and no embedded
bitmaps. Variable weight/width and real Sans/Serif italics are retained; other
synthetic styles use the same policy across platforms. The language chooses
the CJK face, including a distinct Hong Kong face. Font metric and client rect
readback noise are enabled by default and retain the existing seed lifecycle.

CSS family lists, generics, allowed `local()` sources, Canvas, OffscreenCanvas,
workers, per-character fallback, and emoji all use this pack. Downloaded website
fonts remain allowed. Uncovered characters use a fixed bundled missing-glyph
face. Missing or invalid bundled resources fail closed at font loading rather
than selecting an installed font. This protects the font source and metrics;
identical final pixels across all GPU/Skia versions are not claimed.

## Speech and media preferences

Active Personas expose an empty speech voice list and reject speaking
asynchronously with `not-allowed`, without leaving a pending queue. Renderer
initialization, cached/late voice updates, the browser binder, and the native
backend are gated. There is no portable speech backend; old voice names are
retained only as historical data.

Presets default to sRGB, standard dynamic range, and reduced motion. These
values are editable and propagate through the Persona snapshot into dynamic
and cached CSS media evaluation, main frames, and cross-origin frames. Host
display or accessibility changes cannot change those advertised preferences.

## Regression evidence and verification boundary

Service tests cover all 19 defaults, route inheritance, explicit direct access,
missing/deleted proxies, draft quick activation, legacy identity matching,
read-only upgrade preparation, backup preservation, and invalid portable
settings. Renderer tests cover speech binding/cache denial, private text/emoji
fallback, and dynamic/cached media preferences. Browser tests cover multilingual
fonts, styles, allowed/blocked local sources, Canvas/OffscreenCanvas/Worker
measurements, media values in cross-origin frames, and non-hanging speech errors.
The host-display test also observes media-query listeners while changing HDR,
color space, scale, and reduced-motion preferences.

These C++ tests are authored for the user's unified build. Repository validation
and patch fresh-apply do not compile or execute them. TypeScript configuration
behavior and Python resource installation checks can run without a Chromium
build. The local font audit checks SHA-512, licenses, TTC family/index mapping,
and glyph availability for the preset languages plus combining marks and
emoji; this is not a shaping or visual test.

After compiling, run the affected Persona service/browser tests and Blink
font/media/speech tests. For visual QA, compare the same multilingual document
and font styles on macOS, Windows, and Linux; inspect CJK regional glyphs,
Devanagari shaping, combining marks, and emoji. Verify an old custom profile's
upgrade preview and backup, both network choices, proxy deletion, active-save
rollback, and unchanged media-query values/events after host preference changes.
