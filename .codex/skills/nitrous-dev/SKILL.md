---
name: nitrous-dev
description: >
  Use when modifying Nitrous Chromium source, iterating in build/src, fixing
  compile errors, exporting a hot-tree change, repairing an existing patch,
  resolving quilt drift, or preparing a macOS build/package.
---

# Nitrous Dev

## Core invariant

`build/src` is disposable. `patches/` is durable. An automatic hot-tree export
must begin before the edit, prove the pre-edit baseline, generate a new top
patch in staging, replay it, validate the root and macOS queues, then publish.

Every task that changes repository files MUST run the packaging-equivalent
preflight before handoff:

```bash
python3 devutils/agent_patch_guard.py --mode pre-build
```

Fix failures and rerun the command before reporting completion. Targeted tests,
syntax checks, `quick`, `patch-source`, and `export-hotfix` are intermediate
feedback and do not replace this final gate. The gate does not require running
`he auto-package`; package only when the user requests a build or artifact.

Do not hand-edit patch hunks or `.pc` metadata.

## Choose a mode

| Mode | Use | Writable state |
|------|-----|----------------|
| `explore` | Read-only investigation | None |
| `hot-dev` | New behavior or compile fix | Declared files in `build/src` |
| `patch-fix` | Repair an existing patch | Disposable patchwork via quilt |
| `package` | Build/package after guards | Platform build outputs |

## Hot-dev: automatic new patch

Automatic export creates a new root-stack top patch only. Run this before the
first edit, listing every expected Chromium source path:

```bash
python3 devutils/agent_patch_guard.py --mode hot-start \
  --patch helium/core/my-change.patch \
  --file chrome/browser/example.cc \
  --file chrome/browser/example.h
```

Edit only the declared files in `build/src`. Before editing an additional file:

```bash
python3 devutils/agent_patch_guard.py --mode hot-add \
  --file chrome/browser/additional_file.cc
```

Compile against the hot tree:

```bash
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...
python3 devutils/build_targets.py [--from-failed] [target...]
```

### Compile-check boundary

`pre-build` does not compile Chromium C++. A successful guard proves patch and
repository validation, not buildability. GN configuration also does not create
generated mojom, GRIT, protobuf, or other headers under `out/Default/gen`.

`syntax_check.py` invokes clang directly and does not prepare Ninja dependencies.
Generated-header failures on a cold tree are inconclusive and must not be
reported as source failures. Build the smallest owning target, then rerun the
file check:

```bash
python3 devutils/build_targets.py path/to:target
python3 devutils/syntax_check.py path/to/file.cc
```

Only classify the result as a source compile failure after generated dependencies
exist and the file still fails. If the Ninja target fails, report its earliest
real error. Do not require an unconditional full cold build, but run a relevant
target or actual build whenever the task claims buildability or requests a
build/package. Report `pre-build` and compile evidence separately.

After compile checks pass, export through isolated staging:

```bash
python3 devutils/agent_patch_guard.py --mode export-hotfix
```

The command refuses stale quilt metadata, changed queues, undeclared baseline
mismatches, empty changes, existing patch names, failed quilt operations,
unexpected top patches, and root/macOS fresh-apply failures. It does not write
the live patch queue until staging has replayed successfully.

The published root queue is newer than the current hot-tree quilt stack. Rebuild
`build/src` before starting the next hot-dev slice. Never rewrite `.pc` to fake
synchronization.

Abort an incomplete session without reverting hot-tree files:

```bash
python3 devutils/agent_patch_guard.py --mode hot-abort
```

## Patch-fix: existing patch

Existing patch updates start from clean patchwork at that patch layer. Do not copy whole files from build/src into an earlier patch; the hot tree contains
later root/platform layers that would be folded into it.

```bash
python3 devutils/check_chromium_src_clean.py --source-tree chromium_src
# Rebuild codex_tmp/patchwork_src, push the exact target, edit there, then:
NITROUS_QUILT_SRC=codex_tmp/patchwork_src \
  ./devutils/quilt-fix.sh helium/core/existing.patch
python3 devutils/agent_patch_guard.py --mode patch-source
```

`quilt-fix.sh` stops on push failure and verifies `quilt top` before refresh.

## Package

```bash
python3 devutils/agent_patch_guard.py --mode pre-build
source platform/macos/build.sh
he auto-package
```

## Recovery

```bash
python3 devutils/agent_patch_guard.py --mode normalize-artifacts
```

If `.pc` points at a missing/old queue, the applied list differs, quilt leaves
rejects, or a generated queue differs from source, stop and rebuild that tree.
Deleting only `.pc` is not recovery. Report the failed command and affected tree.
