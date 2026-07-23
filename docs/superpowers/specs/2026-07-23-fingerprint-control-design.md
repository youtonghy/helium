# Fingerprint Control Settings

## Goal

Give a Profile owner direct control over its fingerprint seed without changing
the existing Persona profile editor. The feature is an independent Settings
subpage under Privacy and security and uses the existing Persona runtime,
snapshot, and noise-token propagation paths.

## User experience

`chrome://settings/fingerprint` appears next to Persona under Privacy and
security. It shows the current effective fingerprint seed, generation, and
last change time.

The owner chooses one mutually exclusive seed mode:

- **Randomly managed** creates a cryptographically random 32-byte hexadecimal
  seed. The owner can generate a new seed immediately.
- **Fixed seed** accepts and persists exactly one 64-character hexadecimal
  seed. It remains the effective seed until the owner changes mode or replaces
  it.

Automatic controls are available only in randomly managed mode:

- **Clear on exit** removes the effective random seed and its generation state
  while the Profile is shutting down. The next use creates a new seed.
- **Change daily** compares the persisted local calendar day with the current
  day on the first Profile use after startup. It creates a new seed once when
  the day changed. It never schedules a timer or reloads tabs in a live
  session.

Fixed seed mode disables both automatic controls. This makes the configured
seed durable and prevents policy from replacing it unexpectedly.

## Architecture

The page has its own route, TypeScript element, browser proxy, C++ Settings
handler, and localized strings. It does not embed or extend the Persona page.

`PersonaService` remains the sole owner of the effective fingerprint seed and
generation. Dedicated Profile preferences store the selected mode, fixed seed,
automation flags, and last automatic rotation day. The existing
`fingerprint_profile_salt` preference continues to hold only the active
32-byte seed so renderer and network consumers preserve their current
contract.

The service exposes one read operation for display state and explicit commands
to set the mode and seed, generate a new random seed, and update automatic
policy. It validates fixed seeds before mutation. Each effective seed change
increments the existing profile generation and reuses the current runtime
refresh path; no new parallel renderer protocol is introduced.

At service initialization, the daily rule is evaluated before the first active
snapshot is exposed. At Profile shutdown, the exit rule clears random state
before dependent runtime services are torn down. Fixed seed state is not
cleared by either automation rule.

## Error handling and privacy

Only 64-character hexadecimal fixed seeds are accepted. Invalid WebUI payloads
produce a structured error without changing preferences. Seeds are exposed
only through the local Settings WebUI requested by the Profile owner; they are
not sent to metrics, logs, or Persona import/export data.

The UI surfaces an unavailable/error state when no effective seed can be read,
and does not claim a replacement succeeded until the handler returns updated
state.

## Verification

Service tests cover fixed-seed validation, mode transitions, manual random
generation, daily lazy rotation, and exit cleanup. Handler tests cover input
validation and state responses; WebUI tests cover control enablement and
successful/error interactions. Chromium-targeted build evidence and the
repository `pre-build` gate are reported separately.
