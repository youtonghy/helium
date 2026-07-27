#!/usr/bin/env python3
"""Run CI-equivalent validation for the Helium repository."""

import argparse
import ast
import configparser
import hashlib
import json
import shlex
import shutil
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

SKILL_PATHS = {
    'nitrous-dev': '.codex/skills/nitrous-dev',
    'nitrous-validate': '.codex/skills/nitrous-validate',
}
PYTHON_SCAN_EXCLUDES = {
    'devutils/i18n-data',
}

REQUIREMENTS_FILE = '.cirrus_requirements.txt'
SYSTEM_PACKAGES_FILE = '.ci_system_packages.txt'
PYTHON_VERSION_FILE = '.python-version'
CI_ENV_DIR = Path('codex_tmp') / 'ci_env'
SOURCE_MANIFESTS = ('downloads.ini', 'deps.ini')


def quote_command(command):
    return shlex.join(str(part) for part in command)


def make_command(command, *, cwd=ROOT):
    return {
        'command': command,
        'cwd': cwd,
    }


class FailureCollector:
    """Track failed checks so one run can report every problem at once.

    CI is fail-fast, so a red job hides every later step. Collecting failures
    locally means a single validation run surfaces the whole list instead of
    one problem per round trip.
    """

    def __init__(self, keep_going=False):
        self.keep_going = keep_going
        self.failures = []

    def record(self, label, returncode):
        self.failures.append((label, returncode))
        print(f'\nFAILED: {label}', file=sys.stderr)
        if not self.keep_going:
            self.finish()

    def finish(self):
        if not self.failures:
            return
        print(f'\n{len(self.failures)} check(s) failed:', file=sys.stderr)
        for label, returncode in self.failures:
            print(f'  - [exit {returncode}] {label}', file=sys.stderr)
        sys.exit(self.failures[0][1])


COLLECTOR = FailureCollector()


def run(command, *, cwd=ROOT):
    print(f'\n$ {quote_command(command)}', flush=True)
    result = subprocess.run([str(part) for part in command], cwd=cwd, check=False)
    if result.returncode != 0:
        COLLECTOR.record(quote_command(command), result.returncode)
    return result.returncode


def run_status(command, *, cwd=ROOT):
    print(f'\n$ {quote_command(command)}', flush=True)
    return subprocess.run([str(part) for part in command], cwd=cwd, check=False).returncode


def git_check_ignore(path):
    result = subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=ROOT, check=False)
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


def default_changed_from():
    """Pick a ref that covers committed-but-unpushed work.

    Defaulting to HEAD means a change that is already committed looks like an
    empty diff, so auto-scope selects nothing and the run reports success
    without checking anything. Comparing against the upstream merge-base keeps
    committed work in scope until it is actually pushed and validated by CI.
    """
    for upstream in ('@{upstream}', 'origin/main'):
        merge_base = git_lines(['merge-base', upstream, 'HEAD'])
        if merge_base:
            return merge_base[0]
    return 'HEAD'


def touches_any(files, predicates):
    return any(predicate(path) for path in files for predicate in predicates)


def path_under(prefix):
    prefix = prefix.rstrip('/') + '/'
    return lambda path: path.startswith(prefix)


def path_in(paths):
    return lambda path: path in paths


def patch_might_affect_i18n(path):
    if not path.startswith('patches/') or not path.endswith('.patch'):
        return False
    patch_path = ROOT / path
    if not patch_path.is_file():
        return False
    content = patch_path.read_text(encoding='utf-8')
    return '.grd' in content or '.grdp' in content


def path_is_under(path, prefix):
    path_parts = Path(path).parts
    prefix_parts = Path(prefix).parts
    return len(path_parts) >= len(prefix_parts) and path_parts[:len(prefix_parts)] == prefix_parts


def non_ignored_python_files(prefix):
    files = []
    for path in (ROOT / prefix).rglob('*.py'):
        relative_path = path.relative_to(ROOT)
        relative_path_str = str(relative_path)
        if any(path_is_under(relative_path, excluded) for excluded in PYTHON_SCAN_EXCLUDES):
            continue
        if git_check_ignore(relative_path_str):
            continue
        files.append(relative_path_str)
    return sorted(files)


def parse_system_packages():
    """Return (apt_package, binary) rows from the shared package manifest."""
    rows = []
    path = ROOT / SYSTEM_PACKAGES_FILE
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f'ERROR: {SYSTEM_PACKAGES_FILE}: expected "<package> <binary>", got {raw_line!r}',
                  file=sys.stderr)
            sys.exit(2)
        rows.append((parts[0], parts[1]))
    return rows


