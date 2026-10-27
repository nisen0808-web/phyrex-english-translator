"""DeepSeek provider tests; synthetic credentials and fake transport only."""
import io
import json
import os
from pathlib import Path
import ssl
import traceback
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

import bridge
import deepseek_api as api
import deepseek_transport as transport

KEY = 'sk-123456789abcdef0123456789abcdef0'
RESULT = {'chinese': '联邦基金利率维持不变。', 'review': False, 'note': ''}


def response_body(result=RESULT, finish='stop', reasoning=None):
    message = {'role': 'assistant', 'content': json.dumps(result, ensure_ascii=False)}
    if reasoning is not None:
        message['reasoning_content'] = reasoning
    return json.dumps({'object': 'chat.completion', 'choices': [{'index': 0, 'finish_reason': finish, 'message': message}]},
                      ensure_ascii=False).encode('utf-8')


class Response(io.BytesIO):
    status = 200

    def __init__(self, data=None):
        super().__init__(response_body() if data is None else data)


class DeepSeekApiTests(unittest.TestCase):
    def setUp(self):
        api.clear_api_key()

    def tearDown(self):
        api.clear_api_key()

    def translate(self, **kwargs):
        return api.translate('The federal funds rate is unchanged.', 'Prior context.',
                             {'federal funds rate': '联邦基金利率'}, **kwargs)

    def assert_safe_error(self, context, kind=None):
        error = context.exception
        self.assertIsInstance(error, bridge.TranslationError)
        if kind:
            self.assertEqual(error.kind, kind)
        self.assertNotIn(KEY, ''.join(traceback.format_exception(type(error), error, error.__traceback__)))
        self.assertNotIn('SENSITIVE RESPONSE', str(error))
        self.assertIsNone(error.__context__)
        for frame in traceback.StackSummary.extract(traceback.walk_tb(error.__traceback__), capture_locals=True):
            if Path(frame.filename).resolve() == Path(api.__file__).resolve():
                self.assertNotIn(KEY, repr(frame.locals))

    def test_environment_key_is_not_implicitly_used(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': KEY}), patch.object(api, '_open') as send:
            self.assertFalse(api.has_api_key())
            with self.assertRaises(bridge.TranslationError) as caught:
                self.translate()
        self.assert_safe_error(caught, 'auth')
        send.assert_not_called()

    def test_credential_lifetime_and_invalid_replacement(self):
        api.set_api_key(KEY)
        self.assertTrue(api.has_api_key())
        with self.assertRaises(ValueError) as caught:
            api.set_api_key('invalid\r\nInjected: ' + KEY)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertFalse(api.has_api_key())
        api.set_api_key(KEY)
        api.clear_api_key()
        self.assertFalse(api.has_api_key())

    def test_official_request_and_two_explicit_models(self):
        api.set_api_key(KEY)
        for model in ('deepseek-flash', 'deepseek-v4-pro'):
            with self.subTest(model=model), patch.object(api, '_open', return_value=Response()) as send:
                result, elapsed = self.translate(model=model, profile='fed')
                self.assertEqual(result, RESULT)
                self.assertIsInstance(elapsed, (float, int))
                send.assert_called_once()
                req, timeout = send.call_args.args
                self.assertEqual(req.full_url, 'https://api.deepseek.com/chat/completions')
                self.assertEqual(req.get_method(), 'POST')
                self.assertEqual({k.lower(): v for k, v in req.header_items()}['authorization'], 'Bearer ' + KEY)
                body = json.loads(req.data.decode('utf-8'))
                self.assertEqual(body['model'], model)
                self.assertEqual(body['response_format'], {'type': 'json_object'})
                self.assertIs(body['stream'], False)
                self.assertEqual(body['max_tokens'], api.MAX_OUTPUT_TOKENS)
                self.assertEqual(len(body['messages']), 1)
                self.assertEqual(body['messages'][0]['role'], 'user')
                self.assertIn(bridge.translation_prompt('The federal funds rate is unchanged.', 'Prior context.',
                                                        {'federal funds rate': '联邦基金利率'}, 'fed'),
                              body['messages'][0]['content'])
                self.assertNotIn(KEY, req.data.decode('utf-8'))
                self.assertGreater(timeout, 0)

    def test_json_format_example_is_distinct_from_translation_input(self):
        api.set_api_key(KEY)
        for profile in ('fed', 'general'):
            with self.subTest(profile=profile), patch.object(api, '_open', return_value=Response()) as send:
                self.translate(profile=profile)
                prompt = json.loads(send.call_args.args[0].data.decode('utf-8'))['messages'][0]['content']
                self.assertTrue(prompt.startswith(api.JSON_EXAMPLE_INSTRUCTION))
                self.assertIn('仅为输出格式示例，不是待翻译内容', prompt)
                self.assertIn('不要复制示例译文', prompt)
                sample = api.JSON_EXAMPLE_INSTRUCTION.splitlines()[-1]
                self.assertEqual(json.loads(sample), {'chinese': '示例译文', 'review': False, 'note': ''})
                self.assertIn('The federal funds rate is unchanged.', prompt)
                self.assertNotIn(KEY, prompt)

    def test_exact_example_is_never_saved_or_automatically_resent(self):
        # Exercise the real provider route and Engine retry decision, replacing
        # only the transport with a response that repeats the format example.
        import app
        import providers
        api.set_api_key(KEY)
        engine = object.__new__(app.Engine)
        engine.retry_delays = (0, 0)
        engine.streaming_options = lambda *args: {}
        engine.translator = Mock(wraps=providers.translate)
        row = {}
        job = {'source': 'The policy rate is unchanged.', 'context': ''}
        session = {'glossary': {}, 'model': 'deepseek-flash', 'profile': 'fed', 'provider': 'deepseek'}
        example = {'chinese': '示例译文', 'review': False, 'note': ''}
        with patch.object(api, '_open', return_value=Response(response_body(example))) as transport:
            with self.assertRaises(bridge.TranslationError) as caught:
                engine.translate_job(job, session, row)
        self.assert_safe_error(caught, 'format')
        transport.assert_called_once()
        engine.translator.assert_called_once()
        self.assertNotIn('text', row)

    def test_example_variants_are_rejected_without_automatic_resend(self):
        import app
        import providers
        api.set_api_key(KEY)
        variants = ((' 示例译文 ', False, ''), ('示例译文。', True, '需要核实'),
                    ('「示 例译文！」', False, '格式不同'), ('示例\u200b译文', True, ''))
        for chinese, review, note in variants:
            with self.subTest(chinese=chinese, review=review, note=note):
                engine = object.__new__(app.Engine)
                engine.retry_delays = (0, 0)
                engine.streaming_options = lambda *args: {}
                engine.translator = Mock(wraps=providers.translate)
                row = {}
                job = {'source': 'The policy rate is unchanged.', 'context': ''}
                session = {'glossary': {}, 'model': 'deepseek-flash', 'profile': 'fed', 'provider': 'deepseek'}
                example = {'chinese': chinese, 'review': review, 'note': note}
                with patch.object(api, '_open', return_value=Response(response_body(example))) as transport:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        engine.translate_job(job, session, row)
                self.assert_safe_error(caught, 'format')
                transport.assert_called_once()
                engine.translator.assert_called_once()
                self.assertNotIn('text', row)

    def test_normal_translations_containing_example_words_are_preserved(self):
        api.set_api_key(KEY)
        for chinese in ('联邦基金利率维持不变。', '下面是示例译文，利率维持不变。',
                        '示例译文说明了价格稳定。', '这不是示例译文。'):
            with self.subTest(chinese=chinese):
                expected = {'chinese': chinese, 'review': True, 'note': '请核实'}
                with patch.object(api, '_open', return_value=Response(response_body(expected))) as transport:
                    result, _ = self.translate()
                self.assertEqual(result, expected)
                transport.assert_called_once()

    def test_disallowed_model_never_reaches_network(self):
        api.set_api_key(KEY)
        with patch.object(api, '_open') as send, self.assertRaises(bridge.TranslationError) as caught:
            self.translate(model='unknown-private-model')
        self.assert_safe_error(caught, 'model')
        send.assert_not_called()

    def test_key_in_source_or_context_never_reaches_network(self):
        api.set_api_key(KEY)
        for source, context in (('sensitive ' + KEY, ''), ('ordinary', 'sensitive ' + KEY)):
            with self.subTest(source=source[:8]), patch.object(api, '_open') as send:
                with self.assertRaises(bridge.TranslationError) as caught:
                    api.translate(source, context, {})
            self.assert_safe_error(caught)
            send.assert_not_called()

    def test_errors_sanitize_and_never_resend(self):
        cases = ((401, 'auth'), (403, 'auth'), (402, 'quota'), (429, 'quota'),
                 (404, 'model'), (400, 'api'), (408, 'billing_uncertain'),
                 (409, 'billing_uncertain'), (500, 'billing_uncertain'))
        for code, kind in cases:
            with self.subTest(code=code):
                api.set_api_key(KEY)
                failure = HTTPError(api.API_URL, code, 'SENSITIVE RESPONSE ' + KEY, {},
                                    io.BytesIO(('SENSITIVE RESPONSE ' + KEY).encode()))
                with patch.object(api, '_open', side_effect=failure) as send:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        self.translate()
                self.assert_safe_error(caught, kind)
                send.assert_called_once()
        for failure in (TimeoutError(KEY), ConnectionResetError(KEY), URLError(KEY)):
            with self.subTest(failure=type(failure).__name__):
                api.set_api_key(KEY)
                with patch.object(api, '_open', side_effect=failure) as send:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        self.translate()
                self.assert_safe_error(caught, 'billing_uncertain')
                send.assert_called_once()

    def test_refusal_truncation_and_invalid_results_are_never_saved(self):
        cases = [response_body(finish='length'), response_body(finish='content_filter'),
                 response_body(finish='tool_calls'), b'invalid', b'{}',
                 response_body({'chinese': 'English only', 'review': False, 'note': ''}),
                 response_body({'chinese': '中文', 'review': 'false', 'note': ''}),
                 response_body({'chinese': '中文', 'review': False, 'note': KEY})]
        for raw in cases:
            with self.subTest(body=raw[:60]):
                api.set_api_key(KEY)
                with patch.object(api, '_open', return_value=Response(raw)) as send:
                    with self.assertRaises(bridge.TranslationError) as caught:
                        self.translate()
                self.assert_safe_error(caught, 'format')
                send.assert_called_once()

    def test_thinking_is_not_returned_or_saved(self):
        api.set_api_key(KEY)
        with patch.object(api, '_open', return_value=Response(response_body(reasoning='secret reasoning ' + KEY))):
            result, _ = self.translate()
        self.assertEqual(result, RESULT)
        self.assertNotIn(KEY, repr(result))
        self.assertNotIn('secret reasoning', repr(result))

    def test_explicit_refusal_cannot_be_accepted_as_translation(self):
        api.set_api_key(KEY)
        outer = json.loads(response_body())
        outer['choices'][0]['message']['refusal'] = 'Declined'
        with patch.object(api, '_open', return_value=Response(json.dumps(outer).encode())):
            with self.assertRaises(bridge.TranslationError) as caught:
                self.translate()
        self.assert_safe_error(caught, 'format')

    def test_tls_verified_no_proxy_redirect_or_keylog(self):
        req = Request(api.API_URL, data=b'{}', method='POST')
        with patch.dict(os.environ, {'SSLKEYLOGFILE': 'must-not-be-created.log'}):
            with patch.object(transport.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Response()
                transport._open(req, 30)
        handlers = factory.call_args.args
        proxy = next(h for h in handlers if isinstance(h, transport.request.ProxyHandler))
        redirect = next(h for h in handlers if isinstance(h, transport._DenyRedirect))
        https = next(h for h in handlers if isinstance(h, transport.request.HTTPSHandler))
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(req, None, 302, '', {}, 'https://evil.invalid/'))
        self.assertTrue(https._context.check_hostname)
        self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsNone(https._context.keylog_filename)

    def test_platform_adapters_are_identical(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual((repo / 'windows/app/deepseek_api.py').read_bytes(),
                         (repo / 'mac/app/deepseek_api.py').read_bytes())
