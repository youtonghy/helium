#!/usr/bin/env python3
"""Capture and verify hot-tree state before exporting a new top patch."""

import hashlib
import difflib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ExportError(RuntimeError):
    """Raised when a hot-tree export invariant is not satisfied."""


@dataclass(frozen=True)
class ExportContext:
    """Filesystem boundaries for one hot-tree export session."""

    root: Path
    hot_tree: Path
    merged_queue: Path
    session_dir: Path


def _read_series(queue_dir):
    series_path = queue_dir / 'series'
    if not series_path.is_file():
        raise ExportError(f'patch queue has no series file: {series_path}')
    entries = []
    for line in series_path.read_text(encoding='utf-8').splitlines():
        entry = line.split('#', 1)[0].strip()
        if entry:
            entries.append(entry)
    return entries


def queue_fingerprint(queue_dir):
    """Return a stable digest of a patch series and every listed patch."""
    digest = hashlib.sha256()
    for entry in _read_series(queue_dir):
        patch_path = queue_dir / entry
        if not patch_path.is_file():
            raise ExportError(f'patch listed in series is missing: {patch_path}')
        digest.update(entry.encode('utf-8'))
        digest.update(b'\0')
        digest.update(patch_path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def validate_hot_tree(hot_tree, merged_queue):
    """Require a readable hot tree with the complete current queue applied."""
    metadata_dir = hot_tree / '.pc'
    patches_file = metadata_dir / '.quilt_patches'
    series_file = metadata_dir / '.quilt_series'
    applied_file = metadata_dir / 'applied-patches'
    for path in (patches_file, series_file, applied_file):
        if not path.is_file():
            raise ExportError(f'hot tree has incomplete quilt metadata: {path}')

    recorded_queue = Path(patches_file.read_text(encoding='utf-8').strip())
    if recorded_queue.resolve() != merged_queue.resolve():
        raise ExportError(
            f'hot-tree quilt patch path is stale: {recorded_queue}; expected {merged_queue}')
    if series_file.read_text(encoding='utf-8').strip() != 'series':
        raise ExportError('hot-tree quilt series name is not "series"')

    expected = _read_series(merged_queue)
    applied = [
        line.strip() for line in applied_file.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    if applied != expected:
        raise ExportError('hot tree does not have the current merged queue fully applied')
    return expected


def _validate_relative_path(value, *, label):
    if not value or '\\' in value:
        raise ExportError(f'invalid {label}: {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '.' in path.parts:
        raise ExportError(f'invalid {label}: {value!r}')
    return path


def _file_state(path):
    if not path.exists() and not path.is_symlink():
        return {'kind': 'missing'}
    if path.is_symlink() or not path.is_file():
        raise ExportError(f'hot export supports regular files only: {path}')
    mode = stat.S_IMODE(path.stat().st_mode)
    return {
        'kind': 'file',
        'mode': mode,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def start_session(context, patch, files):
    """Record the pre-edit file states and patch-queue identity."""
    validate_hot_tree(context.hot_tree, context.merged_queue)
    patch_path = _validate_relative_path(patch, label='patch path')
    if patch_path.suffix != '.patch':
        raise ExportError('hot export patch name must end in .patch')
    if (context.root / 'patches' / Path(*patch_path.parts)).exists():
        raise ExportError(f'patch already exists: {patch}')

    normalized_files = sorted(
        {str(_validate_relative_path(value, label='source path'))
         for value in files})
    if not normalized_files:
        raise ExportError('hot-start requires at least one --file')
    if context.session_dir.exists():
        raise ExportError(f'hot export session already exists: {context.session_dir}')

    baseline_dir = context.session_dir / 'baseline'
    baseline_dir.mkdir(parents=True)
    manifest_files = []
    try:
        for relative in normalized_files:
            source_path = context.hot_tree / relative
            state = {'path': relative, **_file_state(source_path)}
            manifest_files.append(state)
            if state['kind'] == 'file':
                baseline_path = baseline_dir / relative
                baseline_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, baseline_path)

        manifest = {
            'version': 1,
            'patch': str(patch_path),
            'queue_sha256': queue_fingerprint(context.merged_queue),
            'root_queue_sha256': queue_fingerprint(context.root / 'patches'),
            'files': manifest_files,
        }
        manifest_path = context.session_dir / 'manifest.json'
        temp_path = context.session_dir / 'manifest.json.tmp'
        temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                             encoding='utf-8')
        os.replace(temp_path, manifest_path)
        return manifest_path
    except Exception:
        shutil.rmtree(context.session_dir, ignore_errors=True)
        raise


def _load_manifest(session_dir):
    manifest_path = session_dir / 'manifest.json'
    if not manifest_path.is_file():
        raise ExportError(f'no hot export session found at {session_dir}')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ExportError(f'invalid hot export manifest: {error}') from error
    if manifest.get('version') != 1:
        raise ExportError('unsupported hot export manifest version')
    return manifest


def _write_manifest(session_dir, manifest):
    manifest_path = session_dir / 'manifest.json'
    temp_path = session_dir / 'manifest.json.tmp'
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temp_path, manifest_path)


def verify_session(context):
    """Verify the queue is unchanged and return declared hot-tree changes."""
    validate_hot_tree(context.hot_tree, context.merged_queue)
    manifest = _load_manifest(context.session_dir)
    if manifest.get('queue_sha256') != queue_fingerprint(context.merged_queue):
        raise ExportError('merged patch queue changed after hot-start; abort and restart')
    if manifest.get('root_queue_sha256') != queue_fingerprint(context.root / 'patches'):
        raise ExportError('root patch queue changed after hot-start; abort and restart')

    changed = []
    for baseline in manifest['files']:
        current = _file_state(context.hot_tree / baseline['path'])
        if current != {key: value for key, value in baseline.items() if key != 'path'}:
            changed.append(baseline['path'])
    if not changed:
        raise ExportError('no declared files changed after hot-start')
    return manifest, tuple(changed)


def add_session_files(context, files):
    """Extend an active session with additional pre-edit file baselines."""
    validate_hot_tree(context.hot_tree, context.merged_queue)
    manifest = _load_manifest(context.session_dir)
    if manifest.get('queue_sha256') != queue_fingerprint(context.merged_queue):
        raise ExportError('merged patch queue changed after hot-start; abort and restart')
    if manifest.get('root_queue_sha256') != queue_fingerprint(context.root / 'patches'):
        raise ExportError('root patch queue changed after hot-start; abort and restart')

    existing = {entry['path'] for entry in manifest['files']}
    additions = sorted(
        {str(_validate_relative_path(value, label='source path'))
         for value in files} - existing)
    if not additions:
        raise ExportError('hot-add requires at least one new --file')

    baseline_dir = context.session_dir / 'baseline'
    new_entries = []
    for relative in additions:
        source_path = context.hot_tree / relative
        state = {'path': relative, **_file_state(source_path)}
        new_entries.append(state)
        if state['kind'] == 'file':
            baseline_path = baseline_dir / relative
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, baseline_path)
    manifest['files'] = sorted([*manifest['files'], *new_entries], key=lambda entry: entry['path'])
    _write_manifest(context.session_dir, manifest)
    return tuple(additions)


