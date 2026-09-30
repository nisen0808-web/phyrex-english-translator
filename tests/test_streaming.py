import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from app import Engine, export_text, export_srt
import bridge
from streaming import CodexStream, StreamingUnavailable, chinese_preview
from test_latency import Recognizer, translated


class PreviewTests(unittest.TestCase):
    def test_only_chinese_field_is_decoded_incrementally(self):
        self.assertEqual(chinese_preview('{"chinese":"我们尚未'), '我们尚未')
        self.assertEqual(chinese_preview('{"chinese":"我们尚未降息","review":false,"note":"备注"}'), '我们尚未降息')
        self.assertEqual(chinese_preview('{"chinese":"\\u6211\\u4e'), '我')
        self.assertEqual(chinese_preview('{"chinese":"我\\uD83D'), '')
        self.assertEqual(chinese_preview('{"note":"解释","chinese":"正文"}'), '')
        self.assertEqual(chinese_preview('Here is an English explanation'), '')

    def test_preview_is_visible_but_never_saved_exported_or_read_as_final(self):
        with tempfile.TemporaryDirectory() as folder:
            entered, release = threading.Event(), threading.Event()
            def streaming_translator(*args, on_partial=None, session_id=None):
                on_partial('正在形成的中文')
                entered.set()
                release.wait(2)
                return translated()
            streaming_translator.supports_streaming = True
            engine = Engine(Path(folder), Recognizer(), streaming_translator, warm=False)
            engine.asr = engine.codex = {'ready': True, 'message': 'ready'}
            sid = engine.start('流式测试', 'gpt-6-luna')
            try:
                engine.accept(sid, 0, 0, b'\x01\x10' * 16000)
                self.assertTrue(entered.wait(1))
                state = engine.state(sid)
                row = state['session']['rows'][0]
                self.assertEqual(row['preview'], '正在形成的中文')
                self.assertEqual(row['status'], 'translating')
                engine.persist(engine.sessions[sid])
                disk = (Path(folder) / (sid + '.json')).read_text(encoding='utf-8')
                self.assertNotIn('正在形成的中文', disk)
                self.assertNotIn('正在形成的中文', export_text(state['session']))
                self.assertNotIn('正在形成的中文', export_srt(state['session']))
            finally:
                release.set()
                engine.jobs.join()
            row = engine.state(sid)['session']['rows'][0]
            self.assertNotIn('preview', row)
            self.assertGreaterEqual(row['first_chinese_seconds'], 0)
            self.assertEqual(engine.previews, {})


class ProtocolTests(unittest.TestCase):
    def prepared(self, events):
        client = CodexStream()
        client.key = ('live', 'gpt-6-luna', 'instruction')
        client.thread = 't1'
        client.messages = queue.Queue()
        for event in events:
            client.messages.put(event)
        client.connect = lambda: None
        client.rpc = lambda method, params: {'account': {'type': 'chatgpt'}} if method == 'account/read' else {'turn': {'id': 'turn1'}}
        client.close = lambda: None
        return client

    def event(self, method, **params):
        return {'method': method, 'params': {'threadId': 't1', 'turnId': 'turn1', **params}}

    def test_success_requires_completed_and_valid_final_schema(self):
        raw = json.dumps({'chinese':'尚未决定降息25个基点。', 'review':False, 'note':''}, ensure_ascii=False)
        events = [self.event('item/agentMessage/delta', delta=raw[:18]),
                  self.event('item/agentMessage/delta', delta=raw[18:]),
                  self.event('turn/completed', turn={'id':'turn1', 'status':'completed'})]
        client = self.prepared(events)
        previews = []
        result, _ = client.translate('instruction\n资料 JSON：\n{}', 'gpt-6-luna', 'live', previews.append)
        self.assertEqual(result['chinese'], '尚未决定降息25个基点。')
        self.assertTrue(previews)

    def test_failed_turn_cannot_promote_a_partial_translation(self):
        events = [self.event('item/agentMessage/delta', delta='{"chinese":"不会降息'),
                  self.event('turn/completed', turn={'id':'turn1', 'status':'failed','error':{'message':'rate limit 429'}})]
        client = self.prepared(events)
        with self.assertRaises(bridge.TranslationError) as error:
            client.translate('instruction\n资料 JSON：\n{}', 'gpt-6-luna', 'live', lambda x: None)
        self.assertEqual(error.exception.kind, 'quota')

    def test_stream_auth_still_refuses_api_key_route(self):
        client = CodexStream()
        client.connect = lambda: None
        client.rpc = Mock(return_value={'account': {'type': 'apiKey'}})
        with patch('streaming.CLIENT', client), patch('bridge.login_status') as login:
            with self.assertRaises(bridge.TranslationError):
                bridge.translate('Test.', '', {}, on_partial=lambda x: None)
            login.assert_not_called()
            self.assertEqual([call.args[0] for call in client.rpc.call_args_list], ['account/read'])

    def test_preparation_is_reused_without_any_inference(self):
        client = CodexStream()
        client.connect = lambda: None
        calls = []
        def rpc(method, params):
            calls.append((method, params))
            if method == 'account/read':
                return {'account': {'type': 'chatgpt'}}
            self.assertEqual(method, 'thread/start')
            return {'thread': {'id': 'warm', 'ephemeral': True}}
        client.rpc = rpc
        cancelled = threading.Event()
        with patch('streaming.CLIENT', client):
            bridge.prepare_session(model='gpt-6-luna', profile='fed', session_id='test', cancelled=cancelled)
            instruction = bridge.translation_prompt('We will not cut rates.', 'previous', {}, 'fed').split('\n资料 JSON：\n')[0]
            client.prepare(instruction, 'gpt-6-luna', 'test')
        self.assertEqual(sum(method == 'thread/start' for method, _ in calls), 1)
        self.assertEqual(client.key, ('test', 'gpt-6-luna', instruction))
        self.assertEqual(client.turns, 0)
        cancelled.set()
        client.prepare(instruction, 'gpt-6-luna', 'cancelled', cancelled)
        self.assertEqual(client.key[0], 'test')

    def test_streaming_reuses_validation_without_launching_login_subprocess(self):
        result = {'chinese': '利率保持不变。', 'review': False, 'note': ''}
        with patch('streaming.CLIENT.translate', return_value=(result, .1)), patch('bridge.login_status') as login:
            self.assertEqual(bridge.translate('Rates are unchanged.', '', {}, on_partial=lambda x: None)[0], result)
            login.assert_not_called()

    def test_only_initialization_unavailability_allows_compatibility_fallback(self):
        from types import SimpleNamespace
        output = SimpleNamespace(returncode=0,stdout='{"chinese":"中文译文","review":false,"note":""}',stderr='')
        with patch('bridge.login_status',return_value={'ready':True}), patch('bridge.codex_path',return_value='codex.exe'), patch('streaming.CLIENT.translate',side_effect=StreamingUnavailable()), patch('bridge.subprocess.run',return_value=output) as run:
            result,_=bridge.translate('Test.', '', {}, on_partial=lambda x: None)
            self.assertEqual(result['chinese'], '中文译文')
            self.assertEqual(run.call_count, 1)
        with patch('bridge.login_status',return_value={'ready':True}), patch('streaming.CLIENT.translate',side_effect=bridge.TranslationError('连接中断')), patch('bridge.subprocess.run') as run:
            with self.assertRaises(bridge.TranslationError):
                bridge.translate('Test.', '', {}, on_partial=lambda x: None)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
