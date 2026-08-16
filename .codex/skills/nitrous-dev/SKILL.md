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

Check the hot tree. Agents run validation only and MUST NOT start a compile;
the user compiles once, after several feature slices are done. `syntax_check.py`
is allowed only when the hot tree already has the relevant generated
dependencies — never run `build_targets.py` to supply them.

```bash
python3 devutils/syntax_check.py [-o build/src/out/Default] FILE...
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --ci-env --keep-going
```

Reserved for the user, not for agents: `build_targets.py`, `gn gen`,
`he configure`, `he build`, `he auto-build`, `he auto-package`.

### Compile-check boundary

`pre-build` does not compile Chromium C++. A successful guard proves patch and
repository validation, not buildability. GN configuration also does not create
generated mojom, GRIT, protobuf, or other headers under `out/Default/gen`.

`syntax_check.py` invokes clang directly and does not prepare Ninja dependencies.
Generated-header failures on a cold tree (`out/Default/gen/...`,
`*.mojom-forward.h`, `precompile.h-cc`) are inconclusive: they are NOT source
failures, and an agent must not build the owning target to resolve them — do not
run `devutils/build_targets.py` to supply them. Record the file as
"not compile-verified" and leave it to the user's compile pass.

Only when the user explicitly asks for a build, a package, or proof of
buildability may a target be built. In that case, if the Ninja target itself
fails, report its earliest real error rather than a later missing-file error.

Report `pre-build` and compile evidence separately. By default an agent may
claim validation passed and must state that compilation was not run.

### Delivery template

Claim exactly what was proven, in this order:

1. **Validation passed** — name the guard mode that succeeded.
2. **Patch migrated cleanly** — the new patch is in `patches/`, listed in
   `patches/series`, and fresh-applied against the root and macOS queues.
3. **Compilation not verified** — C++ correctness is deferred to the user's
   unified build.
4. **Trees cleaned** — list what `cleanup` reclaimed.

Never claim that the next compile will succeed. `pre-build` proves migration and
application, not buildability.

After validation passes, export through isolated staging:

```bash
python3 devutils/agent_patch_guard.py --mode export-hotfix
```

The command refuses stale quilt metadata, changed queues, undeclared baseline
mismatches, empty changes, existing patch names, failed quilt operations,
unexpected top patches, and root/macOS fresh-apply failures. It does not write
the live patch queue until staging has replayed successfully.

The published root queue is newer than the current hot-tree quilt stack, so the
hot tree is stale by construction. Reclaim it instead of leaving 15 GB+ of dead
source behind:

```bash
python3 devutils/agent_patch_guard.py --mode cleanup
```

`cleanup` removes the disposable trees (`build/src`, `codex_tmp/patchcheck_src`,
`codex_tmp/patchwork_src`, and other `codex_tmp/*_src` validation trees), prints
the reclaimed size, and leaves `patches/`, `chromium_src`, and tracked
repository files untouched. Run it as the last step of a finished hot-dev slice;
the user's next build re-creates `build/src`.

Never rewrite `.pc` to fake synchronization.

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

Only on an explicit user request to build or package. `he auto-package` is
already incremental: `___helium_build_products` calls `autoninja` (siso), and
the `___helium_auto_prepare` `ensure_*` steps are idempotent guards that skip
source prep, merge, push, and GN when each is already current.

```bash
python3 devutils/agent_patch_guard.py --mode pre-build
source platform/macos/build.sh
he auto-package
```

Incrementality is lost when the merged patch queue goes stale, because
`___helium_ensure_merged_queue` then runs `quilt pop -a` before re-merging. So
avoid repeated patch exports and `he merge && he push` between edits.

## Recovery

```bash
python3 devutils/agent_patch_guard.py --mode normalize-artifacts
```

If `.pc` points at a missing/old queue, the applied list differs, quilt leaves
rejects, or a generated queue differs from source, stop and rebuild that tree.
Deleting only `.pc` is not recovery. Report the failed command and affected tree.
