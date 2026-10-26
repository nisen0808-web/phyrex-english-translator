"""Offline Claude Messages integration: fake requests only, no real account or API."""
import io
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

import bridge
import claude_api as api


KEY = 'sk-ant-api03-fake-private-key-for-tests'
WORKSPACE = 'wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ'
RESULT = {'chinese': '我们尚未降息。', 'review': True, 'note': '请核实否定词。'}


def message(result=RESULT, stop='end_turn'):
    return json.dumps({'type': 'message', 'role': 'assistant', 'stop_reason': stop,
                       'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]},
                      ensure_ascii=False).encode('utf-8')


class Response(io.BytesIO):
    def __init__(self, body=None, status=200):
        super().__init__(message() if body is None else body)
        self.status = status


class ClaudeApiTests(unittest.TestCase):
    def tearDown(self):
        api.clear_api_key()

    def set_key(self, workspace=''):
        api.set_api_key(KEY, workspace)

    def run_translate(self, **kwargs):
        return api.translate('Rates have not fallen.', 'Prior policy context.', {'rates': '利率'}, **kwargs)

    def assert_clean_error(self, context, kind):
        exc = context.exception
        self.assertIsInstance(exc, bridge.TranslationError)
        self.assertEqual(exc.kind, kind)
        rendered = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.assertNotIn(KEY, rendered)
        self.assertNotIn('sensitive server body', rendered)
        self.assertNotIn(WORKSPACE, rendered)
        self.assertIsNone(exc.__context__)
        frames = traceback.StackSummary.extract(traceback.walk_tb(exc.__traceback__), capture_locals=True)
        for frame in frames:
            if Path(frame.filename).resolve() == Path(api.__file__).resolve():
                captured = repr(frame.locals)
                self.assertNotIn(KEY, captured)
                self.assertNotIn(WORKSPACE, captured)
                self.assertNotIn('sensitive server body', captured)

    def test_does_not_read_inherited_env_credentials_or_send_without_key(self):
        api.clear_api_key()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': KEY}, clear=False), patch.object(api, '_open') as send:
            self.assertFalse(api.has_api_key())
            with self.assertRaises(bridge.TranslationError) as caught:
                self.run_translate()
        self.assert_clean_error(caught, 'auth')
        send.assert_not_called()

    def test_key_status_and_invalid_replacement_clear_previous_key(self):
        self.set_key(WORKSPACE)
        self.assertIs(api.has_api_key(), True)
        with self.assertRaises(ValueError) as caught:
            api.set_api_key('invalid secret ' + KEY)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        frames = traceback.StackSummary.extract(traceback.walk_tb(caught.exception.__traceback__), capture_locals=True)
        for frame in frames:
            if Path(frame.filename).resolve() == Path(api.__file__).resolve():
                self.assertNotIn(KEY, repr(frame.locals))
        self.assertFalse(api.has_api_key())
        with self.assertRaises(ValueError):
            api.set_api_key('sk-ant-api03-bad"\\secret')
        self.assertFalse(api.has_api_key())
        api.clear_api_key()

    def test_rejects_bad_workspace_without_retaining_credentials(self):
        self.set_key()
        for value in ('arbitrary-workspace', 'wrkspc_foo\r\nX-Bad: injected', 'wrkspc_' + 'a' * 101):
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                api.set_api_key(KEY, value)
            self.assertFalse(api.has_api_key())
            self.assertIsNone(caught.exception.__context__)
            frames = traceback.StackSummary.extract(traceback.walk_tb(caught.exception.__traceback__), capture_locals=True)
            for frame in frames:
                if Path(frame.filename).resolve() == Path(api.__file__).resolve():
                    self.assertNotIn(KEY, repr(frame.locals))
                    self.assertNotIn(value, repr(frame.locals))

    def test_default_request_sends_one_bounded_messages_call_and_no_workspace(self):
        self.set_key()
        with patch.object(api, '_open', return_value=Response()) as send:
            result, elapsed = self.run_translate()
        self.assertEqual(result, RESULT)
        self.assertIsInstance(elapsed, (int, float))
        send.assert_called_once()
        req, timeout = send.call_args.args
        self.assertEqual(req.full_url, 'https://api.anthropic.com/v1/messages')
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(timeout, 90)
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers['x-api-key'], KEY)
        self.assertEqual(headers['anthropic-version'], '2023-06-01')
        self.assertNotIn('anthropic-workspace-id', headers)
        body = json.loads(req.data.decode('utf-8'))
        self.assertEqual(body['model'], 'claude-sonnet-5-5')
        self.assertEqual(body['max_tokens'], 4096)
        self.assertEqual(set(body), {'model', 'max_tokens', 'messages'})
        self.assertEqual(body['messages'][0]['role'], 'user')
        self.assertEqual(body['messages'][0]['content'], bridge.translation_prompt(
            'Rates have not fallen.', 'Prior policy context.', {'rates': '利率'}, 'fed'))
        self.assertNotIn(KEY, req.data.decode('utf-8'))
        self.assertNotIn(WORKSPACE, req.data.decode('utf-8'))

    def test_optional_workspace_header_and_second_explicit_model(self):
        self.set_key(WORKSPACE)
        with patch.object(api, '_open', return_value=Response()) as send:
            self.run_translate(model='claude-haiku-5-5', profile='general')
        req = send.call_args.args[0]
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers['anthropic-workspace-id'], WORKSPACE)
        data = json.loads(req.data.decode('utf-8'))
        self.assertEqual(data['model'], 'claude-haiku-5-5')
        self.assertEqual(data['messages'][0]['content'], bridge.translation_prompt(
            'Rates have not fallen.', 'Prior policy context.', {'rates': '利率'}, 'general'))

    def test_unapproved_model_never_sends(self):
        self.set_key()
        with patch.object(api, '_open') as send, self.assertRaises(bridge.TranslationError) as caught:
            self.run_translate(model='claude-fable-5-1')
        self.assert_clean_error(caught, 'model')
        send.assert_not_called()

    def test_http_errors_are_sanitized_and_never_retried(self):
        self.set_key(WORKSPACE)
        for code, kind in ((401, 'auth'), (403, 'auth'), (402, 'quota'), (429, 'quota'),
                           (404, 'model'), (400, 'api'), (302, 'api'),
                           (408, 'billing_uncertain'), (500, 'billing_uncertain'), (529, 'billing_uncertain')):
            with self.subTest(code=code):
                failure = HTTPError(api.API_URL, code, 'sensitive server body ' + KEY, {},
                                    io.BytesIO(('sensitive server body ' + KEY).encode()))
                with patch.object(api, '_open', side_effect=failure) as send, self.assertRaises(bridge.TranslationError) as caught:
                    self.run_translate()
                self.assert_clean_error(caught, kind)
                send.assert_called_once()

    def test_transport_failures_are_uncertain_and_never_retried(self):
        self.set_key()
        for failure in (TimeoutError('sensitive server body ' + KEY), URLError(KEY), OSError(KEY), RuntimeError(KEY)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(api, '_open', side_effect=failure) as send, self.assertRaises(bridge.TranslationError) as caught:
                    self.run_translate()
                self.assert_clean_error(caught, 'billing_uncertain')
                send.assert_called_once()

    def test_rejects_nonfinal_refused_or_truncated_messages(self):
        self.set_key()
        for stop in ('max_tokens', 'refusal', 'tool_use', 'pause_turn', None):
            with self.subTest(stop=stop), patch.object(api, '_open', return_value=Response(message(stop=stop))):
                with self.assertRaises(bridge.TranslationError) as caught:
                    self.run_translate()
                self.assert_clean_error(caught, 'format')
                self.assertIn('可能已产生费用', str(caught.exception))

    def test_refusal_details_never_become_a_saved_translation(self):
        self.set_key()
        body = json.loads(message())
        body['stop_details'] = {'type': 'refusal', 'explanation': 'not returned'}
        with patch.object(api, '_open', return_value=Response(json.dumps(body).encode('utf-8'))):
            with self.assertRaises(bridge.TranslationError) as caught:
                self.run_translate()
        self.assert_clean_error(caught, 'format')
        self.assertIn('可能已产生费用', str(caught.exception))

    def test_default_thinking_blocks_are_ignored_and_never_saved(self):
        self.set_key(WORKSPACE)
        outer = json.loads(message())
        outer['content'] = [
            {'type': 'thinking', 'thinking': 'internal ' + KEY, 'signature': 'opaque'},
            {'type': 'redacted_thinking', 'data': 'secret ' + WORKSPACE},
            outer['content'][0],
        ]
        with patch.object(api, '_open', return_value=Response(json.dumps(outer, ensure_ascii=False).encode('utf-8'))):
            result, _ = self.run_translate()
        self.assertEqual(result, RESULT)
        self.assertNotIn(KEY, repr(result))
        self.assertNotIn(WORKSPACE, repr(result))

    def test_unknown_or_tool_blocks_are_not_treated_as_translation(self):
        self.set_key()
        outer = json.loads(message())
        for kind in ('tool_use', 'server_tool_use', 'unknown'):
            with self.subTest(kind=kind):
                outer['content'] = [{'type': kind, 'data': 'sensitive server body ' + KEY},
                                    {'type': 'text', 'text': json.dumps(RESULT, ensure_ascii=False)}]
                with patch.object(api, '_open', return_value=Response(json.dumps(outer, ensure_ascii=False).encode('utf-8'))):
                    with self.assertRaises(bridge.TranslationError) as caught:
                        self.run_translate()
                self.assert_clean_error(caught, 'format')
                self.assertIn('可能已产生费用', str(caught.exception))

    def test_rejects_malformed_unsafe_and_oversized_response(self):
        self.set_key()
        cases = [b'bad json', b'{}', b'\xff', b'a' * (api.MAX_RESPONSE_BYTES + 1),
                 message({'chinese': 'English only', 'review': False, 'note': ''}),
                 message({'chinese': '中文', 'review': 'false', 'note': ''}),
                 message({'chinese': '中文', 'review': False, 'note': '', 'extra': 1}),
                 message({'chinese': '中文', 'review': False, 'note': 'sensitive server body ' + WORKSPACE}),
                 message({'chinese': '中文', 'review': False, 'note': 'sensitive server body ' + KEY})]
        self.set_key(WORKSPACE)
        for body in cases:
            with self.subTest(body_size=len(body)), patch.object(api, '_open', return_value=Response(body)):
                with self.assertRaises(bridge.TranslationError) as caught:
                    self.run_translate()
                self.assert_clean_error(caught, 'format')
                self.assertIn('可能已产生费用', str(caught.exception))

    def test_key_in_source_or_context_is_never_transmitted(self):
        self.set_key()
        with patch.object(api, '_open') as send, self.assertRaises(bridge.TranslationError) as caught:
            api.translate('The key is ' + KEY, '', {})
        self.assert_clean_error(caught, 'format')
        self.assertNotIn('可能已产生费用', str(caught.exception))
        send.assert_not_called()
        self.set_key(WORKSPACE)
        with patch.object(api, '_open') as send, self.assertRaises(bridge.TranslationError) as caught:
            api.translate('Mentioned ' + WORKSPACE, '', {})
        self.assert_clean_error(caught, 'format')
        self.assertNotIn('可能已产生费用', str(caught.exception))
        send.assert_not_called()

    def test_current_request_snapshot_can_finish_after_clear(self):
        self.set_key(WORKSPACE)
        def complete_after_clear(req, timeout):
            api.clear_api_key()
            self.assertEqual({k.lower(): v for k, v in req.header_items()}['x-api-key'], KEY)
            return Response()
        with patch.object(api, '_open', side_effect=complete_after_clear) as send:
            result, _ = self.run_translate()
        self.assertEqual(result, RESULT)
        self.assertFalse(api.has_api_key())
        send.assert_called_once()

    def test_tls_uses_certifi_hostname_verification_no_proxy_and_redirect_denied(self):
        req = Request(api.API_URL, data=b'{}', method='POST')
        with patch.object(api.request, 'build_opener') as factory:
            factory.return_value.open.return_value = Response()
            api._open(req, 90)
        handlers = factory.call_args.args
        proxy = next(h for h in handlers if isinstance(h, api.request.ProxyHandler))
        redirect = next(h for h in handlers if isinstance(h, api._DenyRedirect))
        https = next(h for h in handlers if isinstance(h, api.request.HTTPSHandler))
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(req, None, 302, '', {}, 'https://evil.invalid/'))
        self.assertTrue(https._context.check_hostname)
        self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
        factory.return_value.open.assert_called_once_with(req, timeout=90)

    def test_inherited_ssl_keylog_is_ignored_and_never_creates_a_file(self):
        req = Request(api.API_URL, data=b'{}', method='POST')
        with tempfile.TemporaryDirectory() as folder:
            keylog = str(Path(folder) / 'forbidden-ssl-keylog.log')
            with patch.dict(os.environ, {'SSLKEYLOGFILE': keylog}), patch.object(api.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Response()
                api._open(req, 90)
            https = next(h for h in factory.call_args.args if isinstance(h, api.request.HTTPSHandler))
            self.assertIsNone(https._context.keylog_filename)
            self.assertTrue(https._context.check_hostname)
            self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
            self.assertFalse(Path(keylog).exists())

    def test_missing_certifi_fails_before_network(self):
        req = Request(api.API_URL, data=b'{}', method='POST')
        with patch.dict(sys.modules, {'certifi': None}), patch.object(api.request, 'build_opener') as factory:
            with self.assertRaises(bridge.TranslationError) as caught:
                api._open(req, 90)
        self.assert_clean_error(caught, 'configuration')
        factory.assert_not_called()

    def test_windows_and_mac_adapter_sources_identical(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual((repo / 'windows/app/claude_api.py').read_bytes(),
                         (repo / 'mac/app/claude_api.py').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
