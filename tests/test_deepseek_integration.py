"""Offline DeepSeek routing and local credential endpoint checks."""
import http.client
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import app
import bridge
import deepseek_api
import providers

FAKE_KEY = 'sk-123456789abcdef0123456789abcdef0'


class StubEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.provider = 'deepseek'
        self.pending = 0
        self.problem = {}
        self.sessions = {}
        self.codex = {'ready': False}

    def refresh_login(self):
        self.codex = providers.login_status(self.provider)
        return self.codex

    def state(self, sid=None):
        return {'provider': self.provider, 'codex': self.refresh_login()}


class DeepSeekIntegrationTests(unittest.TestCase):
    def setUp(self):
        deepseek_api.clear_api_key()

    def tearDown(self):
        deepseek_api.clear_api_key()

    def test_provider_registration_and_routing(self):
        self.assertEqual(set(providers.PROVIDERS), {'chatgpt', 'grok', 'gemini', 'claude', 'deepseek'})
        self.assertFalse(providers.login_status('deepseek')['ready'])
        deepseek_api.set_api_key(FAKE_KEY)
        self.assertTrue(providers.login_status('deepseek')['ready'])
        with self.assertRaises(ValueError):
            providers.validate_model('deepseek', 'not-a-deepseek-model')
        expected = ({'chinese': '政策利率保持不变。', 'review': False, 'note': ''}, 0.2)
        with patch.object(deepseek_api, 'translate', return_value=expected) as ds, \
             patch.object(bridge, 'translate') as chatgpt:
            actual = providers.translate('rate unchanged', 'prior', {'rate': '利率'},
                                         'deepseek-flash', 'fed', 'deepseek')
        self.assertEqual(actual, expected)
        ds.assert_called_once_with('rate unchanged', 'prior', {'rate': '利率'}, 'deepseek-flash', 'fed')
        chatgpt.assert_not_called()

    def test_real_engine_does_not_automatically_retry_charged_or_ambiguous_results(self):
        class Response(io.BytesIO):
            status = 200

        engine = object.__new__(app.Engine)
        engine.retry_delays = (0, 0)
        engine.streaming_options = lambda *args: {}
        engine.translator = Mock(wraps=providers.translate)
        job = {'source': 'Rates have not fallen.', 'context': ''}
        session = {'glossary': {}, 'model': 'deepseek-flash', 'profile': 'fed', 'provider': 'deepseek'}
        cases = [(HTTPError(deepseek_api.API_URL, code, 'test', {}, None), kind) for code, kind in
                 ((401, 'auth'), (403, 'auth'), (402, 'quota'), (429, 'quota'),
                  (400, 'api'), (404, 'model'), (408, 'billing_uncertain'),
                  (409, 'billing_uncertain'), (500, 'billing_uncertain'))]
        truncated = {'object': 'chat.completion', 'choices': [{'finish_reason': 'length',
                     'message': {'role': 'assistant', 'content': '{"chinese":"中文"}'}}]}
        refused = {'object': 'chat.completion', 'choices': [{'finish_reason': 'stop',
                   'message': {'role': 'assistant', 'content': '{}', 'refusal': 'Declined'}}]}
        cases.extend([(TimeoutError('test'), 'billing_uncertain'),
                      (ConnectionResetError('test'), 'billing_uncertain'),
                      (Response(b'{not-json'), 'format'),
                      (Response(json.dumps(truncated).encode()), 'format'),
                      (Response(json.dumps(refused).encode()), 'format')])
        for outcome, expected in cases:
            with self.subTest(kind=expected):
                deepseek_api.set_api_key(FAKE_KEY)
                engine.translator.reset_mock()
                opts = {'side_effect': outcome} if isinstance(outcome, BaseException) else {'return_value': outcome}
                with patch.object(deepseek_api, '_open', **opts) as transport:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        engine.translate_job(job, session, {})
                self.assertEqual(caught.exception.kind, expected)
                self.assertNotIn(FAKE_KEY, str(caught.exception))
                engine.translator.assert_called_once()
                transport.assert_called_once()

    def test_key_endpoint_requires_local_origin_and_token_and_clears_on_bad_replacement(self):
        engine = StubEngine()

        class Handler(app.Handler):
            def do_POST(self):
                # Controlled test bodies are buffered before calling the real
                # method, avoiding Windows resets on rejected unread bodies.
                original = self.rfile
                body = original.read(int(self.headers.get('Content-Length', '0')))
                self.rfile = io.BytesIO(body)
                try:
                    return super().do_POST()
                finally:
                    self.rfile = original

        Handler.engine = engine
        Handler.token = 'fixture-local-token'
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        origin = f'http://127.0.0.1:{port}'

        def post(body, request_origin=origin, token='fixture-local-token', host=None):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json', 'X-Local-Token': token}
            if request_origin is not None:
                headers['Origin'] = request_origin
            if host is not None:
                headers['Host'] = host
            try:
                conn.request('POST', '/api/deepseek-key', json.dumps(body), headers)
                response = conn.getresponse()
                raw = response.read()
                self.assertNotIn(FAKE_KEY.encode(), raw)
                return response.status, json.loads(raw)
            finally:
                conn.close()

        try:
            for args in ({'request_origin': None}, {'request_origin': 'https://evil.example'},
                         {'token': 'wrong-token'}, {'host': 'evil.example'}):
                with self.subTest(args=args):
                    self.assertEqual(post({'api_key': FAKE_KEY}, **args)[0], 403)
                    self.assertFalse(deepseek_api.has_api_key())
            self.assertEqual(post({'api_key': 'x' * 2049})[0], 413)
            status, value = post({'api_key': FAKE_KEY})
            self.assertEqual(status, 200)
            self.assertTrue(value['ready'])
            self.assertIn('首次翻译', value['message'])
            self.assertTrue(deepseek_api.has_api_key())
            self.assertEqual(post({'api_key': 'invalid'})[0], 400)
            self.assertFalse(deepseek_api.has_api_key())
            self.assertFalse(engine.codex['ready'])
            self.assertEqual(post({'api_key': FAKE_KEY})[0], 200)
            engine.pending = 1
            self.assertEqual(post({'clear': True})[0], 400)
            self.assertTrue(deepseek_api.has_api_key())
            engine.problem = {'kind': 'auth'}
            self.assertEqual(post({'clear': True})[0], 200)
            self.assertFalse(deepseek_api.has_api_key())
            engine.provider = 'grok'
            self.assertEqual(post({'api_key': FAKE_KEY})[0], 400)
            self.assertFalse(deepseek_api.has_api_key())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_unwrapped_handler_rejects_unauthorized_key_post_without_side_effect(self):
        """Without the fixture, reject with 403 or connection abort/reset.

        The spy records the real access check; unrelated connection failures
        are never accepted as evidence that a credential was rejected.
        """
        engine = StubEngine()
        engine.refresh_login = Mock(wraps=engine.refresh_login)
        original_engine, original_token = app.Handler.engine, app.Handler.token
        app.Handler.engine = engine
        app.Handler.token = 'fixture-local-token'
        checked = threading.Event()
        observed = []
        original_check = app.Handler.local_request

        def observe_check(handler, mutation=False):
            allowed = original_check(handler, mutation)
            observed.append((mutation, allowed))
            checked.set()
            return allowed

        server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            headers = {'Content-Type': 'application/json', 'X-Local-Token': 'bad-token',
                       'Origin': f'http://127.0.0.1:{server.server_port}'}
            with patch.object(app.Handler, 'local_request', observe_check):
                try:
                    conn.request('POST', '/api/deepseek-key', json.dumps({'api_key': FAKE_KEY}), headers)
                    response = conn.getresponse()
                    raw = response.read()
                    self.assertEqual(response.status, 403)
                    self.assertNotIn(FAKE_KEY.encode(), raw)
                    self.assertNotIn(b'fixture-local-token', raw)
                except (ConnectionAbortedError, ConnectionResetError) as exc:
                    self.assertIn(getattr(exc, 'winerror', None) or exc.errno, (10053, 10054, 103, 104))
                self.assertTrue(checked.wait(2), 'The actual access check did not run')
                self.assertEqual(observed, [(True, False)])
                self.assertFalse(deepseek_api.has_api_key())
                engine.refresh_login.assert_not_called()
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            thread.join(2)
            app.Handler.engine, app.Handler.token = original_engine, original_token
