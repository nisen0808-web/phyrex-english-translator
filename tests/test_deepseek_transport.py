"""Real local child processes and a local mock HTTP server, never DeepSeek."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.request import Request

import bridge
import deepseek_api as api
import deepseek_transport as transport
import app
import providers
import certifi

KEY = 'sk-local-fixture-not-a-real-key-12345'
BODY = b'{"prompt":"local fixture"}'


def _stage_certifi(packages, source, *, require_packaged, is_linux):
    """Copy native certifi unchanged, or isolate an external Linux system CA."""
    source_file = getattr(source, '__file__', None)
    source_root = Path(source_file).resolve().parent if source_file else None
    source_ca = Path(source.where()).resolve()
    external_ca = source_root is None or not source_ca.is_relative_to(source_root)
    target = packages / 'certifi'
    if is_linux and not require_packaged and external_ca:
        target.mkdir()
        shutil.copyfile(source_ca, target / 'cacert.pem')
        (target / '__init__.py').write_text(
            'from pathlib import Path\ndef where():\n return str(Path(__file__).with_name("cacert.pem"))\n',
            encoding='utf-8')
        return 'isolated-system-ca'
    if source_root is None:
        raise RuntimeError('A native test must use the actual packaged certifi module.')
    shutil.copytree(source_root, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return 'copied-package'
# Public, throwaway self-signed localhost certificate.  This key is only a
# deterministic test fixture; it is not a user credential or deployment key.
TEST_CERT = "-----BEGIN CERTIFICATE-----\nMIIDJTCCAg2gAwIBAgIUDYSfcFuHHptJnEaltUsqZYZ6q+4wDQYJKoZIhvcNAQEL\nBQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI2MTAyNzEyNDUzN1oXDTM2MTAy\nNDEyNDUzN1owFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF\nAAOCAQ8AMIIBCgKCAQEAvrFzy+FZpagUYhqKKSj5h8ARYKeBG/bJI9bWNRKuCYKO\nyLfJv/MVsKy87o6HiqqaRArKCINp/Mn0oKmir+gQ0WGwiEJXoYSIznzvtkU52Is3\nyXqnguf7RSqcOr9HJySTPU7jbl0U5/yJ7BG+3GoZmNvE0fV+wVMsEQMec6cJwXfo\nbGT+1js9LvmBvX2C5QYC1dIPz5/n/5INy0iYgq//WaF3nj0Qr8wvGjQftPudivFM\nsjVMwCOQqslLzzakQ2K3mIY+/MCkDKymoWOK33i0rUOggqBfbViPjInUTdt9oC7s\n+Y6T7aZahyiZ3DtjwKyDgvyDGflU3e+WDQ6ypk3ZqwIDAQABo28wbTAdBgNVHQ4E\nFgQUnaa6ETUCnfl5SQU4iiLS3Kw51lAwHwYDVR0jBBgwFoAUnaa6ETUCnfl5SQU4\niiLS3Kw51lAwDwYDVR0TAQH/BAUwAwEB/zAaBgNVHREEEzARgglsb2NhbGhvc3SH\nBH8AAAEwDQYJKoZIhvcNAQELBQADggEBAD0F5osWQLIzP3jyMXsv7czNYXbsaxUJ\n42YsdTksZa9YkHj2M4XvEB1TuWYtYPy0jV3owTt6Asf24IZ0B7uIztYqSg6dplf2\njapxlv0KcJqStAMXzFhndacekYetuRjBRucVDokMBY250nKOloQ+Hh28ADLdz8eY\nCNZ8MICqlAvNduuee3xV4HOSAuKoSI1yll8mNEON9s8mQ8namF9Wh4h4om8QRCXi\nrBt2mzpMiefmNVdkk9FvyYA2gYYVv7uPV1iBSkIV4RdO60U4fhCBiziqLo7+EIaI\n4beENoUj3aH43NVWgg6SWOra/li49I15dgBAvFRVQmeaZD5xLkrVMFM=\n-----END CERTIFICATE-----\n\r\n"
TEST_KEY = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC+sXPL4VmlqBRi\nGoopKPmHwBFgp4Eb9skj1tY1Eq4Jgo7It8m/8xWwrLzujoeKqppECsoIg2n8yfSg\nqaKv6BDRYbCIQlehhIjOfO+2RTnYizfJeqeC5/tFKpw6v0cnJJM9TuNuXRTn/Ins\nEb7cahmY28TR9X7BUywRAx5zpwnBd+hsZP7WOz0u+YG9fYLlBgLV0g/Pn+f/kg3L\nSJiCr/9ZoXeePRCvzC8aNB+0+52K8UyyNUzAI5CqyUvPNqRDYreYhj78wKQMrKah\nY4rfeLStQ6CCoF9tWI+MidRN232gLuz5jpPtplqHKJncO2PArIOC/IMZ+VTd75YN\nDrKmTdmrAgMBAAECggEAU+U8XclyKGiPNy4X9M3bIndE7fIj4kqr6YGeUlE6kmKH\nMRVyxGlM9KK6qHW6ei5emmroweAXJCkx3/Fh6uQ9afEBuqD9bskhaz8aM2W3cmal\nj5XP1s77BE4f19TJmBYGVWW8t5RqGzpG775K6ywewNqHeBv6vVE7ROzLW/R0XVIB\ndWiWpVEmsLoBkRo8X9ZhSf5+cplxFrbMCJ3GKYad6Y89ipWWFt4z9+KleR3JtUkO\n44J1ZcOoIYMuFEOonUYehOjHTvk591fRkttEJzii1vp+b/6DMNPTIBM14QDZrB/P\nVYZH+uBQ6eTD9D8AVtZGNKjWmZjSFqu8bSe2v3Y92QKBgQDzS3xBjQ4MhpvrYdIz\nUye8bNtVzH812FqmmuRmebZppYHvXxD2QS389YUdQip5/0UxOL/bBYem1JIKsyoO\nPZpLg6K66+glrgBzZLn8R+ng2riCkX6S2eecD7T6HQmWItWOsS+EV5PLvqqNNvTe\nBZblDPB4mqZjJfOTm9gc6nPgFQKBgQDIpsFe5aXel8GV8Jf3/5Wwvz/CTdoaoK2i\nYTeXO2PnTCSngqGyI4BdZkz+hrY6oS255G9xbNJ3FjX6u6DuxBUwfMaj7wfhPzwr\nVDODr0QV+y2n6a7oKwAxHZz2EWaLs6NeSeJWS39eRuI8+OwYqoUruNmgF0nR1vkB\n9rih3pOCvwKBgQDtWfce/D14etoiCIzJBZb+fDR+v8JbBXdqkjHAx3zuFElu/Y/O\nrkfvQJdcs/A8lI0sN/Dz+7EbUMYpKiEdQ3wDr6hSM1OHbvmBmgLX3FCOzNK0jryt\nB2itF6W3XBy+G728N5/jvIyzeI9qtPKup0VOsBDpl/Y7RAsdNizgCNqDAQKBgDBO\nhUt1emOGoaKZk9yu+bjdslnzKEk02di4Ewwjzj+HQ2PYvVkH1wWldW/pusGOwFV6\nu6HREzJ8dG5y8aHKL1fHEoOxLnJ6KOA9m1FexsOL/0fnqKZYg+lPOdS8B7Ymf3RZ\n0VX5QybNZfZL73tYwkrua+Zw9OLCIJzqazT9QwI9AoGAWsUXeKcAYFOxip7DmhbC\nSX6c8UU8dsvX/F7SCzwZml8/1tO03UMaqCgDIqWXx1u8x4bmTJvpyc7tF/t7Y66o\ntdj1wrTzkzh4QDyVMGwQEE9F4gc6WVuhFXh5qJuDTDR6r9E4iVP+OaQuS0n32hEz\nVd0iSjTEjea4gUt1W2JxNwA=\n-----END PRIVATE KEY-----\n\r\n"


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.server.calls += 1
        self.server.entered.set()
        if self.server.mode == 'headers':
            self.server.stop.wait(4)
            return
        if self.server.mode == 'unauthorized':
            self.send_response(401)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if self.server.mode == 'normal':
            body = b'{"local":"ok"}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header('Content-Length', str(api.MAX_RESPONSE_BYTES + 10))
        self.end_headers()
        if self.server.mode == 'large':
            self.wfile.write(b'x' * (api.MAX_RESPONSE_BYTES + 1))
            return
        try:
            self.wfile.write(b'\n')
            self.wfile.flush()
            while not self.server.stop.wait(0.03):
                if self.server.mode == 'keepalive':
                    self.wfile.write(b'\n')
                    self.wfile.flush()
        except (OSError, ConnectionError):
            pass


class ReapGuardTests(unittest.TestCase):
    def test_guard_stays_closed_when_wait_fails(self):
        slot = threading.Lock()
        slot.acquire()
        with patch.object(api, '_transport_slot', slot):
            api._release_after_reap(Mock(wait=Mock(side_effect=OSError('failed'))))
            self.assertTrue(slot.locked())
            child = Mock()
            child.poll.return_value = 0
            api._release_after_reap(child)
            self.assertFalse(slot.locked())


class CertifiStagingTests(unittest.TestCase):
    def test_external_linux_ca_uses_isolated_copy_but_native_keeps_real_package(self):
        with tempfile.TemporaryDirectory(prefix='deepseek-certifi-layout-') as folder:
            root = Path(folder)
            source = root / 'source-certifi'
            source.mkdir()
            source_init = source / '__init__.py'
            source_init.write_text('# native package marker\n', encoding='utf-8')
            system_ca = root / 'external-system-ca.pem'
            system_ca.write_bytes(b'fixture ca data\n')
            original_hash = hashlib.sha256(system_ca.read_bytes()).hexdigest()
            fake = types.SimpleNamespace(__file__=str(source_init), where=lambda: str(system_ca))

            source_only = root / 'source-only-packages'
            source_only.mkdir()
            self.assertEqual(_stage_certifi(source_only, fake, require_packaged=False, is_linux=True),
                             'isolated-system-ca')
            isolated = source_only / 'certifi'
            self.assertEqual((isolated / 'cacert.pem').read_bytes(), system_ca.read_bytes())
            self.assertIn('Path(__file__).with_name', (isolated / '__init__.py').read_text(encoding='utf-8'))
            with (isolated / 'cacert.pem').open('ab') as stream:
                stream.write(b'fixture test certificate\n')
            self.assertEqual(hashlib.sha256(system_ca.read_bytes()).hexdigest(), original_hash)

            native = root / 'native-packages'
            native.mkdir()
            self.assertEqual(_stage_certifi(native, fake, require_packaged=True, is_linux=True),
                             'copied-package')
            self.assertEqual((native / 'certifi/__init__.py').read_bytes(), source_init.read_bytes())
            self.assertFalse((native / 'certifi/cacert.pem').exists())
            self.assertEqual(hashlib.sha256(system_ca.read_bytes()).hexdigest(), original_hash)


class ChildTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='deepseek-transport-test-')
        self.children = []
        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.mode = 'normal'
        self.server.calls = 0
        self.server.stop = threading.Event()
        self.server.entered = threading.Event()
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.packaged_app = Path(self.temp.name) / 'packaged-app'
        self.packaged_app.mkdir()
        shutil.copyfile(Path(transport.__file__), self.packaged_app / 'deepseek_transport.py')
        packages = self.packaged_app / '.runtime' / 'packages'
        packages.mkdir(parents=True)
        _stage_certifi(packages, certifi, require_packaged='--require-packaged-certifi' in sys.argv,
                       is_linux=sys.platform.startswith('linux'))
        self.child = Path(self.temp.name) / 'test-child.py'
        self.hang_marker = Path(self.temp.name) / 'dns-stall-entered'
        self._write_child()

    def tearDown(self):
        self.server.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(2)
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
        self.temp.cleanup()

    def _write_child(self, never_read=False, hang_before_network=False):
        if never_read:
            self.child.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
            return
        # Import the real transport in the child, replacing only its network
        # open call with a local server. Production does not accept a URL from
        # the request, environment or command line.
        code = '''import sys,time,urllib.request
from pathlib import Path
sys.path.insert(0, APP)
import deepseek_transport as transport
import certifi
assert Path(certifi.__file__).resolve().is_relative_to((Path(APP) / '.runtime/packages/certifi').resolve()), 'certifi must come from the isolated packaged app'
def local_open(req, timeout):
    if HANG:
        Path(MARKER).write_text('entered', encoding='ascii')
        time.sleep(30)
    local=urllib.request.Request(URL,data=req.data,method='POST',headers=dict(req.header_items()))
    return urllib.request.urlopen(local,timeout=timeout)
transport._open=local_open
transport.main()
'''
        code = ('APP=' + repr(str(self.packaged_app)) + '\nURL=' +
                repr(f'http://127.0.0.1:{self.server.server_port}/') + '\nHANG=' +
                repr(hang_before_network) + '\nMARKER=' + repr(str(self.hang_marker)) + '\n' + code)
        self.child.write_text(code, encoding='utf-8')

    def _request(self, body=BODY):
        return Request(api.API_URL, data=body, method='POST', headers={'Authorization': 'Bearer ' + KEY})

    def _run(self, mode, timeout=0.7, body=BODY):
        self.server.mode = mode
        original = subprocess.Popen
        def start(*args, **kwargs):
            self.assertNotIn(KEY, repr(args))
            self.assertNotIn(KEY, repr(kwargs.get('env', {})))
            self.assertEqual(kwargs.get('stderr'), subprocess.DEVNULL)
            child = original(*args, **kwargs)
            self.children.append(child)
            return child
        with patch.object(api, '_CHILD_SCRIPT', self.child), patch.object(api.subprocess, 'Popen', side_effect=start):
            started = time.monotonic()
            try:
                response = api._open(self._request(body), timeout)
                return response, time.monotonic() - started, None
            except bridge.TranslationError as exc:
                self.assertNotIn(KEY, ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                return None, time.monotonic() - started, exc.kind

    def test_real_child_normal_response_and_no_credentials_in_arguments_or_environment(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': KEY, 'SSLKEYLOGFILE': KEY}):
            response, elapsed, error = self._run('normal', timeout=3)
        self.assertIsNone(error)
        self.assertEqual(response.read(), b'{"local":"ok"}')
        self.assertEqual(self.server.calls, 1)
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def test_continuous_keepalive_and_stalled_body_hit_overall_deadline(self):
        for mode in ('keepalive', 'body'):
            with self.subTest(mode=mode):
                self.server.entered.clear()
                response, elapsed, kind = self._run(mode)
                self.assertIsNone(response)
                self.assertEqual(kind, 'billing_uncertain')
                self.assertTrue(self.server.entered.is_set())
                self.assertLess(elapsed, 3.5)
                self.assertTrue(all(p.poll() is not None for p in self.children))
        self.assertEqual(self.server.calls, 2)

    def test_no_response_headers_hits_overall_deadline(self):
        response, elapsed, kind = self._run('headers')
        self.assertIsNone(response)
        self.assertEqual(kind, 'billing_uncertain')
        self.assertTrue(self.server.entered.is_set())
        self.assertLess(elapsed, 3.5)
        self.assertEqual(self.server.calls, 1)
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def test_http_auth_status_returns_without_upstream_body(self):
        response, _, kind = self._run('unauthorized', timeout=3)
        self.assertIsNone(kind)
        self.assertEqual(response.status, 401)
        self.assertEqual(response.read(), b'')
        self.assertEqual(self.server.calls, 1)
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def test_path_alias_is_accepted_for_mock_and_production_tls_child(self):
        alias = Path(self.temp.name) / 'app-alias'
        if os.name == 'nt':
            completed = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(alias), str(self.packaged_app)],
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, 'Could not create local test junction')
        else:
            os.symlink(self.packaged_app, alias, target_is_directory=True)
        self.assertNotEqual(str(alias), str(alias.resolve()))
        self.packaged_app = alias
        self._write_child()
        response, _, kind = self._run('normal', timeout=3)
        self.assertIsNone(kind)
        self.assertEqual(response.read(), b'{"local":"ok"}')
        self.test_production_child_checks_local_tls_hostname_with_packaged_ca()

    def test_external_linux_ca_shim_runs_real_local_tls_without_mutating_source(self):
        root = Path(self.temp.name)
        source_package = root / 'fake-external-certifi'
        source_package.mkdir()
        source_init = source_package / '__init__.py'
        source_init.write_text('# fixture only\n', encoding='utf-8')
        external_ca = root / 'external-ca.pem'
        shutil.copyfile(self.packaged_app / '.runtime/packages/certifi/cacert.pem', external_ca)
        original_hash = hashlib.sha256(external_ca.read_bytes()).hexdigest()
        fake = types.SimpleNamespace(__file__=str(source_init), where=lambda: str(external_ca))
        isolated_app = root / 'source-linux-app'
        packages = isolated_app / '.runtime/packages'
        packages.mkdir(parents=True)
        shutil.copyfile(Path(transport.__file__), isolated_app / 'deepseek_transport.py')
        self.assertEqual(_stage_certifi(packages, fake, require_packaged=False, is_linux=True),
                         'isolated-system-ca')
        self.packaged_app = isolated_app
        self.test_production_child_checks_local_tls_hostname_with_packaged_ca()
        self.assertEqual(hashlib.sha256(external_ca.read_bytes()).hexdigest(), original_hash)

    def test_actual_engine_timeout_pauses_without_automatic_resend(self):
        engine = object.__new__(app.Engine)
        engine.retry_delays = (0, 0)
        engine.streaming_options = lambda *args: {}
        engine.translator = Mock(wraps=providers.translate)
        job = {'source': 'The policy rate is unchanged.', 'context': ''}
        session = {'glossary': {}, 'model': 'deepseek-flash', 'profile': 'fed', 'provider': 'deepseek'}
        self.server.mode = 'keepalive'
        api.set_api_key(KEY)
        try:
            with patch.object(api, '_CHILD_SCRIPT', self.child), patch.object(api, 'TIMEOUT_SECONDS', 0.7):
                started = time.monotonic()
                with self.assertRaises(bridge.TranslationError) as caught:
                    engine.translate_job(job, session, {})
            self.assertLess(time.monotonic() - started, 3.5)
            self.assertEqual(caught.exception.kind, 'billing_uncertain')
            engine.translator.assert_called_once()
            self.assertEqual(self.server.calls, 1)
        finally:
            api.clear_api_key()

    def test_child_that_never_reads_large_stdin_is_stopped(self):
        self._write_child(never_read=True)
        response, elapsed, kind = self._run('normal', body=b'x' * 100000)
        self.assertIsNone(response)
        self.assertEqual(kind, 'billing_uncertain')
        self.assertLess(elapsed, 3.5)
        self.assertTrue(all(p.poll() is not None for p in self.children))
        self.assertEqual(self.server.calls, 0)

    def test_simulated_dns_stall_is_stopped_and_reaped(self):
        self._write_child(hang_before_network=True)
        response, elapsed, kind = self._run('normal')
        self.assertIsNone(response)
        self.assertEqual(kind, 'billing_uncertain')
        self.assertEqual(self.hang_marker.read_text(encoding='ascii'), 'entered')
        self.assertLess(elapsed, 3.5)
        self.assertEqual(self.server.calls, 0)
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def test_response_limit_and_slot_release_after_timeout(self):
        response, _, kind = self._run('large', timeout=3)
        self.assertIsNone(response)
        self.assertEqual(kind, 'format')
        response, elapsed, kind = self._run('normal', timeout=3)
        self.assertIsNone(kind)
        self.assertEqual(response.read(), b'{"local":"ok"}')
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def test_concurrent_second_request_does_not_spawn_or_send(self):
        result = []
        self.server.mode = 'keepalive'
        original = subprocess.Popen
        def start(*args, **kwargs):
            child = original(*args, **kwargs)
            self.children.append(child)
            return child
        with patch.object(api, '_CHILD_SCRIPT', self.child), patch.object(api.subprocess, 'Popen', side_effect=start):
            thread = threading.Thread(target=lambda: result.append(self._run_concurrent_first()), daemon=True)
            thread.start()
            self.assertTrue(self.server.entered.wait(3), 'First request did not reach the local server')
            with self.assertRaises(bridge.TranslationError) as caught:
                api._open(self._request(), 0.7)
            self.assertEqual(caught.exception.kind, 'billing_uncertain')
            thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ['billing_uncertain'])
        self.assertEqual(len(self.children), 1)
        self.assertEqual(self.server.calls, 1)
        self.assertTrue(all(p.poll() is not None for p in self.children))

    def _run_concurrent_first(self):
        try:
            api._open(self._request(), 1.0)
        except bridge.TranslationError as exc:
            return exc.kind
        return 'unexpected-success'

    def test_real_child_entry_rejects_bad_input_without_logging_secret(self):
        child = subprocess.run([sys.executable, '-I', '-B', str(Path(transport.__file__))],
                               input=json.dumps({'key': KEY, 'body': 'invalid!', 'socket_timeout': 1}).encode(),
                               capture_output=True, timeout=5)
        self.assertNotIn(KEY.encode(), child.stdout + child.stderr)
        self.assertEqual(child.returncode, 0)
        self.assertIn(json.loads(child.stdout)['kind'], ('configuration', 'uncertain'))

    def test_production_child_checks_local_tls_hostname_with_packaged_ca(self):
        """Patch only target DNS/URL in the test child, preserving production TLS."""
        cert_file = Path(self.temp.name) / 'test-localhost-cert.pem'
        key_file = Path(self.temp.name) / 'test-localhost-key.pem'
        cert_file.write_text(TEST_CERT, encoding='ascii')
        key_file.write_text(TEST_KEY, encoding='ascii')
        ca_bundle = self.packaged_app / '.runtime/packages/certifi/cacert.pem'
        self.assertTrue(ca_bundle.is_file())
        # Append our throwaway test CA only to the isolated copied CA bundle.
        with ca_bundle.open('ab') as f:
            f.write(b'\n' + TEST_CERT.encode('ascii'))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(cert_file), str(key_file))
        server = Server(('127.0.0.1', 0), Handler)
        server.mode = 'normal'
        server.calls = 0
        server.stop = threading.Event()
        server.entered = threading.Event()
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def write_tls_child(hostname):
                code = '''import socket,sys
from pathlib import Path
sys.path.insert(0, APP)
import deepseek_transport as transport
import certifi
assert Path(certifi.__file__).resolve().is_relative_to((Path(APP) / '.runtime/packages/certifi').resolve())
transport.API_URL=URL
original=socket.getaddrinfo
def local_resolve(host, *args, **kwargs):
    return original('127.0.0.1', *args, **kwargs)
socket.getaddrinfo=local_resolve
transport.main()
'''
                code = ('APP=' + repr(str(self.packaged_app)) + '\nURL=' +
                        repr(f'https://{hostname}:{server.server_port}/') + '\n' + code)
                self.child.write_text(code, encoding='utf-8')

            write_tls_child('localhost')
            response, _, kind = self._run('normal', timeout=3)
            self.assertIsNone(kind)
            self.assertEqual(response.read(), b'{"local":"ok"}')
            self.assertEqual(server.calls, 1)

            write_tls_child('wrong.invalid')
            response, _, kind = self._run('normal', timeout=3)
            self.assertIsNone(response)
            self.assertEqual(kind, 'billing_uncertain')
            self.assertEqual(server.calls, 1, 'Wrong hostname must not reach HTTP handler')
            self.assertTrue(all(p.poll() is not None for p in self.children))
        finally:
            server.stop.set()
            server.shutdown()
            server.server_close()
            thread.join(2)