def check_system_tools():
    """Verify the binaries CI installs are present locally.

    Checks and tests shell out to programs such as patch and quilt. A machine
    that happens to have more tools than CI passes locally and fails remotely,
    so the required set is declared once and verified on both sides.
    """
    print('\nSystem tool checks:', flush=True)
    missing = []
    for package, binary in parse_system_packages():
        location = shutil.which(binary)
        if location:
            print(f'  - {binary} OK ({location})')
        else:
            missing.append((package, binary))
            print(f'  - {binary} MISSING (apt package: {package})')
    if missing:
        names = ', '.join(binary for _, binary in missing)
        COLLECTOR.record(f'system tools missing: {names}', 1)


def requirements_digest():
    payload = (ROOT / REQUIREMENTS_FILE).read_bytes()
    payload += (ROOT / PYTHON_VERSION_FILE).read_bytes()
    return hashlib.sha256(payload).hexdigest()


def ci_env_python(*, quiet=False):
    """Return a Python from a venv pinned to the CI requirements.

    Local tooling versions drift from .cirrus_requirements.txt, and different
    versions of yapf or pylint disagree about the same source, so "passes
    locally" stops predicting "passes on CI". Building the environment from the
    pinned manifest makes that drift structurally impossible.
    """
    env_dir = ROOT / CI_ENV_DIR
    python = env_dir / 'bin' / 'python'
    stamp = env_dir / '.requirements-digest'
    digest = requirements_digest()

    if python.is_file() and stamp.is_file() and stamp.read_text(encoding='utf-8').strip() == digest:
        if not quiet:
            print(f'Reusing pinned CI environment at {CI_ENV_DIR}', flush=True)
        return python

    wanted = (ROOT / PYTHON_VERSION_FILE).read_text(encoding='utf-8').strip()
    interpreter = shutil.which(f'python{wanted}')
    if not interpreter:
        print(
            f'ERROR: python{wanted} not found, but {PYTHON_VERSION_FILE} pins it for CI.\n'
            f'       Install it (e.g. brew install python@{wanted}) or drop --ci-env.',
            file=sys.stderr)
        sys.exit(2)

    print(f'Building pinned CI environment at {CI_ENV_DIR} (python{wanted})', flush=True)
    shutil.rmtree(env_dir, ignore_errors=True)
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    run([interpreter, '-m', 'venv', env_dir])
    run([python, '-m', 'pip', 'install', '--quiet', '--upgrade', 'pip'])
    run([python, '-m', 'pip', 'install', '--quiet', '-r', ROOT / REQUIREMENTS_FILE])
    stamp.write_text(f'{digest}\n', encoding='utf-8')
    return python


def report_version_drift(python):
    """Warn when the interpreter in use disagrees with the CI pins."""
    pins = {}
    for raw_line in (ROOT / REQUIREMENTS_FILE).read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if '==' in line:
            name, _, version = line.partition('==')
            pins[name.strip().lower()] = version.strip()
    if not pins:
        return

    script = ('import json\n'
              'from importlib.metadata import PackageNotFoundError, version\n'
              'names = json.loads(input())\n'
              'out = {}\n'
              'for name in names:\n'
              '    try:\n'
              '        out[name] = version(name)\n'
              '    except PackageNotFoundError:\n'
              '        out[name] = None\n'
              'print(json.dumps(out))\n')
    result = subprocess.run([str(python), '-c', script],
                            cwd=ROOT,
                            check=False,
                            input=json.dumps(sorted(pins)),
                            stdout=subprocess.PIPE,
                            text=True)
    if result.returncode != 0:
        return

    installed = json.loads(result.stdout)
    drift = [(name, pins[name], installed.get(name)) for name in sorted(pins)
             if installed.get(name) != pins[name]]
    if not drift:
        print('Tool versions match the CI pins.', flush=True)
        return

    print('\nWARNING: local tool versions differ from the CI pins '
          f'in {REQUIREMENTS_FILE}:',
          file=sys.stderr)
    for name, pinned, local in drift:
        print(f'  - {name}: CI pins {pinned}, local has {local or "absent"}', file=sys.stderr)
    print('         A local pass does not guarantee CI passes. '
          'Re-run with --ci-env for an exact match.',
          file=sys.stderr)


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


def pytest_check_command(python, config_path, test_path):
    config_path = Path(config_path)
    test_path = Path(test_path)
    cwd = ROOT / config_path.parent
    resolved_test_path = ROOT / test_path
    return make_command(
        [
            python,
            '-m',
            'pytest',
            '-c',
            config_path.name,
            str(resolved_test_path.relative_to(cwd)),
        ],
        cwd=cwd,
    )


