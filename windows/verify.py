"""Run packaged Windows dependencies and loopback routes without a real account."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]).resolve()
checks = []

with tempfile.TemporaryDirectory(prefix='phyrex-windows-check-') as temporary:
    profile = (Path(temporary) / 'user-data').resolve()
    os.environ['FED_TRANSLATOR_USER_DIR'] = str(profile)
    sys.path.insert(0, str(root))
    import runtime
    runtime.prepare()
    import bridge
    import native_host
    import app
    import numpy
    import faster_whisper
    from recognizer import Recognizer
    assert Path(sys.prefix).resolve() == root / '.runtime/python'
    Recognizer().load()
    checks.append('packaged Python, speech dependencies and offline model load')
    output = subprocess.run([runtime.codex_path(), '--version'], check=True, capture_output=True, text=True).stdout
    assert '0.158.0' in output
    with patch.dict(os.environ, {'CODEX_HOME': 'publisher-account', 'OPENAI_API_KEY': 'test-placeholder', 'CODEX_API_KEY': 'test-placeholder'}):
        env = bridge.environment()
        assert Path(env['CODEX_HOME']).resolve() == (profile / 'account').resolve()
        assert 'OPENAI_API_KEY' not in env and 'CODEX_API_KEY' not in env
        assert not bridge.login_status()['ready']
    checks.append('native Codex runs; clean account ignores inherited credentials')
    extension = json.loads((root / 'extension/manifest.json').read_text(encoding='utf-8'))
    identity = ''.join(chr(97 + int(c, 16)) for c in hashlib.sha256(base64.b64decode(extension['key'])).hexdigest()[:32])
    assert identity == native_host.EXTENSION_ID and extension['version'] == '0.2.5'
    assert set(extension['permissions']) == {'sidePanel', 'nativeMessaging'}
    assert not extension.get('content_scripts') and not extension.get('host_permissions')
    checks.append('extension identity preserved; no new browser permissions')
    from http.server import ThreadingHTTPServer
    class FakeEngine:
        glossary = {}
    app.Handler.engine = FakeEngine()
    app.Handler.token = 'test-only-token'
    server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(origin + '/api/config') as response:
            config = json.load(response)
            assert config['version'] == '0.2.5-beta' and config['distribution'] == 'public'
        with opener.open(origin + '/') as response:
            page = response.read().decode('utf-8')
            assert 'readAloud' in page and '中文朗读' in page and '@PhyrexNi' in page
        with opener.open(origin + '/app.js') as response:
            assert b'PhyrexChineseReader' in response.read()
        for path, headers, body, expected in [('/api/config', {'Origin': 'https://evil.example'}, None, 403), ('/api/start', {}, b'{}', 403), ('/user-data/account/auth.json', {}, None, 404)]:
            try:
                opener.open(urllib.request.Request(origin + path, data=body, headers=headers))
            except urllib.error.HTTPError as error:
                assert error.code == expected
            else:
                raise AssertionError('Unsafe request accepted')
    finally:
        server.shutdown(); server.server_close()
    checks.append('actual loopback HTTP serves speech UI; foreign origins and private paths rejected')
    assert not list((profile / 'records').glob('*.json'))
    checks.append('fresh user profile contains no translations')
report.write_text(json.dumps({'version': '0.2.5-beta', 'checks': checks, 'not_tested': ['real account login or quota', 'browser GUI installation and YouTube live capture', 'physical speakers and OS voice availability', 'new antivirus certification']}, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(checks)}))
