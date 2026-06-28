#!/usr/bin/env python3
"""Run CI-equivalent validation for the Helium repository."""

import argparse
import ast
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def find_repo_root():
    current = Path(__file__).resolve()
    for parent in (current.parent, *current.parents):
        if (parent / '.git').exists() and (parent / '.github' / 'workflows' / 'ci.yml').exists():
            return parent
    print('ERROR: Could not find Helium repository root from script path.', file=sys.stderr)
    sys.exit(2)


ROOT = find_repo_root()

CODE_INFRA_PATHS = {
    '.cirrus_requirements.txt',
    '.python-version',
    '.style.yapf',
    '.github/actions/ci-setup/action.yml',
    '.github/workflows/ci.yml',
}

PATCH_OR_CONFIG_PATHS = {
    'deps.ini',
    'domain_regex.list',
    'domain_substitution.list',
    'downloads.ini',
    'flags.gn',
    'pruning.list',
    'resources/patch_order.toml',
    '.github/workflows/ci.yml',
    '.github/workflows/lint.yml',
}

PATCH_TOOL_PATHS = {
    'devutils/check_downloads_ini.py',
    'devutils/check_files_exist.py',
    'devutils/check_gn_flags.py',
    'devutils/check_patch_files.py',
    'devutils/lint.py',
    'devutils/update_lists.py',
    'devutils/validate_config.py',
    'devutils/validate_patches.py',
}

I18N_TOOL_PATHS = {
    'devutils/i18n.py',
    'devutils/i18n_generate.py',
    'devutils/i18n_lint.py',
}

SKILL_PATH = '.codex/skills/helium-validate'


def quote_command(command):
    return shlex.join(str(part) for part in command)


def run(command, *, cwd=ROOT):
    print(f'\n$ {quote_command(command)}', flush=True)
    result = subprocess.run([str(part) for part in command], cwd=cwd, check=False)
    if result.returncode != 0:
        print(f'\nFAILED: {quote_command(command)}', file=sys.stderr)
        sys.exit(result.returncode)


def run_status(command, *, cwd=ROOT):
    print(f'\n$ {quote_command(command)}', flush=True)
    return subprocess.run([str(part) for part in command], cwd=cwd, check=False).returncode


def git_check_ignore(path):
    result = subprocess.run(['git', 'check-ignore', '-q', str(path)],
                            cwd=ROOT,
                            check=False)
    return result.returncode == 0