def utils_checks(python):
    return [
        yapf_check_command(python, 'utils'),
        [python, './devutils/run_utils_pylint.py', '--hide-fixme'],
        pytest_check_command(python, './utils/pytest.ini', './utils/tests'),
    ]


def devutils_checks(python):
    return [
        yapf_check_command(python, 'devutils'),
        [python, './devutils/run_devutils_pylint.py', '--hide-fixme'],
        pytest_check_command(python, './devutils/pytest.ini', './devutils/tests'),
    ]


def run_commands(commands):
    for command in commands:
        if isinstance(command, dict):
            run(command['command'], cwd=command['cwd'])
        else:
            run(command)


def run_i18n_checks(python):
    with tempfile.TemporaryDirectory(prefix='helium-i18n-') as tmpdir:
        generated = Path(tmpdir) / 'source.gen.json'
        run([python, './devutils/i18n.py', 'generate', '-o', generated])
        run(['diff', '-u', './i18n/source.gen.json', generated])
    run([python, './devutils/i18n_lint.py'])


def run_skill_self_checks():
    print('\nSkill self-checks:', flush=True)
    for expected_name, relative_dir in SKILL_PATHS.items():
        skill_md = ROOT / relative_dir / 'SKILL.md'
        if not skill_md.is_file():
            print(f'ERROR: Missing {skill_md.relative_to(ROOT)}', file=sys.stderr)
            COLLECTOR.record(f'missing {skill_md.relative_to(ROOT)}', 1)
            continue

        content = skill_md.read_text(encoding='utf-8')
        if not content.startswith('---\n'):
            print(f'ERROR: {skill_md.relative_to(ROOT)} must start with YAML frontmatter.',
                  file=sys.stderr)
            COLLECTOR.record(f'{skill_md.relative_to(ROOT)} frontmatter missing', 1)
            continue
        try:
            _, frontmatter, body = content.split('---', 2)
        except ValueError:
            print(f'ERROR: {skill_md.relative_to(ROOT)} frontmatter is not closed.',
                  file=sys.stderr)
            COLLECTOR.record(f'{skill_md.relative_to(ROOT)} frontmatter unclosed', 1)
            continue

        required = {'name': False, 'description': False}
        for line in frontmatter.splitlines():
            if line.startswith('name:'):
                required['name'] = line.split(':', 1)[1].strip() == expected_name
            if line.startswith('description:'):
                required['description'] = bool(line.split(':', 1)[1].strip())
        missing = [key for key, ok in required.items() if not ok]
        if missing:
            print(
                f"ERROR: {skill_md.relative_to(ROOT)} missing/invalid frontmatter keys: "
                f"{', '.join(missing)}",
                file=sys.stderr)
            COLLECTOR.record(f"{skill_md.relative_to(ROOT)} frontmatter keys: {','.join(missing)}",
                             1)
            continue
        if '[TODO' in content:
            print(f'ERROR: {skill_md.relative_to(ROOT)} contains TODO template text.',
                  file=sys.stderr)
            COLLECTOR.record(f'{skill_md.relative_to(ROOT)} contains TODO text', 1)
            continue
        if not body.strip():
            print(f'ERROR: {skill_md.relative_to(ROOT)} body is empty.', file=sys.stderr)
            COLLECTOR.record(f'{skill_md.relative_to(ROOT)} body is empty', 1)
            continue
        print(f'  - {skill_md.relative_to(ROOT)} frontmatter/body OK')

    runner = ROOT / SKILL_PATHS['nitrous-validate'] / 'scripts' / 'run_validation.py'
    ast.parse(runner.read_text(encoding='utf-8'), filename=str(runner))
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
    if run_status(
        [python, './utils/downloads.py', 'retrieve', '-i', 'downloads.ini', '-c', cache_dir]) != 0:
        run([python, './utils/clone.py', '-o', source_tree])

    if not source_tree.is_dir():
        run([
            python, './utils/downloads.py', 'unpack', '-i', 'downloads.ini', '-c', cache_dir,
            source_tree
        ])
    run([python, './utils/downloads.py', 'unpack', '-i', 'deps.ini', '-c', cache_dir, source_tree])


