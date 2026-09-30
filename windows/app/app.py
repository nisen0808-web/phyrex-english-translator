from terminology import validate_glossary
"""Loopback-only Chinese livestream translator; browser supplies 16 kHz mono PCM."""
import argparse
import hashlib
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import queue
import re
import secrets
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import zipfile
from xml.sax.saxutils import escape

from runtime import ROOT, USER_DIR, instance_id, acquire_instance_lock, prepare
CONFIG = prepare()
from providers import (PROVIDERS, login_status, translate, TranslationError,
                       validate_provider, validate_model, clear_transient_history, mark_login)
from recognizer import Recognizer
from profiles import PROFILES, profile_config
from provider_auth import LoginManager

DATA = USER_DIR / 'records'
RATE = 16000
MAX_PENDING = 12

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def timestamp(seconds, subtitle=False):
    millis = max(0, round(seconds * 1000))
    h, rem = divmod(millis, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02}' + (f',{ms:03}' if subtitle else '')

def export_text(session, include_times=True):
    lines = [session['title'], session['created'], '']
    for row in sorted(session['rows'], key=lambda r: r['seq']):
        if row['status'] == 'silent':
            continue
        text = row.get('text') or '[该段尚未完成翻译]'
        prefix = f"[{timestamp(row['start'])}] " if include_times else ''
        lines.append(prefix + text)
        if row.get('note'):
            lines.append('待核实：' + row['note'])
        lines.append('')
    if session['status'] not in ('finished',):
        lines.append('说明：这是当前已处理内容，录制可能仍在继续或存在待处理片段。')
    return '\n'.join(lines)

def export_srt(session):
    rows = []
    for row in sorted(session['rows'], key=lambda r: r['seq']):
        if row['status'] == 'silent':
            continue
        text = row.get('text') or '[该段尚未完成翻译]'
        rows.append(f"{len(rows)+1}\n{timestamp(row['start'], True)} --> {timestamp(max(row['end'], row['start']+.05), True)}\n{text}\n")
    return '\n'.join(rows)

