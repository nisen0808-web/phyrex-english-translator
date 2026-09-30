"""Bounded two-stage pipeline; source text stays in process memory only."""
import queue
import math
import threading
import time
from live_updates import LiveUpdates

WORKING = ('queued', 'recognizing', 'waiting_translation', 'translating')


class LowLatencyPipeline(LiveUpdates):
    def initialize_pipeline(self):
        self.initialize_updates()
        self.translation_jobs = queue.Queue()
        self.pipeline_jobs = {}
        self.previews = {}
        self.recognized_sequences = {}
        self.tail_gaps = {}
        threading.Thread(target=self.translation_worker, daemon=True).start()

    def enqueue_job(self, job):
        now = time.monotonic()
        job.setdefault('submitted_at', now)
        job['queued_at'] = now
        self.pipeline_jobs[(job['sid'], job['seq'])] = job
        self.jobs.put(job)
        self.notify_changed()

    def worker(self):
        # Exactly one recognizer preserves overlap, chronological context and
        # the CPU budget. It can work while the translation request is waiting.
        while True:
            job = self.jobs.get()
            self.gate.wait()
            sid, seq = job['sid'], job['seq']
            session = self.sessions[sid]
            row = next(r for r in session['rows'] if r['seq'] == seq)
            try:
                with self.lock:
                    row['recognition_wait_seconds'] = round(time.monotonic() - job['queued_at'], 3)
                    row['status'] = 'recognizing'
                    self.notify_changed()
                self.recognize_job(job, session, row)
                with self.lock:
                    if job['source']:
                        row['status'] = 'waiting_translation'
                        job['translation_queued_at'] = time.monotonic()
                        self.translation_jobs.put((job, session, row))
                        self.notify_changed()
                    else:
                        row['status'] = 'silent'
                        self.complete_job(job, session, row)
            except Exception as exc:
                self.fail_job(job, session, row, exc)
                self.complete_job(job, session, row)
            # Do not hold the last source/audio in an idle worker frame.
            job = session = row = None

    def translation_worker(self):
        # One request at a time: preserve order and provider/account isolation.
        while True:
            job, session, row = self.translation_jobs.get()
            self.gate.wait()
            try:
                with self.lock:
                    row['translation_wait_seconds'] = round(time.monotonic() - job['translation_queued_at'], 3)
                    row['status'] = 'translating'
                    self.notify_changed()
                self.translate_job(job, session, row)
            except Exception as exc:
                self.fail_job(job, session, row, exc)
            finally:
                self.complete_job(job, session, row)
                self.translation_jobs.task_done()
            job = session = row = None

    def complete_job(self, job, session, row):
        with self.lock:
            row['processing_seconds'] = round(time.monotonic() - job['submitted_at'], 3)
            key = (job['sid'], job['seq'])
            self.pipeline_jobs.pop(key, None)
            self.previews.pop(key, None)
            self.pending -= 1
            self.settle(session)
            try:
                self.persist(session)
                self.storage_error = ''
            except OSError:
                self.storage_error = '磁盘写入失败：请保留服务运行，导出当前译文并检查磁盘空间。'
            if key not in self.failed:
                job.clear()
            self.notify_changed()
        # jobs.join() still means both recognition AND translation completed.
        self.jobs.task_done()

    def pipeline_state(self, session):
        jobs = [j for (sid, _), j in self.pipeline_jobs.items() if sid == session['id']]
        rows = session['rows']
        completed = [r for r in rows if r['status'] == 'done']
        latest = max(completed, key=lambda r: r['seq']) if completed else {}
        recent = sorted(completed, key=lambda r: r['seq'])[1:][-6:]
        # Size chunks to the slower parallel stage, with the first cold request excluded.
        # Two active stages are normal, not a growing queue.
        costs = sorted(max(r.get('asr_seconds', 0), r.get('translation_seconds', 0)) for r in recent)
        target = 4 if len(costs) < 2 else min(8, max(4, math.ceil((costs[len(costs) * 3 // 4] + .5) * 2) / 2))
        return {
            'recommended_chunk_seconds': target,
            'recognizing': sum(r['status'] == 'recognizing' for r in rows),
            'translating': sum(r['status'] == 'translating' for r in rows),
            'queued': sum(r['status'] in ('queued', 'waiting_translation') for r in rows),
            'oldest_processing_seconds': round(max((time.monotonic() - j['submitted_at'] for j in jobs), default=0), 1),
            'latest': {k: latest.get(k, 0) for k in ('asr_seconds', 'translation_seconds',
                      'recognition_wait_seconds', 'translation_wait_seconds', 'processing_seconds', 'first_chinese_seconds')},
        }

    def streaming_options(self, job, session, row):
        if not getattr(self.translator, 'supports_streaming', False):
            return {}
        key = (job['sid'], job['seq'])
        started = time.monotonic()
        with self.lock:
            self.previews.pop(key, None)
            row.pop('first_chinese_seconds', None)
        def partial(text):
            with self.lock:
                if row['status'] != 'translating':
                    return
                self.previews[key] = text
                row.setdefault('first_chinese_seconds', round(time.monotonic() - started, 3))
                self.notify_changed()
        return {'on_partial': partial, 'session_id': session['id']}
