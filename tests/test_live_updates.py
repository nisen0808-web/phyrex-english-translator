import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from app import Engine, Handler
from live_updates import StateDelta
from test_latency import Recognizer, translated


def decode(frame):
    lines = frame.decode('utf-8').splitlines()
    return lines[0].split(': ', 1)[1], json.loads(lines[1].split(': ', 1)[1])


class DeltaTests(unittest.TestCase):
    def test_delta_only_sends_changed_rows_and_reconnect_resets(self):
        state = {'revision': 1, 'session': {'id': 's1', 'rows': [
            {'seq': 0, 'text': '第一段', 'status': 'done'},
            {'seq': 1, 'text': '', 'preview': '第二', 'status': 'translating'}]}}
        delta = StateDelta()
        self.assertEqual(decode(delta.encode(copy.deepcopy(state)))[0], 'snapshot')
        state['revision'] = 2
        state['session']['rows'][1]['preview'] = '第二段'
        event, payload = decode(delta.encode(copy.deepcopy(state)))
        self.assertEqual(event, 'update')
        self.assertNotIn('rows', payload['state']['session'])
        self.assertEqual([row['seq'] for row in payload['rows']], [1])
        state['session']['rows'].pop(0)
        self.assertEqual(decode(delta.encode(copy.deepcopy(state)))[1]['removed'], [0])
        self.assertEqual(decode(StateDelta().encode(state))[0], 'snapshot')
        state['session']['id'] = 'history'
        self.assertEqual(decode(delta.encode(state))[0], 'snapshot')


class EventHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name), Recognizer(), translated, warm=False)
        self.engine.asr = self.engine.codex = {'ready': True, 'message': 'ready'}
        engine = self.engine
        class TestHandler(Handler):
            pass
        TestHandler.engine, TestHandler.token = engine, 'local-test-token'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connections = []

    def tearDown(self):
        for conn, response in self.connections:
            response.close()
            conn.close()
        self.engine.jobs.join()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def connect(self, path='/api/events', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request('GET', path, headers=headers or {})
        response = conn.getresponse()
        self.connections.append((conn, response))
        return response

    def event(self, response):
        event, data = '', ''
        while True:
            line = response.readline().decode('utf-8').strip()
            if line.startswith('event: '):
                event = line[7:]
            if line.startswith('data: '):
                data = line[6:]
            if not line and event and data:
                return event, json.loads(data)

    def test_push_and_reconnect_deliver_exact_final_without_persisting_preview(self):
        entered, release = threading.Event(), threading.Event()
        def translator(*args, **kwargs):
            kwargs['on_partial']('尚未决定')
            entered.set()
            release.wait(2)
            return translated()
        translator.supports_streaming = True
        self.engine.translator = translator
        sid = self.engine.start('推送验证', 'gpt-6-luna')
        response = self.connect('/api/events?session=' + sid)
        self.assertEqual(response.status, 200)
        self.assertTrue(response.getheader('Content-Type').startswith('text/event-stream'))
        event, initial = self.event(response)
        self.assertEqual(event, 'snapshot')
        self.assertEqual(initial['session']['rows'], [])
        self.engine.accept(sid, 0, 0, b'\x01\x10' * 16000)
        try:
            self.assertTrue(entered.wait(1))
            while True:
                event, update = self.event(response)
                if any(row.get('preview') == '尚未决定' for row in update.get('rows', [])):
                    break
            self.assertEqual(event, 'update')
            self.assertFalse(any(row['status'] == 'done' for row in update['rows']))
        finally:
            release.set()
            self.engine.jobs.join()
        self.engine.finish(sid)
        fresh = self.connect('/api/events?session=' + sid)
        event, final = self.event(fresh)
        self.assertEqual(event, 'snapshot')
        row = final['session']['rows'][0]
        self.assertEqual(row['text'], translated()[0]['chinese'])
        self.assertNotIn('preview', row)
        self.assertEqual(final['session']['status'], 'finished')
        disk = (Path(self.temp.name) / (sid + '.json')).read_text(encoding='utf-8')
        self.assertNotIn('preview', disk)

    def test_event_stream_retains_host_and_origin_restrictions(self):
        for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}):
            response = self.connect(headers=headers)
            self.assertEqual(response.status, 403)

    def test_preparation_runs_during_capture_and_is_cancelled_on_empty_finish(self):
        entered, returned = threading.Event(), threading.Event()
        observed = []
        def translator(*args, **kwargs):
            return translated()
        def prepare(**options):
            observed.append(options)
            entered.set()
            options['cancelled'].wait(2)
            returned.set()
        translator.prepare = prepare
        self.engine.translator = translator
        sid = self.engine.start('预热验证', 'gpt-6-luna')
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.engine.sessions[sid]['rows'], [])
        self.engine.finish(sid)
        self.assertTrue(returned.wait(1))
        self.assertTrue(observed[0]['cancelled'].is_set())
        self.assertEqual(observed[0]['session_id'], sid)


if __name__ == '__main__':
    unittest.main()