def git_lines(args):
    result = subprocess.run(['git', *args],
                            cwd=ROOT,
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(ref):
    files = set(git_lines(['diff', '--name-only', '--diff-filter=ACMR', ref, '--']))
    files.update(git_lines(['ls-files', '--others', '--exclude-standard']))
    return sorted(path for path in files if path)


def touches_any(files, predicates):
    return any(predicate(path) for path in files for predicate in predicates)


def path_under(prefix):
    prefix = prefix.rstrip('/') + '/'
    return lambda path: path.startswith(prefix)


def path_in(paths):
    return lambda path: path in paths


def non_ignored_python_files(prefix):
    return sorted(str(path) for path in (ROOT / prefix).rglob('*.py') if not git_check_ignore(path))


def yapf_check_command(python, prefix):
    files = non_ignored_python_files(prefix)
    return [
        python,
        '-m',
        'yapf',
        '--style',
        '.style.yapf',
        '-e',
        '*/third_party/*',
        '-dp',
        *files,
    ]


def utils_checks(python):
    return [
        yapf_check_command(python, 'utils'),
        ['./devutils/run_utils_pylint.py', '--hide-fixme'],
        ['./devutils/run_utils_tests.sh'],
    ]


def devutils_checks(python):
    return [
        yapf_check_command(python, 'devutils'),
        ['./devutils/run_devutils_pylint.py', '--hide-fixme'],
        ['./devutils/run_devutils_tests.sh'],
    ]


def run_commands(commands):
    for command in commands:
        run(command)


def run_i18n_checks(python):
    with tempfile.TemporaryDirectory(prefix='helium-i18n-') as tmpdir:
        generated = Path(tmpdir) / 'source.gen.json'
        run([python, './devutils/i18n.py', 'generate', '-o', generated])
        run(['diff', '-u', './i18n/source.gen.json', generated])
    run([python, './devutils/i18n_lint.py'])


def run_skill_self_checks():
    skill_dir = ROOT / SKILL_PATH
    skill_md = skill_dir / 'SKILL.md'
    runner = skill_dir / 'scripts' / 'run_validation.py'

    print('\nSkill self-checks:', flush=True)
    if not skill_md.is_file():
        print(f'ERROR: Missing {skill_md.relative_to(ROOT)}', file=sys.stderr)
        sys.exit(1)

    content = skill_md.read_text(encoding='utf-8')
    if not content.startswith('---\n'):
        print('ERROR: SKILL.md must start with YAML frontmatter.', file=sys.stderr)
        sys.exit(1)
    try:
        _, frontmatter, body = content.split('---', 2)
    except ValueError:
        print('ERROR: SKILL.md frontmatter is not closed.', file=sys.stderr)
        sys.exit(1)

    required = {'name': False, 'description': False}
    for line in frontmatter.splitlines():
        if line.startswith('name:'):
            required['name'] = line.split(':', 1)[1].strip() == 'helium-validate'
        if line.startswith('description:'):
            required['description'] = bool(line.split(':', 1)[1].strip())
    missing = [key for key, ok in required.items() if not ok]
    if missing:
        print(f"ERROR: SKILL.md missing/invalid frontmatter keys: {', '.join(missing)}",
              file=sys.stderr)
        sys.exit(1)
    if '[TODO' in content:
        print('ERROR: SKILL.md still contains TODO template text.', file=sys.stderr)
        sys.exit(1)
    if not body.strip():
        print('ERROR: SKILL.md body is empty.', file=sys.stderr)
        sys.exit(1)

    ast.parse(runner.read_text(encoding='utf-8'), filename=str(runner))
    print('  - SKILL.md frontmatter/body OK')
    print('  - scripts/run_validation.py syntax OK')


def resolve_source_tree(args):
    if args.source_tree:
        source_tree = Path(args.source_tree)
        if not source_tree.is_absolute():
            source_tree = ROOT / source_tree
    else:
        source_tree = ROOT / 'chromium_src'
    if not source_tree.is_dir():
        print(
            f'ERROR: Chromium source tree not found at {source_tree}. '
            'Provide --source-tree or omit --with-source.',
            file=sys.stderr,
        )
        sys.exit(2)
    return source_tree


def prepare_source_tree(python, source_tree):
    cache_dir = ROOT / 'chromium_download_cache'
    cache_dir.mkdir(exist_ok=True)

    run([python, './utils/downloads.py', 'retrieve', '-i', 'deps.ini', '-c', cache_dir])
    if run_status([python, './utils/downloads.py', 'retrieve', '-i', 'downloads.ini', '-c', cache_dir]) != 0:
        run([python, './utils/clone.py', '-o', source_tree])

    if not source_tree.is_dir():
        run([python, './utils/downloads.py', 'unpack', '-i', 'downloads.ini', '-c', cache_dir, source_tree])
    run([python, './utils/downloads.py', 'unpack', '-i', 'deps.ini', '-c', cache_dir, source_tree])


def run_source_checks(python, source_tree):
    run([python, './devutils/check_chromium_src_clean.py', '--source-tree', source_tree])
    run([python, './devutils/validate_patches.py', '-l', source_tree, '-v'])
    with tempfile.TemporaryDirectory(prefix='helium-lists-') as tmpdir:
        tmpdir = Path(tmpdir)
        pruning = tmpdir / 'pruning.list.gen'
        domain_substitution = tmpdir / 'domain_substitution.list.gen'
        run([
            python,
            './devutils/update_lists.py',
            '--tree',
            source_tree,
            '--pruning',
            pruning,
            '--domain-substitution',
            domain_substitution,
            '--no-error-unused',
        ])
        run(['diff', '-u', 'pruning.list', pruning])
        run(['diff', '-u', 'domain_substitution.list', domain_substitution])


def selected_auto_checks(files, python, lint_python):
    commands = []

    utils_touched = touches_any(files, [
        path_under('utils'),
        path_in(CODE_INFRA_PATHS),
        path_in({'devutils/run_utils_pylint.py', 'devutils/run_utils_tests.sh'}),
    ])
    devutils_touched = touches_any(files, [
        path_under('devutils'),
        path_in(CODE_INFRA_PATHS),
    ])
    config_touched = touches_any(files, [
        path_under('patches'),
        path_under('resources'),
        path_in(PATCH_OR_CONFIG_PATHS),
        path_in(PATCH_TOOL_PATHS),
    ])
    lint_touched = config_touched or touches_any(files, [
        path_in({'.github/workflows/lint.yml'}),
        path_in(PATCH_TOOL_PATHS),
    ])
    i18n_touched = touches_any(files, [
        path_under('i18n'),
        path_under('patches'),
        path_in(I18N_TOOL_PATHS),
        path_in({'.github/workflows/lint.yml'}),
    ])
    skill_touched = touches_any(files, [
        path_under(SKILL_PATH),
    ])

    if utils_touched:
        commands.extend(utils_checks(python))
    if devutils_touched:
        commands.extend(devutils_checks(python))
    if config_touched:
        commands.append([python, './devutils/validate_config.py'])
    if lint_touched:
        commands.append([lint_python, './devutils/lint.py'])

    return commands, i18n_touched, skill_touched


def print_changed(files):
    if not files:
        print('No changed or untracked files detected by git.', flush=True)
        return
    print('Changed/untracked files considered for validation:', flush=True)
    for path in files:
        print(f'  - {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',
                        action='store_true',
                        help='Run all local CI-equivalent checks except source-backed Chromium checks.')
    parser.add_argument('--self-check-only',
                        action='store_true',
                        help='Only validate this skill and runner script.')
    parser.add_argument('--with-source',
                        action='store_true',
                        help='Also run Chromium-source-backed patch and list validation.')
    parser.add_argument('--source-tree',
                        help='Chromium source tree for --with-source. Defaults to ./chromium_src.')
    parser.add_argument('--prepare-source',
                        action='store_true',
                        help='Download/unpack Chromium inputs before source-backed validation.')
    parser.add_argument('--changed-from',
                        default='HEAD',
                        help='Git ref used for auto-scope validation. Defaults to HEAD.')
    parser.add_argument('--python',
                        default=sys.executable,
                        help='Python executable for CI Python commands. Defaults to this interpreter.')
    parser.add_argument('--lint-python',
                        help='Python executable for lint.yml checks. Defaults to --python.')
    args = parser.parse_args()

    python = args.python
    lint_python = args.lint_python or args.python
    print(f'Using Python for local CI commands: {python}', flush=True)
    print(f'Using Python for lint.yml commands: {lint_python}', flush=True)

    if args.self_check_only:
        run_skill_self_checks()
    elif args.full:
        print('Running full local CI-equivalent validation.', flush=True)
        run_skill_self_checks()
        run_commands(utils_checks(python))
        run_commands(devutils_checks(python))
        run([python, './devutils/validate_config.py'])
        run([lint_python, './devutils/lint.py'])
        run_i18n_checks(lint_python)
    else:
        files = changed_files(args.changed_from)
        print_changed(files)
        commands, needs_i18n, needs_skill = selected_auto_checks(files, python, lint_python)
        if not commands and not needs_i18n and not needs_skill and not args.with_source:
            print('\nNo CI-equivalent checks selected for this change set.')
        if needs_skill:
            run_skill_self_checks()
        run_commands(commands)
        if needs_i18n:
            run_i18n_checks(lint_python)

    if args.prepare_source and not args.with_source:
        print('ERROR: --prepare-source requires --with-source.', file=sys.stderr)
        sys.exit(2)

    if args.with_source:
        if args.source_tree:
            source_tree = Path(args.source_tree)
            if not source_tree.is_absolute():
                source_tree = ROOT / source_tree
        else:
            source_tree = ROOT / 'chromium_src'
        if args.prepare_source:
            prepare_source_tree(python, source_tree)
        else:
            source_tree = resolve_source_tree(args)
        run_source_checks(python, source_tree)

    print('\nValidation completed successfully.')


if __name__ == '__main__':
    main()
