"""Prepare isolated app and pinned production Python/certifi without any AI requests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

repo = Path(os.environ['GITHUB_WORKSPACE']).resolve()
work = Path(os.environ['RUNNER_TEMP']).resolve() / 'phyrex-diag-runtime'
work.mkdir(parents=True, exist_ok=False)
arch = os.environ.get('DIAG_ARCH', '')
platform = 'windows' if os.name == 'nt' else 'mac'
app = work / 'app'
shutil.copytree(repo / platform / 'app', app, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
runtime = app / '.runtime'
runtime.mkdir()

def fetch(url, sha, target):
    # Fixed project release / source-lock URL only; never AI API, key, or prompt.
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Phyrex-local-diagnostic'}), timeout=180) as response, target.open('wb') as f:
        shutil.copyfileobj(response, f, 1024 * 1024)
    with target.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != sha:
        raise RuntimeError(f'Pinned artifact digest mismatch: {target.name}')
    print('artifact-sha256-ok:', target.name, actual, flush=True)

lock = json.loads((repo / 'mac/sources.lock.json').read_text(encoding='utf-8'))
certspec = next(x for x in lock['architectures']['arm64']['wheels'] if x['package'] == 'certifi')
portable = None
if os.name == 'nt':
    url = 'https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.2.2-beta/Fed-English-Translator-0.2.2-beta-Windows-x64-Compact.7z'
    sha = '24b3c081b4fb9e01a7006493429c02193f4aeb9ade939901592e2be13b775725'
    archive = work / 'base.7z'
    fetch(url, sha, archive)
    extracted = work / 'extracted'
    extracted.mkdir()
    seven = shutil.which('7z') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe')
    subprocess.run([seven, 'x', str(archive), '-o' + str(extracted), '-y', '-bso0'], check=True)
    old = extracted / 'Fed-English-Translator-0.2.2-beta' / '.runtime'
    shutil.copytree(old / 'python', runtime / 'python')
    (runtime / 'packages').mkdir()
    shutil.copytree(old / 'packages/certifi', runtime / 'packages/certifi')
    portable = runtime / 'python/python.exe'
elif sys.platform == 'darwin':
    spec = lock['architectures'][arch]['python']
    archive = work / 'python.tar.gz'
    fetch(spec['url'], spec['sha256'], archive)
    with tarfile.open(archive) as tf:
        tf.extractall(runtime, filter='data')
    portable = runtime / 'python/bin/python3'

# On Linux this exact fixed wheel supplies certifi to source-only diagnostics;
# on Mac it reproduces the package bytes from sources.lock for both interpreters.
if os.name != 'nt':
    wheel = work / 'certifi.whl'
    fetch(certspec['url'], certspec['sha256'], wheel)
    packages = runtime / 'packages'
    packages.mkdir()
    with zipfile.ZipFile(wheel) as z:
        for item in z.infolist():
            path = Path(item.filename)
            if path.parts and path.parts[0] == 'certifi':
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError('Unsafe wheel entry')
                z.extract(item, packages)
if portable and not portable.is_file():
    raise RuntimeError('Portable interpreter is missing')
record = {'app': str(app), 'portable_python': str(portable) if portable else None,
          'source_python': sys.executable, 'platform': platform, 'arch': arch,
          'dependency_scope': 'fixed upstream files, SHA-256 verified; no DeepSeek API requests'}
(work / 'paths.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print('PREPARED_PATHS=' + json.dumps(record), flush=True)

