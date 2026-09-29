"""Native Mac smoke/security tests; does not claim a real-user browser/login test."""
import io
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
report_path = Path(sys.argv[2]).resolve()
results = {'platform': platform.platform(), 'architecture': platform.machine(), 'checks': [],
           'not_tested': ['Chrome/Edge GUI extension installation', 'Gatekeeper approval and Apple notarization',
                          'real account login and paid quota', 'real YouTube audio capture and long livestream',
                          'Mac antivirus certification']}


def passed(name):
    results['checks'].append(name)
    print('PASS ' + name, flush=True)


with tempfile.TemporaryDirectory(prefix='phyrex-mac-check-') as scratch:
    temporary = Path(scratch).resolve()
    os.environ['FED_TRANSLATOR_USER_DIR'] = str(temporary / 'user-data')
    sys.path.insert(0, str(root))
    import runtime
    runtime.prepare()
    import bridge
    import native_host
    import mac_launcher
    import app
    import numpy as np
    import onnxruntime
    import ctranslate2
    import av

    assert Path(runtime.python_path()).is_file()
    assert Path(sys.prefix).resolve().is_relative_to(root / '.runtime/python'), sys.prefix
    results['portable_python_version'] = platform.python_version()
    assert len(json.loads((root / 'glossary.json').read_text(encoding='utf-8'))) == 556
    passed('portable Python and speech dependencies load; 556 glossary entries')
    version = subprocess.run([runtime.codex_path(), '--version'], capture_output=True, text=True, check=True).stdout.strip()
    assert '0.158.0' in version, version
    help_output = subprocess.run([runtime.codex_path(), 'exec', '--help'], capture_output=True, text=True, check=True).stdout
    assert '--ephemeral' in help_output and '--output-schema' in help_output
    passed('native Codex CLI runs with required command options')
    results['codex_version'] = version
    with patch.dict(os.environ, {'CODEX_HOME': '/publisher-account', 'OPENAI_API_KEY': 'test-placeholder'}):
        env = bridge.environment()
    assert env['CODEX_HOME'] == str(temporary / 'user-data/account')
    assert 'OPENAI_API_KEY' not in env
    status = bridge.login_status()
    assert status['ready'] is False
    passed('fresh account is logged out and does not inherit publisher credentials')

    with patch.object(native_host, 'ensure_service') as start:
        assert not native_host.dispatch({'command': 'exec'})['ok']
        start.assert_not_called()
    wire = io.BytesIO()
    native_host.write_message(wire, {'ok': True, 'message': '译文'})
    wire.seek(0)
    assert native_host.read_message(wire)['message'] == '译文'
    for content in (struct.pack('<I', 20000), b'\x01'):
        try:
            native_host.read_message(io.BytesIO(content))
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid native message accepted')
    manifest = json.loads((root / 'extension/manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['permissions']) == {'sidePanel', 'nativeMessaging'}
    assert not manifest.get('host_permissions') and not manifest.get('content_scripts')
    passed('native protocol, command allowlist and minimal extension permissions')

    mock_home = temporary / 'test home with spaces'
    mac_launcher.install(mock_home)
    for file in mac_launcher.manifest_paths(mock_home):
        item = json.loads(file.read_text(encoding='utf-8'))
        assert item['path'] == str(root / 'NativeHost.sh')
        assert item['allowed_origins'] == [mac_launcher.EXTENSION]
    mac_launcher.uninstall(mock_home)
    assert not any(p.exists() for p in mac_launcher.manifest_paths(mock_home))
    passed('Chrome and Edge manifest install/uninstall in isolated user home')

    import fcntl
    lock = runtime.acquire_instance_lock()
    try:
        runtime.acquire_instance_lock()
    except SystemExit:
        pass
    else:
        raise AssertionError('Duplicate instance accepted')
    lock.close()
    passed('per-copy process lock rejects duplicate service')

    from http.server import ThreadingHTTPServer
    app.Handler.token = 'test-placeholder-token'
    class FakeEngine:
        glossary = {}
    app.Handler.engine = FakeEngine()
    server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = 'http://127.0.0.1:' + str(server.server_port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/api/config') as response:
            assert json.load(response)['version'] == '0.2.3-mac-beta'
        with opener.open(url + '/') as response:
            assert b'@PhyrexNi' in response.read()
            assert 'chrome-extension://' in response.headers['Content-Security-Policy']
        cases = [('/api/config', {'Host': 'attacker.example'}, None, 403),
                 ('/api/config', {'Origin': 'https://attacker.example'}, None, 403),
                 ('/api/start', {}, b'{}', 403),
                 ('/user-data/account/auth.json', {}, None, 404),
                 ('/../bridge.py', {}, None, 404)]
        for path, headers, body, expected in cases:
            try:
                opener.open(urllib.request.Request(url + path, headers=headers, data=body))
            except urllib.error.HTTPError as error:
                assert error.code == expected, (path, error.code)
            else:
                raise AssertionError('Unsafe request accepted: ' + path)
    finally:
        server.shutdown()
        server.server_close()
    passed('actual loopback HTTP routes, origin checks, write token and private path rejection')

    from recognizer import Recognizer
    from faster_whisper.audio import decode_audio
    audio_path = temporary / 'speech.aiff'
    subprocess.run(['/usr/bin/say', '-r', '145', '-o', str(audio_path),
                    'The Federal Reserve will assess inflation and conditions in the labor market. The federal funds rate remains unchanged.'], check=True)
    pcm = (decode_audio(str(audio_path), sampling_rate=16000) * 32767).astype('<i2').tobytes()
    recognizer = Recognizer()
    recognizer.load()
    text, _, _, _, _ = recognizer.transcribe(pcm, b'', '', {}, 'fed')
    assert text and any(word in text.lower() for word in ('federal', 'inflation', 'market')), text
    results['speech_test'] = {'source': 'macOS built-in synthetic English voice; not real Fed audio', 'recognized_words': len(text.split())}
    passed('offline Whisper small model loads and recognizes synthesized English speech')

    for script in [*root.glob('*.command'), root / 'NativeHost.sh']:
        subprocess.run(['/bin/bash', '-n', str(script)], check=True)
        assert os.access(script, os.X_OK), str(script)
    process = subprocess.run([str(root / 'NativeHost.sh'), 'chrome-extension://invalid/'], capture_output=True)
    assert process.returncode == 1 and not process.stdout
    passed('executable launch scripts and native host reject unauthorized extension')

report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