def manifest_output_paths():
    """Return (manifest, component, output_path) for every declared download."""
    entries = []
    for manifest in SOURCE_MANIFESTS:
        path = ROOT / manifest
        if not path.is_file():
            continue
        parser = configparser.ConfigParser()
        parser.read(path, encoding='utf-8')
        for component in parser.sections():
            output_path = parser[component].get('output_path', fallback=None)
            if not output_path or output_path.strip() in ('', './', '.'):
                continue
            entries.append((manifest, component, output_path.strip()))
    return entries


def check_source_tree_freshness(source_tree):
    """Fail when the reusable source tree predates the current manifests.

    CI unpacks every manifest into a fresh tree on each run, while local runs
    reuse whatever is on disk. A tree that is missing a newly added dependency
    silently validates the old state and reports a pass that CI will not
    reproduce.
    """
    print('\nSource tree freshness:', flush=True)
    stale = []
    for manifest, component, output_path in manifest_output_paths():
        if (source_tree / output_path).exists():
            print(f'  - {component} OK ({output_path})')
        else:
            stale.append((manifest, component, output_path))
            print(f'  - {component} MISSING ({output_path}, from {manifest})')
    if not stale:
        return

    components = ' '.join(component for _, component, _ in stale)
    manifests = sorted({manifest for manifest, _, _ in stale})
    hint = ' '.join(f'-i {manifest}' for manifest in manifests)
    print(
        f'\nERROR: {source_tree.name} predates the current download manifests.\n'
        f'       Unpack the missing components before trusting source-backed checks:\n'
        f'       python3 utils/downloads.py unpack {hint} '
        f'-c chromium_download_cache {source_tree} --components {components}',
        file=sys.stderr)
    COLLECTOR.record(f'stale source tree: missing {components}', 1)


def run_source_checks(python, source_tree):
    check_source_tree_freshness(source_tree)
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
        path_in(I18N_TOOL_PATHS),
        path_in({'.github/workflows/lint.yml'}),
    ]) or any(patch_might_affect_i18n(path) for path in files)
    skill_touched = touches_any(files, [
        *(path_under(path) for path in SKILL_PATHS.values()),
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
    parser.add_argument(
        '--full',
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
                        help='Git ref used for auto-scope validation. Defaults to the merge-base '
                        'with the upstream branch so committed work stays in scope.')
    parser.add_argument('--keep-going',
                        action='store_true',
                        help='Run every selected check and report all failures at the end.')
    parser.add_argument('--ci-env',
                        action='store_true',
                        help=f'Run checks in a venv built from {REQUIREMENTS_FILE} using the '
                        f'{PYTHON_VERSION_FILE} interpreter, matching CI exactly.')
    parser.add_argument('--skip-system-tools',
                        action='store_true',
                        help='Skip verifying that the CI system binaries are installed.')
    parser.add_argument('--require-checks',
                        action='store_true',
                        help='Fail when auto-scope selects no checks at all. Use from delivery '
                        'gates, where validating nothing must never look like a pass.')
    parser.add_argument(
        '--python',
        default=sys.executable,
        help='Python executable for CI Python commands. Defaults to this interpreter.')
    parser.add_argument('--lint-python',
                        help='Python executable for lint.yml checks. Defaults to --python.')
    args = parser.parse_args()

    COLLECTOR.keep_going = args.keep_going

    if args.ci_env:
        pinned = ci_env_python()
        python = str(pinned)
        lint_python = args.lint_python or python
    else:
        python = args.python
        lint_python = args.lint_python or args.python
    print(f'Using Python for local CI commands: {python}', flush=True)
    print(f'Using Python for lint.yml commands: {lint_python}', flush=True)
    report_version_drift(python)

    if not args.skip_system_tools and not args.self_check_only:
        check_system_tools()

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
        changed_from = args.changed_from or default_changed_from()
        print(f'Auto-scope diff base: {changed_from}', flush=True)
        files = changed_files(changed_from)
        print_changed(files)
        commands, needs_i18n, needs_skill = selected_auto_checks(files, python, lint_python)
        if not commands and not needs_i18n and not needs_skill and not args.with_source:
            if files:
                print('\nSKIPPED: no CI-equivalent checks cover these files.')
            else:
                print(
                    '\nSKIPPED: no changes detected relative to '
                    f'{changed_from}, so nothing was validated.\n'
                    '         This is not a pass. If you expected checks to run, the diff base is '
                    'wrong:\n'
                    '         pass --changed-from <ref> explicitly, or use --full.',
                    file=sys.stderr)
                if args.require_checks:
                    COLLECTOR.record(f'no changes detected relative to {changed_from}', 1)
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

    COLLECTOR.finish()
    print('\nValidation completed successfully.')


if __name__ == '__main__':
    main()