def export_docx(session, include_times=True):
    # A minimal standards-based DOCX avoids a second document runtime dependency.
    paragraphs = export_text(session, include_times).split('\n')
    xml = ''.join('<w:p><w:r><w:t xml:space="preserve">' + escape(p) + '</w:t></w:r></w:p>' for p in paragraphs)
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + xml + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', document)
        z.writestr('word/_rels/document.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('word/styles.xml', '<?xml version="1.0"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:eastAsia="Microsoft YaHei"/><w:sz w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="320" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults></w:styles>')
    return out.getvalue()

from latency import LowLatencyPipeline
from live_updates import serve_events

class Engine(LowLatencyPipeline):
    def __init__(self, data=DATA, recognizer=None, translator=translate, warm=True, retry_delays=(2, 5)):
        self.data = data
        self.data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.recognizer = recognizer or Recognizer()
        self.translator = translator
        self.sessions = {}
        self.contexts, self.tails, self.failed = {}, {}, {}
        self.pending = 0
        self.storage_error = ''
        self.jobs = queue.Queue()
        self.gate = threading.Event()
        self.gate.set()
        self.problem = {}
        self.retry_delays = retry_delays
        self.login = LoginManager()
        self.provider = 'chatgpt'
        try:
            self.provider = validate_provider(json.loads((USER_DIR / 'ai-choice.json').read_text(encoding='utf-8'))['provider'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.login.select(self.provider)
        for provider in ('grok', 'gemini'):
            clear_transient_history(provider)
        self.asr = {'ready': False, 'message': '正在加载本地语音模型'}
        self.codex = {'ready': False, 'message': '正在检查 ' + PROVIDERS[self.provider]['label'] + ' 登录'}
        self.glossary = json.loads(((USER_DIR / 'glossary.json') if (USER_DIR / 'glossary.json').exists() else (ROOT / 'glossary.json')).read_text(encoding='utf-8'))
        for path in self.data.glob('*.json'):
            try:
                s = json.loads(path.read_text(encoding='utf-8'))
                if s.get('status') in ('recording', 'draining'):
                    s['status'] = 'interrupted'
                    for row in s['rows']:
                        if row['status'] in ('queued', 'recognizing', 'waiting_translation', 'translating'):
                            row.update(status='failed', text='[程序中断，该段未完成翻译]', note='请从原视频重播这一时间段。')
                    write_json(path, s)
                self.sessions[s['id']] = s
            except (ValueError, KeyError, OSError):
                continue
        self.initialize_pipeline()
        if warm:
            threading.Thread(target=self.warm, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()

    def warm(self):
        self.refresh_login()
        try:
            self.recognizer.load()
            self.asr = {'ready': True, 'message': getattr(self.recognizer, 'status_message', '本地语音识别已就绪')}
        except Exception:
            self.asr = {'ready': False, 'message': '语音模型加载失败，请运行安装程序。'}
        finally:
            self.notify_changed()

    def refresh_login(self):
        with self.lock:
            provider = self.provider
        status = login_status(provider)
        with self.lock:
            if provider == self.provider:
                self.codex = status
                self.notify_changed()
        return status

    def select_provider(self, provider):
        validate_provider(provider)
        with self.lock:
            if provider == self.provider:
                return self.codex
            if self.pending or self.problem or any(s['status'] in ('recording', 'draining') for s in self.sessions.values()):
                raise ValueError('请先结束当前采集并处理完片段，再切换 AI；当前记录不会改用其他账号。')
            self.login.select(provider)
            write_json(USER_DIR / 'ai-choice.json', {'provider': provider})
            self.provider = provider
            self.codex = {'ready': False, 'message': '正在检查 ' + PROVIDERS[provider]['label'] + ' 登录'}
        return self.refresh_login()

    def resume(self, sid=None, model=None):
        status = self.refresh_login()
        with self.lock:
            self.codex = status
            if not status['ready']:
                raise ValueError(status['message'])
            # A model unavailable to this account can be replaced for this session.
            sid = self.problem.get('session', sid)
            if model is not None:
                validate_model(self.provider, model)
                if sid:
                    self.sessions[sid]['model'] = model
            # Retry cached failures before releasing the waiting worker.
            if sid and any(key[0] == sid for key in self.failed):
                self.retry(sid)
            self.problem = {}
            self.gate.set()
            self.notify_changed()

    def heartbeat(self, sid):
        with self.lock:
            if self.sessions[sid]['status'] == 'recording':
                self.sessions[sid]['last_seen'] = time.time()

    def expire_sessions(self, now=None):
        with self.lock:
            now = time.time() if now is None else now
            for s in self.sessions.values():
                if s['status'] == 'recording' and now - s.get('last_seen', now) > 180:
                    s['status'] = 'draining'
                    s['capture_notice'] = '页面连接已中断，采集已结束；已提交的音频继续处理。'
                    self.settle(s)
                    self.persist(s)

    def persist(self, session):
        write_json(self.data / (session['id'] + '.json'), session)
        self.notify_changed()

    def start(self, title, model, profile='fed', provider=None):
        with self.lock:
            provider = provider or self.provider
            validate_provider(provider)
            if provider != self.provider:
                raise ValueError('AI 选择已发生变化，请刷新页面后重新开始。')
            profile_config(profile)
            if self.problem:
                raise ValueError(self.problem['message'])
            if not self.asr['ready'] or not self.codex['ready']:
                raise ValueError('请先等待语音模型就绪，并确认所选 AI 已登录。')
            if any(s['status'] in ('recording', 'draining') for s in self.sessions.values()):
                raise ValueError('已有会话正在运行，请先结束并等待处理完成。')
            validate_model(provider, model)
            sid = datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(3)
            s = {'id': sid, 'title': str(title).strip()[:100] or '美联储直播翻译',
                 'created': datetime.now().astimezone().isoformat(timespec='seconds'),
                 'status': 'recording', 'model': model, 'next_seq': 0, 'received_seconds': 0,
                 'rows': [], 'glossary': dict(self.glossary) if profile == 'fed' else {},
                 'profile': profile, 'language': 'en', 'provider': provider, 'last_seen': time.time()}
            self.sessions[sid] = s
            self.persist(s)
            self.prepare_session(s)
            return sid

    def accept(self, sid, seq, start, pcm):
        if self.storage_error:
            raise ValueError('中文记录写入失败，请先检查磁盘空间并导出当前内容。')
        if len(pcm) % 2 or not 320 <= len(pcm) <= RATE * 2 * 35:
            raise ValueError('音频片段格式或长度无效。')
        if not math.isfinite(start) or start < 0:
            raise ValueError('音频时间无效。')
        duration = len(pcm) / (RATE * 2)
        digest = hashlib.sha256(pcm).hexdigest()
        with self.lock:
            s = self.sessions[sid]
            if seq < s['next_seq']:
                old = next((r for r in s['rows'] if r['seq'] == seq), None)
                if old and old['digest'] == digest:
                    return {'accepted': True, 'duplicate': True}
                raise ValueError('重复序号的音频内容不同。')
            if s['status'] != 'recording':
                raise ValueError('会话已结束，无法继续接收音频。')
            if seq != s['next_seq'] or abs(start - s['received_seconds']) > 0.05:
                raise ValueError('音频片段顺序或时间不连续，请停止后重新开始。')
            if self.pending >= MAX_PENDING:
                raise OverflowError('处理队列已满，正在等待已有片段完成。')
            row = {'seq': seq, 'start': start, 'end': start + duration, 'text': '', 'note': '',
                   'capture_start': start, 'capture_end': start + duration, 'status': 'queued', 'review': False, 'digest': digest, 'asr_seconds': 0, 'translation_seconds': 0}
            s['rows'].append(row)
            s['next_seq'] += 1
            s['received_seconds'] += duration
            s['last_seen'] = time.time()
            self.persist(s)
            self.pending += 1
            self.enqueue_job({'sid': sid, 'seq': seq, 'pcm': pcm})
        return {'accepted': True}

    def finish(self, sid):
        with self.lock:
            s = self.sessions[sid]
            if s['status'] == 'recording':
                s['status'] = 'draining'
            self.settle(s)
            self.persist(s)

    def settle(self, s):
        working = any(r['status'] in ('queued', 'recognizing', 'waiting_translation', 'translating') for r in s['rows'])
        if s['status'] == 'draining' and not working:
            s['status'] = 'finished'
            self.cancel_preparation(s['id'])
            self.contexts.pop(s['id'], None)
            self.tails.pop(s['id'], None)
            self.recognized_sequences.pop(s['id'], None)
            self.tail_gaps.pop(s['id'], None)
            if getattr(self.translator, 'supports_streaming', False):
                from streaming import close_session
                close_session(s['id'])

    def retry(self, sid):
        with self.lock:
            if self.sessions[sid].get('provider', 'chatgpt') != self.provider:
                raise ValueError('请先切换到这场记录原来使用的 AI，再重试。')
            items = [(key, job) for key, job in self.failed.items() if key[0] == sid]
            if not items:
                raise ValueError('没有可重试的缓存；重启前失败的音频需要从原视频重播。')
            for key, job in items:
                if self.pending >= MAX_PENDING:
                    break
                row = next(r for r in self.sessions[sid]['rows'] if r['seq'] == key[1])
                row.update(status='queued', text='', note='')
                self.failed.pop(key)
                self.pending += 1
                self.enqueue_job(job)
            if self.sessions[sid]['status'] == 'finished':
                self.sessions[sid]['status'] = 'draining'
            self.persist(self.sessions[sid])

    def recognize_job(self, job, s, row):
        sid, seq = job['sid'], job['seq']
        if 'source' not in job:
            tail = job.get('tail', self.tails.get(sid, b''))
            context = job.get('context', self.contexts.get(sid, ''))
            job['tail'], job['context'] = tail, context
            recovery = {}
            if getattr(self.recognizer, 'supports_tail_recovery', False):
                job.setdefault('tail_gap', self.tail_gaps.get(sid, 0))
                recovery['uncommitted_tail_seconds'] = job['tail_gap']
            source, a, b, seconds, uncertain = self.recognizer.transcribe(job['pcm'], tail, context, list(s['glossary']), s.get('profile', 'fed'), **recovery)
            if seq > self.recognized_sequences.get(sid, -1):
                if recovery:
                    carry = job.get('tail_gap', 0) if not source and b == 0 else 0
                    gap = min(5, max(0, len(job['pcm']) / (RATE * 2) - b + carry))
                    self.tail_gaps[sid] = gap
                    keep = int((gap + 1) * RATE) * 2
                    self.tails[sid] = (tail + job['pcm'])[-keep:]
                else:
                    self.tails[sid] = job['pcm'][-RATE * 2:]
                self.contexts[sid] = (context + ' ' + source)[-1800:]
                self.recognized_sequences[sid] = seq
            job.update(source=source, uncertain=uncertain)
            row['asr_seconds'] = seconds
            if hasattr(self.recognizer, 'status_message'):
                self.asr = {'ready': True, 'message': self.recognizer.status_message}
            # Preserve original capture interval for retries, independent of word boundaries.
            row.setdefault('capture_start', row['start'])
            row['start'], row['end'] = row['capture_start'] + a, row['capture_start'] + b

    def translate_job(self, job, s, row):
        for attempt in range(len(self.retry_delays) + 1):
            try:
                stream = self.streaming_options(job, s, row)
                args = (job['source'], job['context'], s['glossary'], s['model'], s.get('profile', 'fed'))
                if s.get('provider', 'chatgpt') == 'chatgpt':
                    result, elapsed = self.translator(*args, **stream)
                else:
                    result, elapsed = self.translator(*args, provider=s['provider'], **stream)
                break
            except TranslationError as exc:
                if exc.kind != 'network' or attempt == len(self.retry_delays):
                    raise
                with self.lock:
                    row['note'] = f'连接暂时中断，正在自动重试（{attempt + 1}/{len(self.retry_delays)}）…'
                time.sleep(self.retry_delays[attempt])
        with self.lock:
            row.update(text=result['chinese'].strip(), status='done', translation_seconds=elapsed,
                       review=bool(result['review'] or job['uncertain']), note=result['note'])
            if job['uncertain'] and not row['note']:
                row['note'] = '部分音频识别把握较低，数字和专有名词建议复核。'

    def fail_job(self, job, s, row, exc):
        sid, seq = job['sid'], job['seq']
        with self.lock:
            # Never persist raw exception strings or raw source audio/transcripts.
            note = str(exc) if isinstance(exc, RuntimeError) and re.search('[\u3400-\u9fff]', str(exc)) else '语音识别或翻译失败，请重试。'
            row.update(status='failed', text='[该段翻译失败]', note=note, review=True)
            if isinstance(exc, TranslationError):
                self.problem = {'kind': exc.kind, 'session': sid, 'message': note + ' 已暂停处理，请解决后点击“继续处理”。'}
                self.gate.clear()
                if exc.kind == 'auth':
                    provider = s.get('provider', 'chatgpt')
                    if provider != 'chatgpt':
                        mark_login(provider, False)
                    self.codex = {'ready': False, 'message': PROVIDERS[provider]['label'] + ' 登录需要重新确认。'}
            if len(self.failed) < 30:
                self.failed[(sid, seq)] = job
            else:
                row['note'] += ' 内存重试缓存已满，请从原视频重播。'

    def state(self, sid=None):
        with self.lock:
            s = self.sessions.get(sid)
            if not s and self.sessions:
                s = next(reversed(self.sessions.values()))
            # Serialization here also prevents concurrent mutation during response writes.
            result = {'revision': self.revision, 'asr': self.asr, 'codex': self.codex, 'session': s, 'storage_error': self.storage_error,
                      'provider': self.provider, 'providers': PROVIDERS,
                      'login': self.login.state(), 'problem': self.problem,
                      'sessions': [{'id': x['id'], 'title': x['title'], 'created': x['created'], 'status': x['status']}
                                   for x in reversed(list(self.sessions.values()))],
                      'pending': self.pending, 'retryable': sum(1 for key in self.failed if s and key[0] == s['id'])}
            if s:
                result['latency'] = self.pipeline_state(s)
                result['backlog_seconds'] = round(sum(r['end'] - r['start'] for r in s['rows'] if r['status'] in ('queued','recognizing','waiting_translation','translating')), 1)
            result = json.loads(json.dumps(result, ensure_ascii=False))
            if result['session']:
                for row in result['session']['rows']:
                    preview = self.previews.get((result['session']['id'], row['seq']))
                    if preview and row['status'] == 'translating':
                        row['preview'] = preview
            return result

class Handler(BaseHTTPRequestHandler):
    engine = None
    token = None

    def log_message(self, *args):
        pass

    def send(self, data, status=200, content_type='application/json; charset=utf-8', filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; frame-ancestors 'self' chrome-extension://kiceknjkkhbfedilkgiegndlehnffmcc")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def local_request(self, mutation=False):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{host}' for host in allowed}:
            return False
        return not mutation or secrets.compare_digest(self.headers.get('X-Local-Token', ''), self.token)

    def do_GET(self):
        if not self.local_request():
            return self.send({'error': '仅允许本机页面访问。'}, 403)
        parsed = urlparse(self.path)
        args = parse_qs(parsed.query)
        try:
            if parsed.path == '/api/glossary-default':
                return self.send(json.loads((ROOT / 'glossary.json').read_text(encoding='utf-8')))
            if parsed.path == '/api/events':
                return serve_events(self, args.get('session', [None])[0])
            if parsed.path == '/api/state':
                return self.send(self.engine.state(args.get('session', [None])[0]))
            if parsed.path == '/api/config':
                return self.send({'app': 'fed-live-translator', 'distribution': 'public', 'instance': instance_id(), 'version': '0.3.1-beta', 'token': self.token,
                                  'providers': PROVIDERS,
                                  'language': 'en', 'glossary': self.engine.glossary,
                                  'glossary_info': json.loads((ROOT / 'glossary-info.json').read_text(encoding='utf-8')),
                                  'profiles': {key: item['label'] for key, item in PROFILES.items()}})
            if parsed.path == '/api/export':
                sid = args.get('session', [''])[0]
                with self.engine.lock:
                    s = json.loads(json.dumps(self.engine.sessions[sid]))
                fmt = args.get('format', ['txt'])[0]
                times = args.get('times', ['1'])[0] != '0'
                if fmt == 'txt':
                    body, mime = export_text(s, times).encode('utf-8-sig'), 'text/plain; charset=utf-8'
                elif fmt == 'srt':
                    body, mime = export_srt(s).encode('utf-8-sig'), 'application/x-subrip; charset=utf-8'
                elif fmt == 'docx':
                    body, mime = export_docx(s, times), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                else:
                    raise ValueError('不支持的导出格式。')
                return self.send(body, content_type=mime, filename=f'fed-{sid}.{fmt}')
            files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/capture.js': 'capture.js'}
            if parsed.path in files:
                file = ROOT / 'web' / files[parsed.path]
                return self.send(file.read_bytes(), content_type=mimetypes.guess_type(file)[0] or 'text/plain')
            return self.send({'error': '页面不存在。'}, 404)
        except (KeyError, ValueError):
            return self.send({'error': '记录不存在或导出参数无效。'}, 400)

    def do_POST(self):
        if not self.local_request(True):
            return self.send({'error': '请求已过期，请刷新本机页面。'}, 403)
        parsed = urlparse(self.path)
        args = parse_qs(parsed.query)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > RATE * 2 * 35 + 4096:
                return self.send({'error': '请求过大。'}, 413)
            body = self.rfile.read(length)
            if parsed.path == '/api/audio':
                return self.send(self.engine.accept(args['session'][0], int(args['seq'][0]), float(args['start'][0]), body))
            obj = json.loads(body or b'{}')
            if parsed.path == '/api/start':
                return self.send({'id': self.engine.start(obj.get('title', ''), obj.get('model', 'gpt-6-luna'), obj.get('profile', 'fed'), obj.get('provider'))})
            if parsed.path == '/api/provider':
                return self.send(self.engine.select_provider(obj['provider']))
            if parsed.path == '/api/heartbeat':
                self.engine.heartbeat(obj['session'])
                return self.send({'ok': True})
            if parsed.path == '/api/login':
                if obj.get('provider', self.engine.provider) != self.engine.provider:
                    raise ValueError('请先选择需要登录的 AI。')
                return self.send(self.engine.login.start(self.engine.provider))
            if parsed.path == '/api/resume':
                self.engine.resume(obj.get('session'), obj.get('model'))
                return self.send({'ok': True})
            if parsed.path == '/api/finish':
                self.engine.finish(obj['session'])
                return self.send({'ok': True})
            if parsed.path == '/api/retry':
                self.engine.retry(obj['session'])
                return self.send({'ok': True})
            if parsed.path == '/api/check-login':
                return self.send(self.engine.refresh_login())
            if parsed.path == '/api/glossary':
                glossary = obj['glossary']
                validate_glossary(glossary)
                with self.engine.lock:
                    self.engine.glossary = glossary
                    write_json(USER_DIR / 'glossary.json', glossary)
                return self.send({'ok': True})
            return self.send({'error': '接口不存在。'}, 404)
        except OverflowError as e:
            return self.send({'error': str(e)}, 429)
        except (ValueError, KeyError, TypeError) as e:
            return self.send({'error': str(e) if re.search('[\u3400-\u9fff]', str(e)) else '请求参数无效。'}, 400)
        except Exception:
            return self.send({'error': '本地服务处理失败，已有内容仍保存在记录中。'}, 500)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8878)
    parser.add_argument('--data-dir', type=Path, default=DATA)
    args = parser.parse_args()
    instance_lock = acquire_instance_lock()
    Handler.engine = Engine(data=args.data_dir)
    Handler.token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    USER_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DIR / 'server.pid').write_text(str(os.getpid()), encoding='ascii')
    def maintenance():
        while True:
            time.sleep(10)
            try:
                Handler.engine.expire_sessions()
                if Handler.engine.login.state()['running'] or not Handler.engine.codex['ready']:
                    Handler.engine.refresh_login()
            except (OSError, ValueError):
                pass
    threading.Thread(target=maintenance, daemon=True).start()
    print(f'美联储直播翻译已启动：http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.engine.login.cancel()
        server.server_close()

if __name__ == '__main__':
    main()
