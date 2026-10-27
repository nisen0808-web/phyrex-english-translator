"""Exercise retry-consent routing on the real local Handler and Engine methods.

All services, accounts and keys are simulated; no model requests are made.
"""
import copy
import http.client
import json
import queue
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

import app


class ApiChargeConfirmationTests(unittest.TestCase):
    def setUp(self):
        class Handler(app.Handler):
            pass

        Handler.token = 'fixture-local-token'
        self.handler = Handler
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def engine(self, provider, *, problem=True):
        engine = object.__new__(app.Engine)
        engine.lock = threading.RLock()
        engine.provider = provider
        model = {'claude': 'claude-sonnet-5-5', 'deepseek': 'deepseek-flash', 'chatgpt': 'gpt-6-luna',
                 'grok': 'auto', 'gemini': 'auto'}[provider]
        engine.sessions = {'fixture': {'provider': provider, 'model': model, 'status': 'finished',
                                        'rows': [{'seq': 1, 'status': 'failed', 'text': 'old', 'note': 'old'}]}}
        engine.failed = {('fixture', 1): {'sid': 'fixture', 'seq': 1}}
        engine.pending = 0
        engine.problem = {'kind': 'quota', 'session': 'fixture', 'message': 'fixture'} if problem else {}
        engine.gate = threading.Event()
        if not problem:
            engine.gate.set()
        engine.codex = {'ready': True, 'message': 'before'}
        engine.refresh_login = Mock(return_value={'ready': True, 'message': 'ready'})
        engine.notify_changed = Mock()
        engine.persist = Mock()
        engine.enqueue_job = Mock()
        self.handler.engine = engine
        return engine

    def post(self, route, payload):
        port = self.server.server_port
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            conn.request('POST', route, json.dumps(payload), {
                'Content-Type': 'application/json',
                'Origin': f'http://127.0.0.1:{port}',
                'X-Local-Token': 'fixture-local-token',
            })
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def snapshot(self, engine):
        return copy.deepcopy((engine.provider, engine.sessions, engine.failed, engine.pending,
                              engine.problem, engine.gate.is_set(), engine.codex))

    def assert_no_effect(self, engine, before):
        self.assertEqual(self.snapshot(engine), before)
        engine.refresh_login.assert_not_called()
        engine.notify_changed.assert_not_called()
        engine.persist.assert_not_called()
        engine.enqueue_job.assert_not_called()

    def test_api_resume_requires_exact_boolean_and_matching_provider(self):
        for provider in ('claude', 'deepseek'):
            for consent in ({}, {'confirm_api_charge': True},
                            {'confirm_api_charge': 1, 'confirm_api_provider': provider},
                            {'confirm_api_charge': True, 'confirm_api_provider': 'chatgpt'},
                            {'confirm_api_charge': True, 'confirm_api_provider': 'deepseek' if provider == 'claude' else 'claude'}):
                with self.subTest(provider=provider, consent=consent):
                    engine = self.engine(provider)
                    before = self.snapshot(engine)
                    status, _ = self.post('/api/resume', {'session': 'fixture', **consent})
                    self.assertEqual(status, 400)
                    self.assert_no_effect(engine, before)

    def test_api_retry_requires_explicit_confirmation_without_side_effects(self):
        for provider in ('claude', 'deepseek'):
            for consent in ({}, {'confirm_api_charge': False, 'confirm_api_provider': provider},
                            {'confirm_api_charge': True, 'confirm_api_provider': 'claude' if provider == 'deepseek' else 'deepseek'}):
                with self.subTest(provider=provider, consent=consent):
                    engine = self.engine(provider, problem=False)
                    before = self.snapshot(engine)
                    status, _ = self.post('/api/retry', {'session': 'fixture', **consent})
                    self.assertEqual(status, 400)
                    self.assert_no_effect(engine, before)

    def test_confirmed_api_resume_requeues_once_and_opens_gate(self):
        for provider in ('claude', 'deepseek'):
            with self.subTest(provider=provider):
                engine = self.engine(provider)
                status, _ = self.post('/api/resume', {'session': 'fixture', 'model': engine.sessions['fixture']['model'],
                    'confirm_api_charge': True, 'confirm_api_provider': provider})
                self.assertEqual(status, 200)
                engine.refresh_login.assert_called_once()
                engine.enqueue_job.assert_called_once()
                self.assertEqual(engine.pending, 1)
                self.assertFalse(engine.failed)
                self.assertFalse(engine.problem)
                self.assertTrue(engine.gate.is_set())

    def test_confirmed_api_retry_requeues_once(self):
        for provider in ('claude', 'deepseek'):
            with self.subTest(provider=provider):
                engine = self.engine(provider, problem=False)
                status, _ = self.post('/api/retry', {'session': 'fixture',
                    'confirm_api_charge': True, 'confirm_api_provider': provider})
                self.assertEqual(status, 200)
                engine.enqueue_job.assert_called_once()
                self.assertEqual(engine.pending, 1)
                self.assertFalse(engine.failed)

    def test_non_api_resume_and_retry_do_not_require_api_consent(self):
        for provider in ('chatgpt', 'grok', 'gemini'):
            with self.subTest(provider=provider):
                engine = self.engine(provider)
                status, _ = self.post('/api/resume', {'session': 'fixture', 'model': engine.sessions['fixture']['model']})
                self.assertEqual(status, 200)
                engine.enqueue_job.assert_called_once()
                engine = self.engine(provider, problem=False)
                status, _ = self.post('/api/retry', {'session': 'fixture'})
                self.assertEqual(status, 200)
                engine.enqueue_job.assert_called_once()

    def test_stale_page_or_mismatched_session_cannot_authorize_another_provider(self):
        engine = self.engine('deepseek')
        engine.sessions['other'] = {'provider': 'chatgpt', 'model': 'gpt-6-luna', 'status': 'finished', 'rows': []}
        before = self.snapshot(engine)
        # The actual problem session is DeepSeek even if the selected history is ChatGPT.
        status, _ = self.post('/api/resume', {'session': 'other', 'model': 'deepseek-flash'})
        self.assertEqual(status, 400)
        self.assert_no_effect(engine, before)
        status, _ = self.post('/api/resume', {'session': 'other', 'model': 'deepseek-flash',
            'confirm_api_charge': True, 'confirm_api_provider': 'claude'})
        self.assertEqual(status, 400)
        self.assert_no_effect(engine, before)
        # A cross-provider selected history cannot be mutated or requeued.
        engine.problem = {}
        before = self.snapshot(engine)
        status, _ = self.post('/api/retry', {'session': 'other', 'confirm_api_charge': True, 'confirm_api_provider': 'deepseek'})
        self.assertEqual(status, 400)
        self.assert_no_effect(engine, before)

    def test_missing_session_falls_back_to_current_api_and_still_requires_consent(self):
        engine = self.engine('deepseek')
        engine.problem = {}
        before = self.snapshot(engine)
        status, _ = self.post('/api/resume', {})
        self.assertEqual(status, 400)
        self.assert_no_effect(engine, before)

    def test_full_queue_retry_keeps_finished_session_and_failed_cache(self):
        for provider in ('claude', 'deepseek'):
            with self.subTest(provider=provider):
                engine = self.engine(provider, problem=False)
                engine.pending = app.MAX_PENDING
                before = self.snapshot(engine)
                status, result = self.post('/api/retry', {'session': 'fixture',
                    'confirm_api_charge': True, 'confirm_api_provider': provider})
                self.assertEqual(status, 400)
                self.assertIn('队列已满', result['error'])
                self.assertEqual(self.snapshot(engine), before)
                engine.enqueue_job.assert_not_called()

    def test_full_queue_resume_opens_gate_and_reports_unqueued_failures(self):
        for provider in ('claude', 'deepseek'):
            with self.subTest(provider=provider):
                engine = self.engine(provider)
                engine.pending = app.MAX_PENDING
                status, result = self.post('/api/resume', {'session': 'fixture',
                    'confirm_api_charge': True, 'confirm_api_provider': provider})
                self.assertEqual(status, 200)
                self.assertEqual((result['retried'], result['remaining']), (0, 1))
                self.assertTrue(engine.gate.is_set())
                self.assertEqual(engine.sessions['fixture']['status'], 'finished')
                self.assertEqual(engine.sessions['fixture']['rows'][0]['status'], 'failed')
                self.assertEqual(len(engine.failed), 1)
                engine.enqueue_job.assert_not_called()

    def test_partial_queue_reports_remaining_for_resume_and_retry(self):
        for provider in ('claude', 'deepseek'):
            for route in ('resume', 'retry'):
                with self.subTest(provider=provider, route=route):
                    engine = self.engine(provider, problem=(route == 'resume'))
                    engine.pending = app.MAX_PENDING - 1
                    engine.sessions['fixture']['rows'].append({'seq': 2, 'status': 'failed', 'text': 'old', 'note': 'old'})
                    engine.failed[('fixture', 2)] = {'sid': 'fixture', 'seq': 2}
                    status, result = self.post('/api/' + route, {'session': 'fixture',
                        'confirm_api_charge': True, 'confirm_api_provider': provider})
                    self.assertEqual(status, 200)
                    self.assertEqual((result['retried'], result['remaining']), (1, 1))
                    self.assertEqual(engine.pending, app.MAX_PENDING)
                    self.assertEqual(len(engine.failed), 1)
                    self.assertEqual([row['status'] for row in engine.sessions['fixture']['rows']], ['queued', 'failed'])
                    engine.enqueue_job.assert_called_once()
                    if route == 'resume':
                        self.assertTrue(engine.gate.is_set())

    def test_failure_completion_cannot_race_with_confirmed_resume(self):
        class StopWorker(Exception):
            pass

        class SingleGetQueue(queue.Queue):
            def __init__(self):
                super().__init__()
                self.taken = False

            def get(self, *args, **kwargs):
                if self.taken:
                    raise StopWorker()
                self.taken = True
                return super().get(*args, **kwargs)

        for phase in ('recognition', 'translation'):
            with self.subTest(phase=phase):
                engine = self.engine('deepseek', problem=False)
                del engine.enqueue_job
                engine.sessions['fixture']['status'] = 'recording'
                row = engine.sessions['fixture']['rows'][0]
                row['status'] = 'queued'
                engine.failed = {}
                engine.pending = 1
                engine.pipeline_jobs = {}
                engine.previews = {}
                engine.settle = Mock()
                engine.jobs = SingleGetQueue() if phase == 'recognition' else queue.Queue()
                engine.translation_jobs = SingleGetQueue() if phase == 'translation' else queue.Queue()
                job = {'sid': 'fixture', 'seq': 1, 'source': 'mock', 'submitted_at': time.monotonic(),
                       'queued_at': time.monotonic(), 'translation_queued_at': time.monotonic()}
                engine.pipeline_jobs[('fixture', 1)] = job
                engine.jobs.put(job)
                if phase == 'translation':
                    self.assertIs(engine.jobs.get(), job)
                    engine.translation_jobs.put((job, engine.sessions['fixture'], row))
                failure = app.TranslationError('模拟失败', 'format')
                engine.recognize_job = Mock(side_effect=failure)
                engine.translate_job = Mock(side_effect=failure)
                failed, release, attempt = threading.Event(), threading.Event(), threading.Event()
                original_fail = engine.fail_job

                def staged_fail(*args):
                    original_fail(*args)
                    failed.set()
                    if not release.wait(3):
                        raise AssertionError('test did not release the failed worker')

                engine.fail_job = staged_fail
                errors = []

                def run_worker():
                    try:
                        (engine.worker if phase == 'recognition' else engine.translation_worker)()
                    except StopWorker:
                        pass
                    except Exception as exc:
                        errors.append(exc)

                def run_resume():
                    attempt.set()
                    try:
                        engine.resume('fixture', None, True, 'deepseek')
                    except Exception as exc:
                        errors.append(exc)

                worker = threading.Thread(target=run_worker, daemon=True)
                worker.start()
                self.assertTrue(failed.wait(3))
                # The failure and completion transition holds one lock.
                self.assertFalse(engine.lock.acquire(blocking=False))
                resumer = threading.Thread(target=run_resume, daemon=True)
                resumer.start()
                self.assertTrue(attempt.wait(3))
                release.set()
                worker.join(3)
                resumer.join(3)
                self.assertFalse(worker.is_alive())
                self.assertFalse(resumer.is_alive())
                self.assertEqual(errors, [])
                self.assertIs(engine.jobs.queue[0], job)
                self.assertEqual(job['sid'], 'fixture')
                self.assertIs(engine.pipeline_jobs[('fixture', 1)], job)
                self.assertEqual(engine.pending, 1)
                self.assertEqual(row['status'], 'queued')


if __name__ == '__main__':
    unittest.main()
