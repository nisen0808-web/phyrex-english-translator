"""Build portable Mac packages from fixed, hashed upstream artifacts on a Mac runner."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
from urllib.parse import urlparse, unquote

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'sources.lock.json').read_text(encoding='utf-8'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(spec, cache):
    name = spec.get('name') or unquote(Path(urlparse(spec['url']).path).name)
    path = cache / (spec['sha256'][:12] + '-' + name)
    if path.is_file() and digest(path) == spec['sha256']:
        return path
    for attempt in range(3):
        try:
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'PhyrexNi-Mac-build'})
            with urllib.request.urlopen(request, timeout=90) as response, path.open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
            if digest(path) != spec['sha256']:
                raise RuntimeError('Download digest mismatch: ' + name)
            return path
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def command(args, **kwargs):
    print('Running:', str(args[0]), str(args[1]) if len(args) > 1 else '', flush=True)
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def manifest(root):
    files = []
    forbidden = {'auth.json', 'runtime.local.json', 'server.pid', 'service.log', 'service-error.log'}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if relative.parts[0] in {'user-data', '.git', '.codex'} or path.name in forbidden:
            raise RuntimeError('Private runtime data in package: ' + str(relative))
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise RuntimeError('External symlink in package: ' + str(relative))
            files.append({'path': relative.as_posix(), 'symlink': os.readlink(path)})
        elif path.is_file() and path.name != 'manifest.sha256.json':
            files.append({'path': relative.as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (root / 'manifest.sha256.json').write_text(json.dumps({'version': LOCK['version'], 'files': files}, indent=2), encoding='utf-8')
    return len(files)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=LOCK['architectures'], required=True)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != args.arch:
        raise SystemExit('Build and validate on the matching native Mac runner.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'cache'
    cache.mkdir(exist_ok=True)
    name = 'Fed-English-Translator-' + LOCK['version'] + '-macOS-' + args.arch
    root = output / name
    if root.exists():
        raise SystemExit('Use a fresh output directory; refusing to package prior user data.')
    shutil.copytree(HERE / 'app', root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    runtime = root / '.runtime'
    runtime.mkdir()
    spec = LOCK['architectures'][args.arch]
    artifacts = [spec['python'], spec['codex'], *LOCK['model'], *spec['wheels']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        downloaded = dict(zip([item['sha256'] for item in artifacts], pool.map(lambda item: fetch(item, cache), artifacts)))
    with tarfile.open(downloaded[spec['python']['sha256']]) as archive:
        archive.extractall(runtime, filter='data')
    python = runtime / 'python/bin/python3'
    if not python.is_file():
        raise RuntimeError('Unexpected portable Python layout')
    codex_dir = runtime / 'codex'
    codex_dir.mkdir()
    with tarfile.open(downloaded[spec['codex']['sha256']]) as archive:
        archive.extractall(codex_dir, filter='data')
    if not (codex_dir / 'codex').is_file():
        candidates = [p for p in codex_dir.rglob('*') if p.is_file() and p.name in {'codex', 'codex-aarch64-apple-darwin', 'codex-x86_64-apple-darwin'}]
        if len(candidates) != 1:
            raise RuntimeError('Unexpected Codex package layout')
        (codex_dir / 'codex').symlink_to(candidates[0].relative_to(codex_dir))
    wheelhouse = output / 'wheels'
    wheelhouse.mkdir(exist_ok=True)
    wheels = []
    for wheel in spec['wheels']:
        filename = unquote(Path(urlparse(wheel['url']).path).name)
        target = wheelhouse / filename
        shutil.copy2(downloaded[wheel['sha256']], target)
        wheels.append(target)
    command([python, '-E', '-s', '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', '--target', runtime / 'packages', *wheels])
    # Wheel-generated entrypoint scripts contain temporary build paths and are unused.
    generated_bin = runtime / 'packages/bin'
    if generated_bin.is_dir():
        shutil.rmtree(generated_bin)
    model = runtime / 'model'
    model.mkdir()
    for item in LOCK['model']:
        shutil.copy2(downloaded[item['sha256']], model / item['name'])
    for file in root.glob('*.command'):
        file.chmod(0o755)
    (root / 'NativeHost.sh').chmod(0o755)
    info = {'version': LOCK['version'], 'architecture': args.arch, 'minimum_macos': LOCK['minimum_macos'],
            'python': spec['python']['name'], 'codex': '0.158.0', 'model_revision': LOCK['model_revision']}
    (root / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    shutil.copy2(HERE / 'sources.lock.json', root / 'sources.lock.json')
    report_path = output / (name + '-checks.json')
    # Tests use an independent temporary home and never log into a real account.
    command([python, '-B', '-E', '-s', HERE / 'verify.py', root, report_path])
    command(['node', '--check', root / 'web/app.js'])
    command(['node', HERE.parent / 'tests/read-aloud.cjs', root / 'web/app.js', output / (name + '-read-aloud-checks.json')])
    count = manifest(root)
    zip_path = output / (name + '.zip')
    command(['/usr/bin/ditto', '-c', '-k', '--keepParent', root, zip_path])
    # Archive Utility uses ditto-compatible metadata, including executable bits and symlinks.
    relocated_parent = output / 'relocated verification'
    relocated_parent.mkdir()
    command(['/usr/bin/ditto', '-x', '-k', zip_path, relocated_parent])
    relocated = relocated_parent / name
    command([relocated / '.runtime/python/bin/python3', '-B', '-E', '-s', HERE / 'verify.py', relocated, output / (name + '-relocated-checks.json')])
    archive_hash = digest(zip_path)
    (output / (name + '.zip.sha256')).write_text(archive_hash + '  ' + zip_path.name + '\n', encoding='ascii')
    print(json.dumps({'file': zip_path.name, 'bytes': zip_path.stat().st_size, 'sha256': archive_hash, 'manifest_entries': count}), flush=True)


if __name__ == '__main__':
    main()
