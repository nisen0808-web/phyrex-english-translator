"""Offline tests for public Claude API route and local key entry. No real credentials or AI calls."""
import http.client
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import app
import bridge
import claude_api
import providers

FAKE_KEY = 'sk-ant-api03-unit-test-only-not-real-12345'


class StubEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.provider = 'claude'
        self.pending = 0
        self.problem = {}
        self.sessions = {}
        self.codex = {'ready': False}

    def refresh_login(self):
        self.codex = providers.login_status(self.provider)
        return self.codex

    def state(self, sid=None):
        return {'provider': self.provider, 'codex': self.refresh_login()}


class ClaudeIntegrationTests(unittest.TestCase):
    def setUp(self):
        claude_api.clear_api_key()

    def tearDown(self):
        claude_api.clear_api_key()

    def test_four_options_and_claude_defaults_without_auto_switch(self):
        self.assertEqual(set(providers.PROVIDERS), {'chatgpt', 'grok', 'gemini', 'claude'})
        self.assertEqual(next(iter(providers.PROVIDERS['claude']['models'])), 'claude-sonnet-5-5')
        self.assertFalse(providers.login_status('claude')['ready'])
        claude_api.set_api_key(FAKE_KEY)
        status = providers.login_status('claude')
        self.assertTrue(status['ready'])
        self.assertIn('首次翻译', status['message'])
        with self.assertRaises(ValueError):
            providers.validate_model('claude', 'gpt-6-luna')

    def test_route_invokes_only_claude_with_identical_arguments(self):
        expected = ({'chinese': '政策利率保持不变。', 'review': False, 'note': ''}, 0.2)
        callback = Mock()
        with patch.object(claude_api, 'translate', return_value=expected) as call, \
             patch.object(providers.subprocess, 'run') as foreign, \
             patch.object(bridge, 'translate') as chatgpt:
            actual = providers.translate('policy rate unchanged', 'prior', {'policy rate': '政策利率'},
                                         'claude-sonnet-5-5', 'fed', 'claude', on_partial=callback)
        self.assertEqual(actual, expected)
        call.assert_called_once_with('policy rate unchanged', 'prior', {'policy rate': '政策利率'}, 'claude-sonnet-5-5', 'fed')
        foreign.assert_not_called()
        chatgpt.assert_not_called()
        callback.assert_not_called()  # Non-streaming Claude: no unvalidated preview.

    def test_ambiguous_failure_is_not_automatically_retried(self):
        engine = object.__new__(app.Engine)
        engine.retry_delays = (0, 0)
        engine.streaming_options = lambda *args: {}
        engine.translator = Mock(side_effect=bridge.TranslationError('连接中断，费用状态待确认。', 'billing_uncertain'))
        with self.assertRaises(bridge.TranslationError):
            engine.translate_job({'source': 'test', 'context': ''},
                                 {'glossary': {}, 'model': 'claude-sonnet-5-5', 'provider': 'claude'}, {})
        self.assertEqual(engine.translator.call_count, 1)

    def test_all_claude_api_error_kinds_stop_real_engine_without_retry(self):
        """Exercise the real route and Engine method; replace only HTTP transport."""
        class FakeResponse(io.BytesIO):
            status = 200

        engine = object.__new__(app.Engine)
        engine.retry_delays = (0, 0)
        engine.streaming_options = lambda *args: {}
        engine.translator = Mock(wraps=providers.translate)
        job = {'source': 'The federal funds rate has not changed.', 'context': ''}
        session = {'glossary': {}, 'model': 'claude-sonnet-5-5', 'profile': 'fed', 'provider': 'claude'}

        cases = [
            ('auth-401', HTTPError(claude_api.API_URL, 401, 'unit test', {}, None), 'auth'),
            ('auth-403', HTTPError(claude_api.API_URL, 403, 'unit test', {}, None), 'auth'),
            ('billing-402', HTTPError(claude_api.API_URL, 402, 'unit test', {}, None), 'quota'),
            ('quota-429', HTTPError(claude_api.API_URL, 429, 'unit test', {}, None), 'quota'),
            ('request-400', HTTPError(claude_api.API_URL, 400, 'unit test', {}, None), 'api'),
            ('model-404', HTTPError(claude_api.API_URL, 404, 'unit test', {}, None), 'model'),
            ('server-500', HTTPError(claude_api.API_URL, 500, 'unit test', {}, None), 'billing_uncertain'),
            ('timeout', TimeoutError('unit test'), 'billing_uncertain'),
            ('missing-ca', bridge.TranslationError('模拟缺少 CA', 'configuration'), 'configuration'),
            ('bad-format', FakeResponse(b'{not json'), 'format'),
        ]
        for name, mock_outcome, expected_kind in cases:
            with self.subTest(name=name):
                claude_api.set_api_key(FAKE_KEY)
                engine.translator.reset_mock()
                mock_options = {'side_effect': mock_outcome} if isinstance(mock_outcome, BaseException) else {'return_value': mock_outcome}
                with patch.object(claude_api, '_open', **mock_options) as transport:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        engine.translate_job(job, session, {})
                self.assertEqual(caught.exception.kind, expected_kind)
                self.assertNotIn(FAKE_KEY, str(caught.exception))
                engine.translator.assert_called_once()
                transport.assert_called_once()

    def test_config_and_mutations_enforce_existing_local_access_boundary(self):
        """GET config checks Host/Origin; mutation routes also require the token."""
        engine = StubEngine()
        engine.glossary = {}
        engine.start = Mock(return_value='fixture-session')
        engine.accept = Mock(return_value={'accepted': True})
        engine.resume = Mock()
        engine.retry = Mock()

        class TestHandler(app.Handler):
            pass

        TestHandler.engine = engine
        TestHandler.token = 'local-fixture-token'
        server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        good_host = f'127.0.0.1:{port}'
        good_origin = f'http://{good_host}'

        def request(method, path, body=None, *, host=good_host, origin=good_origin, token='local-fixture-token'):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Host': host}
            if origin is not None:
                headers['Origin'] = origin
            if token is not None:
                headers['X-Local-Token'] = token
            if isinstance(body, dict):
                body = json.dumps(body).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            elif isinstance(body, bytes):
                headers['Content-Type'] = 'application/octet-stream'
            try:
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                raw = response.read()
                self.assertNotIn(FAKE_KEY.encode(), raw)
                return response.status, raw
            finally:
                conn.close()

        operations = [
            ('/api/start', {'title': 'fixture', 'model': 'claude-sonnet-5-5', 'provider': 'claude'}, engine.start),
            ('/api/audio?session=fixture&seq=0&start=0', b'\x00' * 320, engine.accept),
            ('/api/resume', {'session': 'fixture'}, engine.resume),
            ('/api/retry', {'session': 'fixture'}, engine.retry),
        ]
        try:
            for headers in ({'host': 'evil.example'}, {'origin': 'https://evil.example'}):
                with self.subTest(endpoint='/api/config', headers=headers):
                    status, body = request('GET', '/api/config', **headers)
                    self.assertEqual(status, 403)
                    self.assertNotIn(TestHandler.token.encode(), body)
            # The existing bootstrap intentionally returns the local token to a
            # permitted Host/Origin before the frontend has obtained a token.
            for token in (None, 'wrong-token'):
                status, body = request('GET', '/api/config', token=token)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)['token'], TestHandler.token)

            for path, body, invoked in operations:
                for headers in ({'host': 'evil.example'}, {'origin': 'https://evil.example'},
                                {'token': None}, {'token': 'wrong-token'}):
                    with self.subTest(endpoint=path, headers=headers):
                        status, raw = request('POST', path, body, **headers)
                        self.assertEqual(status, 403)
                        self.assertNotIn(TestHandler.token.encode(), raw)
                        invoked.assert_not_called()
                with self.subTest(endpoint=path, authorized=True):
                    status, _ = request('POST', path, body)
                    self.assertEqual(status, 200)
                    invoked.assert_called_once()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_key_endpoint_origin_token_recovery_and_no_echo(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        engine = StubEngine()
        app.Handler.engine = engine
        app.Handler.token = 'test-local-token-not-a-secret'
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_port

        def post(body, origin=None, token='test-local-token-not-a-secret', path='/api/claude-key'):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json', 'X-Local-Token': token}
            if origin is not None:
                headers['Origin'] = origin
            conn.request('POST', path, json.dumps(body), headers)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            status = response.status
            conn.close()
            self.assertNotIn(FAKE_KEY, data)
            return status, json.loads(data)

        try:
            good_origin = f'http://127.0.0.1:{port}'
            self.assertEqual(post({'key': FAKE_KEY})[0], 403)
            self.assertEqual(post({'key': FAKE_KEY}, 'https://evil.example')[0], 403)
            self.assertEqual(post({'key': FAKE_KEY}, good_origin, token='bad')[0], 403)
            self.assertEqual(post({'key': 'x' * 2049}, good_origin)[0], 413)
            self.assertFalse(claude_api.has_api_key())
            status, body = post({'key': FAKE_KEY, 'workspace_id': ''}, good_origin)
            self.assertEqual(status, 200)
            self.assertTrue(body['ready'])
            self.assertIn('首次翻译', body['message'])
            self.assertTrue(claude_api.has_api_key())
            self.assertEqual(post({'key': 'invalid'}, good_origin)[0], 400)
            self.assertFalse(claude_api.has_api_key())
            self.assertFalse(engine.codex['ready'])
            self.assertEqual(post({'key': FAKE_KEY}, good_origin)[0], 200)
            engine.pending = 1
            self.assertEqual(post({'clear': True}, good_origin)[0], 400)
            self.assertTrue(claude_api.has_api_key())
            engine.problem = {'kind': 'auth'}
            self.assertEqual(post({'clear': True}, good_origin)[0], 200)
            self.assertFalse(claude_api.has_api_key())
            engine.provider = 'grok'
            self.assertEqual(post({'key': FAKE_KEY}, good_origin)[0], 400)
            self.assertFalse(claude_api.has_api_key())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