def _run_quilt(source_tree, patches_dir, *args):
    env = os.environ.copy()
    env.update({
        'LC_ALL': 'C',
        'QUILT_PATCHES': str(patches_dir.resolve()),
        'QUILT_SERIES': 'series',
        'QUILT_PATCH_OPTS': '--unified --reject-format=unified',
        'QUILT_DIFF_ARGS': '-p ab --no-timestamps --no-index',
        'QUILT_REFRESH_ARGS': '-p ab --no-timestamps --no-index --strip-trailing-whitespace',
    })
    command = ['quilt', '--quiltrc', '-', *args]
    result = subprocess.run(command,
                            cwd=source_tree,
                            env=env,
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True)
    if result.returncode != 0:
        raise ExportError(f'quilt command failed ({result.returncode}): '
                          f'{" ".join(command)}\n{result.stdout.rstrip()}')
    return result.stdout.strip()


def _manifest_state(entry):
    return {key: value for key, value in entry.items() if key != 'path'}


def _assert_state(path, expected, message):
    actual = _file_state(path)
    if actual != expected:
        raise ExportError(f'{message}: {path}')


def _apply_hot_delta(root_path, baseline_path, hot_path):
    """Apply only the captured hot-tree edit to a root-stack source file."""
    baseline = baseline_path.read_bytes()
    current = hot_path.read_bytes()
    delta = b''.join(
        difflib.diff_bytes(difflib.unified_diff,
                           baseline.splitlines(keepends=True),
                           current.splitlines(keepends=True),
                           fromfile=b'baseline',
                           tofile=b'hot-tree',
                           n=3))
    if not delta:
        return

    command = [
        'patch', '--batch', '--forward', '--silent', '--fuzz=0', '--no-backup-if-mismatch',
        str(root_path)
    ]
    dry_run = subprocess.run([*command, '--dry-run'],
                             input=delta,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             check=False)
    if dry_run.returncode != 0:
        raise ExportError('hot-tree delta does not apply cleanly to root baseline: '
                          f'{root_path}\n{dry_run.stdout.decode(errors="replace").rstrip()}')
    subprocess.run(command,
                   input=delta,
                   check=True,
                   stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT)


