---
name: nitrous-validate
description: >
  Use when validating Nitrous code, config, patches, i18n, scripts, skills,
  AGENTS.md, Chromium source-backed patch application, pre-build state, or a
  change set before handoff.
---

# Nitrous Validate

## Overview

Use **after** edits are done (or as handoff). Maps touched files to non-mutating
CI checks. For **how to edit / compile / export patches**, use `$nitrous-dev`
first — this skill does not replace the dev workflow.

## Mandatory handoff gate

Every task that changes repository files MUST run this command successfully
before reporting completion:

```bash
python3 devutils/agent_patch_guard.py --mode pre-build
```

Fix failures and rerun until it passes. The other modes below provide faster
intermediate feedback but do not replace this gate. This runs the checks needed
before `he auto-package`; it does not build or package unless the user requested
that separately. Read-only investigations are exempt.

## Compilation boundary

`pre-build` does not compile Chromium C++. Its success must be reported as
validation success, not compile or build success. GN output does not guarantee
that generated files under `out/Default/gen` exist, and `syntax_check.py` does
not ask Ninja to generate them.

Missing generated headers on a cold or rebuilt tree must not be reported as source compile failures. Prepare the smallest relevant target and rerun the
file check:

```bash
python3 devutils/build_targets.py path/to:target
python3 devutils/syntax_check.py path/to/file.cc
```

For Chromium source changes, handoff reports must list guard validation and
compile evidence separately. Without a targeted or actual build, say that
compilation was not verified. A full cold build is required only when requested
or when the task must prove the complete artifact builds.

## CI equivalence boundary

A local pass predicts a CI pass only for checks the repository controls. Four
kinds of drift have each turned a local green into a red CI job:

| Drift | Symptom | Guard |
|-------|---------|-------|
| Tool versions | yapf/pylint disagree between local and pinned | `--ci-env`, drift warning |
| System binaries | local has `quilt`, CI did not | `.ci_system_packages.txt` check |
| Empty scope | committed change means no diff, so nothing runs | `--require-checks` |
| Stale source tree | reused `chromium_src` predates a new dependency | freshness check |

Outside that boundary: runner image changes and the archive-retrieval fallback
to `clone.py` depend on upstream availability and cannot be reproduced locally.
CI remains the backstop for those.

## Default

From repository root:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py
```

Auto-scope compares against the upstream merge-base, so committed work stays in
scope until CI has seen it. Passing `--changed-from HEAD` on a clean tree
validates nothing; the runner says `SKIPPED`, and that is not a pass.

Exact CI parity, in a cached venv built from `.cirrus_requirements.txt` with the
`.python-version` interpreter:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --ci-env
```

Report every failure in one run instead of stopping at the first, which is how
CI's fail-fast hides later steps:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --keep-going
```

Optional Python versions:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --python python3.10 --lint-python python3.13
```

## Full local CI

Unclear impact, cross-module, CI config, or handoff:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --full
```

## Source-backed

When a Chromium tree is available and patches/lists changed:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

Network/download unpack only when intentional:

```bash
python3 .codex/skills/nitrous-validate/scripts/run_validation.py --with-source --prepare-source --source-tree chromium_src
```

## Agent patch guard (preferred unified entry)

```bash
python3 devutils/agent_patch_guard.py --mode quick
python3 devutils/agent_patch_guard.py --mode patch-source
python3 devutils/agent_patch_guard.py --mode pre-build
python3 devutils/agent_patch_guard.py --mode normalize-artifacts
```

## Reporting

Always report which command ran and the outcome. If source-backed was relevant
but skipped (no tree), say so explicitly.

## Resources

- `scripts/run_validation.py` — CI-equivalent runner
- `devutils/agent_patch_guard.py` — series/artifact + scoped validation
