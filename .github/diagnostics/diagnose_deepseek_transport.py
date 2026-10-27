"""Offline local-only reproduction of isolated transport test failures.

Uses candidate tests, fake key, localhost servers and temporary files only.
Never sends a request to DeepSeek. The child stderr is diagnostic output from
a test-only child, not a modification of the production transport.
"""
import base64
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

repo = Path(os.environ['GITHUB_WORKSPACE']).resolve()
work = Path(os.environ['RUNNER_TEMP']).resolve() / 'phyrex-diag-runtime'
paths = json.loads((work / 'paths.json').read_text(encoding='utf-8'))
app = Path(paths['app'])
if not (app / 'deepseek_transport.py').is_file():
    raise RuntimeError('Prepared app is missing')

with tempfile.TemporaryDirectory(prefix='phyrex-diagnostic-user-') as data:
    os.environ['FED_TRANSLATOR_USER_DIR'] = data
    sys.path.insert(0, str(repo / 'tests'))
    sys.path.insert(0, str(app))
    from runtime import prepare
    prepare()
    import certifi
    import test_deepseek_transport as tests

    fake_key = tests.KEY
    def safe(value):
        return str(value).replace(fake_key, '<fake-key-redacted>')
    def pathinfo(value):
        p = Path(value)
        return {'raw': str(p), 'absolute': str(p.absolute()), 'resolved': str(p.resolve()),
                'normcase_resolved': os.path.normcase(str(p.resolve()))}
    print('SOURCE_OR_PORTABLE=' + os.environ.get('DIAG_MODE', 'unknown'))
    print('INTERPRETER=' + json.dumps(pathinfo(sys.executable)))
    print('APP=' + json.dumps(pathinfo(app)))
    print('CERTIFI_MODULE=' + json.dumps(pathinfo(certifi.__file__)))
    print('CERTIFI_CA=' + json.dumps(pathinfo(certifi.where())))
    print('CERTIFI_VERSION=' + str(getattr(certifi, '__version__', 'unknown')))
    print('NOW_UTC=' + datetime.now(timezone.utc).isoformat())

    # Execute production test module as-is. Its parent captures stdout/stderr;
    # the test's own transport child continues to use the production DEVNULL.
    test_output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    result = unittest.TextTestRunner(stream=test_output, verbosity=2).run(suite)
    print('ORIGINAL_UNITTEST_OUTPUT_BEGIN')
    print(safe(test_output.getvalue()))
    print('ORIGINAL_UNITTEST_OUTPUT_END')
    print('ORIGINAL_UNITTEST_SUMMARY=' + json.dumps({'tests': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)}))

    test = tests.ChildTransportTests(methodName='test_real_child_normal_response_and_no_credentials_in_arguments_or_environment')
    test.setUp()
    try:
        cert_file = Path(test.temp.name) / 'fixture-cert.pem'
        cert_file.write_text(tests.TEST_CERT, encoding='ascii')
        parsed = ssl._ssl._test_decode_cert(str(cert_file))
        print('TEST_CERT_VALIDITY=' + json.dumps({'notBefore': parsed.get('notBefore'),
              'notAfter': parsed.get('notAfter'), 'subjectAltName': parsed.get('subjectAltName')}))
        child_source = test.child.read_text(encoding='utf-8')
        marker = "assert certifi.__file__.startswith(APP), 'certifi must come from the isolated packaged app'"
        if child_source.count(marker) != 1:
            raise RuntimeError('Expected original child path assertion not found')
        instrumentation = '''import json,os,pathlib
print('CHILD_EXECUTABLE='+str(sys.executable),file=sys.stderr)
print('CHILD_APP='+str(APP),file=sys.stderr)
print('CHILD_CERTIFI='+str(certifi.__file__),file=sys.stderr)
print('CHILD_APP_RESOLVED='+str(pathlib.Path(APP).resolve()),file=sys.stderr)
print('CHILD_CERTIFI_RESOLVED='+str(pathlib.Path(certifi.__file__).resolve()),file=sys.stderr)
print('CHILD_RAW_STARTSWITH='+str(certifi.__file__.startswith(APP)),file=sys.stderr)
print('CHILD_RESOLVED_CONTAINMENT='+str(pathlib.Path(certifi.__file__).resolve().is_relative_to(pathlib.Path(APP).resolve())),file=sys.stderr)
'''
        # Insert diagnostic lines before, but retain, the exact original assertion.
        child_source = child_source.replace(marker, instrumentation + marker, 1)
        test.child.write_text(child_source, encoding='utf-8')
        payload = json.dumps({'key': fake_key, 'body': base64.b64encode(tests.BODY).decode('ascii'),
                              'socket_timeout': 3}).encode()
        child = subprocess.run([sys.executable, '-I', '-B', str(test.child)], input=payload,
                               capture_output=True, timeout=10)
        print('NORMAL_CHILD_EXIT=' + str(child.returncode))
        print('NORMAL_CHILD_STDERR_BEGIN\n' + safe(child.stderr.decode('utf-8', 'replace')) + 'NORMAL_CHILD_STDERR_END')
        print('NORMAL_CHILD_STDOUT=' + safe(child.stdout.decode('utf-8', 'replace')))
        print('NORMAL_LOCAL_CALLS=' + str(test.server.calls))

        # Reproduce the original local TLS fixture with the same CA copy. Only
        # the test child prints exception class / SSL verification code; no
        # private key, fake credential or request body is printed.
        private_file = Path(test.temp.name) / 'fixture-key.pem'
        private_file.write_text(tests.TEST_KEY, encoding='ascii')
        ca = test.packaged_app / '.runtime/packages/certifi/cacert.pem'
        print('FIXTURE_CA=' + json.dumps(pathinfo(ca)))
        with ca.open('ab') as f:
            f.write(b'\n' + tests.TEST_CERT.encode('ascii'))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(cert_file), str(private_file))
        server = tests.Server(('127.0.0.1', 0), tests.Handler)
        server.mode, server.calls = 'normal', 0
        server.stop, server.entered = threading.Event(), threading.Event()
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for hostname in ('localhost', 'wrong.invalid'):
                url = f'https://{hostname}:{server.server_port}/'
                code = '''import json,socket,sys,pathlib
sys.path.insert(0, APP)
import deepseek_transport as transport
import certifi
print('TLS_CHILD_APP='+str(APP),file=sys.stderr)
print('TLS_CHILD_CERTIFI='+str(certifi.__file__),file=sys.stderr)
print('TLS_CHILD_RAW_STARTSWITH='+str(certifi.__file__.startswith(APP)),file=sys.stderr)
print('TLS_CHILD_RESOLVED_CONTAINMENT='+str(pathlib.Path(certifi.__file__).resolve().is_relative_to(pathlib.Path(APP).resolve())),file=sys.stderr)
assert certifi.__file__.startswith(APP)
transport.API_URL=URL
original_resolve=socket.getaddrinfo
def local_resolve(host, *args, **kwargs):
    if host not in ('localhost','wrong.invalid'):
        raise RuntimeError('non-local host refused')
    return original_resolve('127.0.0.1', *args, **kwargs)
socket.getaddrinfo=local_resolve
original_open=transport._open
def debug_open(req,timeout):
    try:
        return original_open(req,timeout)
    except Exception as exc:
        reason=getattr(exc,'reason',exc)
        print('TLS_ERROR='+json.dumps({'outer':type(exc).__name__,'inner':type(reason).__name__,
              'verify_code':getattr(reason,'verify_code',None),
              'verify_message':getattr(reason,'verify_message',None)}),file=sys.stderr)
        raise
transport._open=debug_open
transport.main()
'''
                test.child.write_text('APP=' + repr(str(test.packaged_app)) + '\nURL=' + repr(url) + '\n' + code, encoding='utf-8')
                child = subprocess.run([sys.executable, '-I', '-B', str(test.child)], input=payload,
                                       capture_output=True, timeout=10)
                print('TLS_HOST=' + hostname + ' EXIT=' + str(child.returncode))
                print('TLS_CHILD_STDERR_BEGIN\n' + safe(child.stderr.decode('utf-8', 'replace')) + 'TLS_CHILD_STDERR_END')
                print('TLS_CHILD_STDOUT=' + safe(child.stdout.decode('utf-8', 'replace')))
                print('TLS_LOCAL_CALLS=' + str(server.calls))
        finally:
            server.stop.set()
            server.shutdown()
            server.server_close()
            thread.join(2)
    finally:
        test.tearDown()

    # A zero exit here means diagnostics were collected, not that tests passed.
    print('DIAGNOSTICS_COMPLETE; inspect ORIGINAL_UNITTEST_SUMMARY and child stderr')

