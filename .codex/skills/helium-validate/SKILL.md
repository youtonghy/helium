---
name: helium-validate
description: Run Helium repository validation using CI-equivalent commands after editing code, config, patches, i18n files, scripts, repository instructions, or validation tooling. Use when Codex needs to choose and run the right local checks before handing off work in /Users/youtonghy/github/Project/helium, including full CI-style validation and optional Chromium-source-backed patch/list checks.
---

# Helium Validate

## Overview

Use this skill after editing the Helium repository. It maps touched files to the same non-mutating checks used by GitHub Actions, then reports exactly what ran and what remains unverified.

## Default Workflow

From the repository root, run:

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py
```

The script reads `git diff HEAD` plus untracked files and selects checks for the changed scope. It uses CI's `yapf -rpd` diff mode, not the local wrappers that rewrite files.

If CI Python versions are installed locally, pass them explicitly:

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --python python3.10 --lint-python python3.13
```

Without these flags, the script uses the interpreter that launched it and prints that choice. `--python` maps to `.github/workflows/ci.yml`; `--lint-python` maps to `.github/workflows/lint.yml`.

## Full Local CI

Run full local CI-style checks when the impact is unclear, the edit crosses modules, CI config changed, or the work is ready to hand off:

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --full
```

This runs:

- skill self-checks when this project skill changed
- `python -m yapf --style .style.yapf -e '*/third_party/*' -rpd utils`
- `./devutils/run_utils_pylint.py --hide-fixme`
- `./devutils/run_utils_tests.sh`
- `python -m yapf --style .style.yapf -e '*/third_party/*' -rpd devutils`
- `./devutils/run_devutils_pylint.py --hide-fixme`
- `./devutils/run_devutils_tests.sh`
- `./devutils/validate_config.py`
- `python3 ./devutils/lint.py`
- i18n source generation drift check against `i18n/source.gen.json`
- `python3 ./devutils/i18n_lint.py`

## Source-Backed CI

CI also validates patches and source lists against a Chromium checkout. Run this only when a source tree is available or the task specifically requires source-backed validation:

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --source-tree chromium_src
```

To also retrieve/unpack the source inputs before validating, use:

```bash
python3 .codex/skills/helium-validate/scripts/run_validation.py --with-source --prepare-source --source-tree chromium_src
```

Use `--prepare-source` only when a network/download-heavy validation is intended.

This runs:

- optional source retrieval/unpack when `--prepare-source` is passed
- `python3 ./devutils/check_chromium_src_clean.py --source-tree <source-tree>`
- `./devutils/validate_patches.py -l <source-tree> -v`
- `./devutils/update_lists.py --tree <source-tree> --pruning <tmp> --domain-substitution <tmp> --no-error-unused`
- diffs generated `pruning.list` and `domain_substitution.list` output against committed files

## Reporting

Always include the validation command and outcome in the final response. If source-backed validation was relevant but not run because no Chromium source tree was available, state that explicitly.

## Resources

- `scripts/run_validation.py`: CI-equivalent validation runner.
