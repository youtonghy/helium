---
name: nitrous-dev
description: >
  Nitrous Chromium patch development workflow: hot-tree edits, compile feedback
  (syntax_check / build_targets), quilt export, patch hygiene, persona/feature
  work without hand-editing .patch diffs. Use when modifying Chromium source,
  fixing compile errors, changing patches, persona/fingerprint work, hot-dev,
  export-patch, quilt-fix, he build iteration, or when the user runs /nitrous-dev.
  Always load this before editing build/src or patches/.
---

# Nitrous Dev

## Before any edit

1. Declare mode: `explore` | `hot-dev` (default) | `export-patch` | `patch-fix` | `package`.
2. If unclear → **`hot-dev`**.
3. Do **not** hand-edit `patches/**/*.patch` diff bodies.

## Modes

### explore

- Read only. No writes.

### hot-dev (default development)

**Writable:** only `build/src`  
**Forbidden:** `patches/**`, `chromium_src`, per-iteration `he merge && he push`

```bash
# C++ seconds
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...

# Link / TS / action minutes
python3 devutils/build_targets.py [--from-failed] [target...]

# Optional product incremental confirm
source platform/macos/build.sh && he build
```

**Done:** compile checks green. Say explicitly: **patch not exported yet**.

### export-patch

Use when hot-dev logic is ready to land in `patches/`.

1. Map changed files → one target patch under `patches/` (e.g. `helium/core/persona-….patch`).
2. Prefer disposable patchwork + quilt-fix (or guard):

```bash
python3 devutils/agent_patch_guard.py --mode after-hotfix --patch helium/core/YOUR.patch
```

If guard's after-hotfix only refreshes from clean push (no hot-tree copy), use standard flow:

```bash
# unpack patchwork if needed, copy relevant edited files from build/src, then:
./devutils/quilt-fix.sh helium/core/YOUR.patch
python3 devutils/agent_patch_guard.py --mode patch-source
```

**Forbidden:** editing `.patch` hunks in an editor to fix line numbers.

**Done:** guard / fresh apply green; list refreshed patch names.

### patch-fix

Upstream merge or apply failures only.

```bash
python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
# fix via patchwork + quilt-fix, never hand-hunk
python3 devutils/agent_patch_guard.py --mode patch-source
```

### package

Only after validation:

```bash
python3 devutils/agent_patch_guard.py --mode pre-build
source platform/macos/build.sh
he auto-package
```

## Hard rules

| Do | Don't |
|----|--------|
| Edit `build/src` while iterating | Edit `patches/*.patch` diff text |
| One-shot export at end of slice | Refresh patch every few lines |
| Rebuild dirty trees | Delete only `.pc/` to "clean" |
| Main agent applies/refreshes patches | Multi-agent write same patch set |
| `NITROUS_*` env (fallback `HELIUM_*`) | Assume standalone `helium-macos` tree |

## Tree cheat sheet

| Path | Role |
|------|------|
| `build/src` | Hot tree |
| `codex_tmp/patchwork_src` | Quilt export |
| `codex_tmp/patchcheck_src` | Fresh apply only |
| `chromium_src` | Clean baseline only |
| `patches/` | Delivered SoT |

## Env

- `NITROUS_OUT_DIR` / `HELIUM_OUT_DIR` → `syntax_check`
- `NITROUS_BUILD_ROOT` / `HELIUM_BUILD_ROOT` → `build_targets`
- `NITROUS_QUILT_SRC` / `HELIUM_QUILT_SRC` → `quilt-fix.sh`

## After export → validate

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py
# or full / with-source per impact
```

## Failure report

State: failed command, cause, which tree may be dirty, whether rebuild is required.
