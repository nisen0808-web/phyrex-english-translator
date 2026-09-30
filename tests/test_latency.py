"""Concurrency, failure, privacy and timing guarantees of the live pipeline."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import Engine
from bridge import TranslationError


class Recognizer:
    def __init__(self):
        self.calls = []
        self.second = threading.Event()

    def transcribe(self, pcm, tail, context, *args):
        self.calls.append((tail, context))
        if len(self.calls) == 2:
            self.second.set()
        return f'Private English passage {len(self.calls)}.', 0, 1, .02, False


def translated(*args, **kwargs):
    return {'chinese': '保留否定与条件语气。', 'review': False, 'note': ''}, .03


class LatencyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.recognizer = Recognizer()
        self.engine = Engine(Path(self.folder.name), self.recognizer, translated, warm=False, retry_delays=())
        self.engine.asr = self.engine.codex = {'ready': True, 'message': 'ready'}
        self.sid = self.engine.start('延迟测试', 'gpt-6-luna')
        self.pcm = b'\x01\x10' * 16000
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        self.engine.gate.set()
        self.drain()
        self.folder.cleanup()

    def drain(self):
        deadline = time.monotonic() + 5
        while self.engine.jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(self.engine.jobs.unfinished_tasks, 0, 'Pipeline did not drain')

    def test_next_audio_is_recognized_while_first_translation_waits(self):
        entered = threading.Event()
        calls = []
        def blocking(source, context, *args):
            calls.append((source, context))
            entered.set()
            self.release.wait(4)
            return translated()
        self.engine.translator = blocking
        self.engine.accept(self.sid, 0, 0, self.pcm)
        self.assertTrue(entered.wait(2))
        self.engine.accept(self.sid, 1, 1, self.pcm)
        self.assertTrue(self.recognizer.second.wait(2), 'ASR still blocked on the AI request')
        self.assertEqual(len(calls), 1, 'Only one AI request may run at once')
        self.engine.finish(self.sid)
        self.assertEqual(self.engine.sessions[self.sid]['status'], 'draining')
        self.release.set()
        self.drain()
        self.assertEqual(calls[1][1].strip(), calls[0][0])
        self.assertNotIn(calls[1][0], calls[1][1])
        self.assertEqual(self.recognizer.calls[1][0], self.pcm[-32000:])
        self.assertEqual(self.engine.sessions[self.sid]['status'], 'finished')
        self.assertEqual(self.engine.pending, 0)
        self.assertEqual(self.engine.pipeline_jobs, {})
        self.assertEqual(self.engine.contexts, {})
        self.assertEqual(self.engine.tails, {})
        self.assertEqual(self.engine.recognized_sequences, {})

    def test_latency_data_does_not_serialize_english_or_audio(self):
        self.engine.accept(self.sid, 0, 0, self.pcm)
        self.drain()
        state = self.engine.state(self.sid)
        row = state['session']['rows'][0]
        for key in ('processing_seconds', 'recognition_wait_seconds', 'translation_wait_seconds'):
            self.assertGreaterEqual(row[key], 0)
        self.assertEqual(state['latency']['latest']['asr_seconds'], .02)
        serialized = (Path(self.folder.name) / (self.sid + '.json')).read_text(encoding='utf-8')
        self.assertNotIn('Private English', serialized)
        self.assertNotIn('Private English', json.dumps(state))
        self.assertNotIn('submitted_at', serialized)
        self.assertEqual(row['capture_start'], 0)
        self.assertEqual(row['capture_end'], 1)

    def test_quota_stops_further_ai_calls_without_dropping_prepared_audio(self):
        entered = threading.Event()
        calls = []
        def quota(*args):
            calls.append(args)
            if len(calls) == 1:
                entered.set()
                self.release.wait(4)
                raise TranslationError('额度受限', 'quota')
            return translated()
        self.engine.translator = quota
        self.engine.accept(self.sid, 0, 0, self.pcm)
        self.assertTrue(entered.wait(2))
        self.engine.accept(self.sid, 1, 1, self.pcm)
        self.assertTrue(self.recognizer.second.wait(2))
        self.release.set()
        deadline = time.monotonic() + 2
        while not self.engine.problem and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(self.engine.problem.get('kind'), 'quota')
        self.assertEqual(len(calls), 1)
        with patch('app.login_status', return_value={'ready': True, 'message': 'ready'}):
            self.engine.resume(self.sid)
        self.drain()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(self.recognizer.calls), 2, 'Translated retry should reuse recognition')
        self.assertTrue(all(r['status'] == 'done' for r in self.engine.sessions[self.sid]['rows']))
        self.assertEqual(self.engine.failed, {})

    def test_restart_recovers_waiting_translation_without_source(self):
        session = self.engine.sessions[self.sid]
        session['rows'].append({'seq': 0, 'start': 0, 'end': 1, 'status': 'waiting_translation', 'text': ''})
        self.engine.persist(session)
        recovered = Engine(Path(self.folder.name), Recognizer(), translated, warm=False)
        self.assertEqual(recovered.sessions[self.sid]['status'], 'interrupted')
        self.assertEqual(recovered.sessions[self.sid]['rows'][0]['status'], 'failed')

    def test_adaptive_chunks_follow_slower_parallel_stage_and_stay_bounded(self):
        session = self.engine.sessions[self.sid]
        self.assertEqual(self.engine.pipeline_state(session)['recommended_chunk_seconds'], 4)
        session['rows'] = [{'seq': i, 'status': 'done', 'asr_seconds': .4, 'translation_seconds': 2.3} for i in range(6)]
        self.assertEqual(self.engine.pipeline_state(session)['recommended_chunk_seconds'], 4)
        for row in session['rows']:
            row['translation_seconds'] = 6
        self.assertEqual(self.engine.pipeline_state(session)['recommended_chunk_seconds'], 6.5)
        for row in session['rows']:
            row['translation_seconds'] = 70
        self.assertEqual(self.engine.pipeline_state(session)['recommended_chunk_seconds'], 8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
