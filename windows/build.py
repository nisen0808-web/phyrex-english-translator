"""Reuse the hash-verified clean public runtime and replace allowlisted app sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
VERSION = '0.2.5-beta'
BASE_NAME = 'Fed-English-Translator-0.2.2-beta'
BASE_URL = 'https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.2.2-beta/Fed-English-Translator-0.2.2-beta-Windows-x64-Compact.7z'
BASE_SHA = '24b3c081b4fb9e01a7006493429c02193f4aeb9ade939901592e2be13b775725'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def manifest(root, verify=False):
    records = []
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file.name == 'manifest.sha256.json':
            continue
        rel = file.relative_to(root)
        if file.is_symlink() or any(p in {'user-data', 'data', '.codex', '__pycache__'} for p in rel.parts) or file.name in {'auth.json', 'runtime.local.json', 'server.pid', 'service.log', 'service-error.log'}:
            raise RuntimeError('Unexpected private or generated file: ' + str(rel))
        records.append({'path': rel.as_posix(), 'bytes': file.stat().st_size, 'sha256': digest(file)})
    target = root / 'manifest.sha256.json'
    if verify:
        assert records == json.loads(target.read_text(encoding='utf-8'))['files'], 'Extracted file integrity mismatch'
    else:
        target.write_text(json.dumps({'version': VERSION, 'files': records}, indent=2), encoding='utf-8')
    return len(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('dist-windows'))
    parser.add_argument('--base-archive', type=Path)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Use a Windows runner for packaging and runtime checks.')
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Use a fresh output directory.')
    output.mkdir(parents=True)
    archive = args.base_archive or output / 'base.7z'
    if args.base_archive is None:
        with urllib.request.urlopen(BASE_URL, timeout=120) as response, archive.open('wb') as target:
            shutil.copyfileobj(response, target, 1024 * 1024)
    assert digest(archive) == BASE_SHA, 'Public base runtime hash mismatch'
    seven = shutil.which('7z') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe')
    unpack = output / 'base'; unpack.mkdir()
    subprocess.run([seven, 'x', str(archive.resolve()), '-o' + str(unpack), '-y', '-bso0'], check=True)
    base = unpack / BASE_NAME
    assert base.is_dir() and {p.name for p in unpack.iterdir()} == {BASE_NAME}
    root = output / ('Fed-English-Translator-' + VERSION)
    shutil.copytree(base, root)
    suffixes = {'.py', '.json', '.js', '.css', '.html', '.cmd', '.ps1', '.md', '.txt'}
    for file in (HERE / 'app').rglob('*'):
        if not file.is_file():
            continue
        rel = file.relative_to(HERE / 'app')
        assert file.suffix.lower() in suffixes and not file.is_symlink()
        assert not any(p.startswith('.') or p in {'user-data', 'data', '__pycache__'} for p in rel.parts)
        file.read_text(encoding='utf-8')
        dest = root / rel; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest)
    python = root / '.runtime/python/python.exe'
    name = root.name + '-Windows-x64-Compact'
    subprocess.run([str(python), '-B', '-X', 'utf8', str(HERE / 'verify.py'), str(root), str(output / (name + '-checks.json'))], check=True)
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required on the build machine for release checks.')
    subprocess.run([node, '--check', str(root / 'web/app.js')], check=True)
    subprocess.run([node, str(HERE.parent / 'tests/read-aloud.cjs'), str(root / 'web/app.js'), str(output / (name + '-read-aloud-checks.json'))], check=True)
    count = manifest(root)
    package = output / (name + '.7z')
    subprocess.run([seven, 'a', str(package), root.name, '-t7z', '-mx=7', '-m0=lzma2', '-md=64m', '-mmt=2', '-bso0'], cwd=output, check=True)
    relocated = output / 'relocated verification'; relocated.mkdir()
    subprocess.run([seven, 'x', str(package), '-o' + str(relocated), '-y', '-bso0'], check=True)
    extracted = relocated / root.name
    manifest(extracted, verify=True)
    subprocess.run([str(extracted / '.runtime/python/python.exe'), '-B', '-X', 'utf8', str(HERE / 'verify.py'), str(extracted), str(output / (name + '-relocated-checks.json'))], check=True)
    checksum = digest(package)
    package.with_suffix('.7z.sha256').write_text(checksum + '  ' + package.name + '\n', encoding='ascii')
    print(json.dumps({'file': package.name, 'bytes': package.stat().st_size, 'sha256': checksum, 'manifest_files': count}), flush=True)


if __name__ == '__main__':
    main()
