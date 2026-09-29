"""Bundle fixed official CLIs. Builds never sign in or invoke an AI model."""
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'ai-sources.lock.json').read_text(encoding='utf-8'))


def download(spec, cache):
    name = spec['url'].rsplit('/', 1)[1]
    path = cache / name
    if not path.exists():
        with urllib.request.urlopen(spec['url'], timeout=120) as response, path.open('wb') as target:
            shutil.copyfileobj(response, target, 1024 * 1024)
    if 'sha256' in spec:
        expected = spec['sha256']; actual = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        algorithm, expected = spec['integrity'].split('-', 1)
        actual = base64.b64encode(hashlib.new(algorithm, path.read_bytes()).digest()).decode()
    if actual != expected:
        raise RuntimeError('Official AI component checksum mismatch: ' + name)
    return path


def bundle(root, platform, cache):
    root, cache = Path(root).resolve(), Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    specs = {'gemini': LOCK['gemini'], **LOCK['platforms'][platform]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        archives = dict(zip(specs, pool.map(lambda spec: download(spec, cache), specs.values())))
    output = root / '.runtime/ai'
    if output.exists():
        raise RuntimeError('Refusing to replace an existing AI runtime')
    output.mkdir(parents=True)
    node_dir = output / 'node'; node_dir.mkdir()
    is_windows = platform.startswith('win32')
    executable = 'node.exe' if is_windows else 'bin/node'
    if is_windows:
        with zipfile.ZipFile(archives['node']) as archive:
            for name in (executable, 'LICENSE'):
                matches = [p for p in archive.namelist() if p.split('/', 1)[-1] == name]
                assert len(matches) == 1
                (node_dir / name).write_bytes(archive.read(matches[0]))
    else:
        with tarfile.open(archives['node']) as archive:
            for name in (executable, 'LICENSE'):
                matches = [p for p in archive.getmembers() if p.isfile() and p.name.split('/', 1)[-1] == name]
                assert len(matches) == 1
                target = node_dir / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(matches[0]).read())
        (node_dir / executable).chmod(0o755)
    node = node_dir / executable
    for package in ('gemini', 'grok'):
        staging = cache / ('unpacked-' + platform + '-' + package)
        if not staging.exists():
            staging.mkdir()
            with tarfile.open(archives[package]) as archive:
                archive.extractall(staging, filter='data')
        if package == 'gemini':
            shutil.copytree(staging / 'package', output / 'gemini')
        else:
            dest = output / 'grok'; dest.mkdir()
            binary = 'grok.exe' if is_windows else 'grok'
            compressed = staging / 'package/bin' / (binary + '.br')
            if compressed.is_file():
                subprocess.run([str(node), '-e', 'const fs=require("fs"),z=require("zlib");fs.writeFileSync(process.argv[2],z.brotliDecompressSync(fs.readFileSync(process.argv[1])));', str(compressed), str(dest / binary)], check=True)
            else:
                shutil.copy2(staging / 'package/bin' / binary, dest / binary)
            if not is_windows:
                (dest / binary).chmod(0o755)
            for name in ('THIRD_PARTY_NOTICES.md', 'package.json', 'README.md'):
                shutil.copy2(staging / 'package' / name, dest / name)
    (output / 'sources.lock.json').write_text(json.dumps(LOCK, indent=2), encoding='utf-8')
    print('Bundled official AI runtimes:', platform, flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('platform', choices=LOCK['platforms'])
    parser.add_argument('cache', type=Path)
    args = parser.parse_args()
    bundle(args.root, args.platform, args.cache)