def _validate_generated_patch(patch_path):
    content = patch_path.read_text(encoding='utf-8')
    if not content.strip():
        raise ExportError(f'generated patch is empty: {patch_path}')
    for line in content.splitlines():
        if line.startswith('Index:'):
            raise ExportError(f'generated patch contains Index metadata: {patch_path}')
        if line.startswith('--- ') and not line.startswith(('--- a/', '--- /dev/null')):
            raise ExportError(f'generated patch has unstable source path: {line}')
        if line.startswith('+++ ') and not line.startswith(('+++ b/', '+++ /dev/null')):
            raise ExportError(f'generated patch has unstable target path: {line}')


def stage_session(context, patchwork_tree):
    """Generate and replay a new top patch in an isolated staging queue."""
    manifest, changed = verify_session(context)
    staged_queue = context.session_dir / 'staged-patches'
    if staged_queue.exists():
        raise ExportError(f'staged patch queue already exists: {staged_queue}')
    shutil.copytree(context.root / 'patches', staged_queue)

    _run_quilt(patchwork_tree, staged_queue, 'push', '-a')

    patch = manifest['patch']
    (staged_queue / patch).parent.mkdir(parents=True, exist_ok=True)
    _run_quilt(patchwork_tree, staged_queue, 'new', patch)
    replay_states = {}
    for relative in changed:
        _run_quilt(patchwork_tree, staged_queue, 'add', relative)
        hot_path = context.hot_tree / relative
        patchwork_path = patchwork_tree / relative
        baseline_path = context.session_dir / 'baseline' / relative
        baseline_entry = next(entry for entry in manifest['files'] if entry['path'] == relative)
        current = _file_state(hot_path)
        if current['kind'] == 'missing':
            _assert_state(patchwork_path, _manifest_state(baseline_entry),
                          'cannot delete a file changed by a later platform layer')
            patchwork_path.unlink()
        elif baseline_entry['kind'] == 'missing':
            _assert_state(patchwork_path, {'kind': 'missing'},
                          'new hot-tree file already exists in root baseline')
            patchwork_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hot_path, patchwork_path)
        else:
            _apply_hot_delta(patchwork_path, baseline_path, hot_path)
            if current['mode'] != baseline_entry['mode']:
                patchwork_path.chmod(current['mode'])
        replay_states[relative] = _file_state(patchwork_path)

    top = _run_quilt(patchwork_tree, staged_queue, 'top')
    if top != patch:
        raise ExportError(f'quilt top is {top}; expected {patch}')
    _run_quilt(patchwork_tree, staged_queue, 'refresh', patch)
    _validate_generated_patch(staged_queue / patch)

    _run_quilt(patchwork_tree, staged_queue, 'pop')
    _run_quilt(patchwork_tree, staged_queue, 'push', patch)
    for relative in changed:
        _assert_state(patchwork_tree / relative, replay_states[relative],
                      'replayed patch does not reproduce the hot-tree file')
    return staged_queue


def publish_staged_patch(context, staged_queue):
    """Publish a verified staged patch, placing the series update last."""
    manifest = _load_manifest(context.session_dir)
    live_queue = context.root / 'patches'
    if manifest.get('root_queue_sha256') != queue_fingerprint(live_queue):
        raise ExportError('root patch queue changed before publish; abort and restart')

    patch = manifest['patch']
    destination = live_queue / patch
    if destination.exists():
        raise ExportError(f'patch already exists: {patch}')
    staged_patch = staged_queue / patch
    _validate_generated_patch(staged_patch)
    expected_series = [*_read_series(live_queue), patch]
    if _read_series(staged_queue) != expected_series:
        raise ExportError('staged series contains unexpected changes')

    destination.parent.mkdir(parents=True, exist_ok=True)
    patch_temp = destination.with_suffix(destination.suffix + '.tmp')
    series_temp = live_queue / 'series.tmp'
    try:
        shutil.copy2(staged_patch, patch_temp)
        os.replace(patch_temp, destination)
        shutil.copy2(staged_queue / 'series', series_temp)
        os.replace(series_temp, live_queue / 'series')
    except Exception:
        patch_temp.unlink(missing_ok=True)
        series_temp.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    shutil.rmtree(context.session_dir)
