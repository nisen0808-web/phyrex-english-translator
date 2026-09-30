"""Official Codex stdio streaming. In-memory threads; validated Chinese only."""
import atexit
from collections import deque
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import tomllib

import bridge
from runtime import ROOT


class StreamingUnavailable(RuntimeError):
    """Raised only before inference starts, allowing the existing CLI fallback."""


def chinese_preview(raw):
    """Decode only the chinese JSON string, including incomplete UTF-8 escapes."""
    match = re.match(r'^\s*\{\s*"chinese"\s*:\s*"', raw)
    if not match:
        return ''
    start, i = match.end(), match.end()
    while i < len(raw):
        if raw[i] == '"':
            break
        if raw[i] == '\\':
            if i + 1 >= len(raw):
                break
            if raw[i+1] == 'u':
                if i + 6 > len(raw):
                    break
                i += 6
            else:
                i += 2
        else:
            i += 1
    try:
        text = json.loads('"' + raw[start:i] + '"')
        text.encode('utf-8')  # Reject a partially received surrogate pair.
    except (ValueError, UnicodeError):
        return ''
    if not re.search('[\u3400-\u9fff]', text) or re.search(r'(?:\b[A-Za-z]+[ ,;:]+){8,}[A-Za-z]+', text):
        return ''
    return text


class CodexStream:
    def __init__(self):
        self.lock = threading.RLock()
        self.proc = None
        self.key = self.thread = None
        self.turns = self.number = 0
        self.events = deque()

    def close(self):
        with self.lock:
            process, self.proc = self.proc, None
            self.thread = self.key = None
            self.events.clear()
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                for handle in (process.stdin, process.stdout):
                    if handle:
                        handle.close()

    @staticmethod
    def read_output(process, messages):
        try:
            for line in process.stdout:
                if len(line) > 2_000_000:
                    break
                messages.put(json.loads(line))
        except (ValueError, OSError):
            pass
        finally:
            messages.put({'closed': True})

    def send(self, value):
        self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()

    def next_message(self, until):
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        try:
            message = self.messages.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError() from None
        if message.get('closed'):
            raise OSError('Official client disconnected')
        # The translator never services agent requests or user approvals.
        if 'method' in message and 'id' in message:
            self.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Unavailable in translator'}})
            raise OSError('Unexpected agent request')
        return message

    def rpc(self, method, params, seconds=15):
        self.number += 1
        number = self.number
        self.send({'id': number, 'method': method, 'params': params})
        until = time.monotonic() + seconds
        while True:
            message = self.next_message(until)
            if message.get('id') == number:
                if 'error' in message:
                    raise StreamingUnavailable('官方流式连接暂不可用。')
                return message['result']
            self.events.append(message)

    def connect(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        self.close()
        env = bridge.environment()
        work = ROOT / '.runtime/codex-work'
        work.mkdir(parents=True, exist_ok=True)
        overrides = {'forced_login_method': 'chatgpt', 'model_provider': 'openai',
                     'web_search': 'disabled', 'history.persistence': 'none',
                     'analytics.enabled': False, 'features.shell_tool': False,
                     'features.apps': False, 'features.plugins': False,
                     'features.multi_agent': False, 'features.memories': False,
                     'features.hooks': False, 'features.image_generation': False,
                     'project_doc_max_bytes': 0, 'developer_instructions': ''}
        # app-server has no exec --ignore-user-config equivalent. Disable each
        # configured MCP by name without copying or exposing any credentials.
        path = Path(env['CODEX_HOME']) / 'config.toml'
        if path.exists():
            config = tomllib.loads(path.read_text(encoding='utf-8-sig'))
            for name in config.get('mcp_servers', {}):
                if not re.fullmatch(r'[\w-]+', name):
                    raise StreamingUnavailable('连接配置不适合流式模式。')
                overrides['mcp_servers.' + name + '.enabled'] = False
        command = [bridge.codex_path(), 'app-server', '--listen', 'stdio://']
        for name, value in overrides.items():
            command.extend(['-c', name + '=' + json.dumps(value, ensure_ascii=False)])
        self.proc = subprocess.Popen(command, cwd=work, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, encoding='utf-8', creationflags=bridge.NO_WINDOW)
        self.messages = queue.Queue()
        threading.Thread(target=self.read_output, args=(self.proc, self.messages), daemon=True).start()
        self.rpc('initialize', {'clientInfo': {'name': 'phyrex_live_translator', 'title': 'Phyrex Live Translator', 'version': '0.3.1'}, 'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized', 'params': {}})
        self.check_account()

    def check_account(self):
        # Reuse the authenticated official process; never start a login CLI
        # subprocess for each audio segment. Still validate before every turn.
        account = self.rpc('account/read', {'refreshToken': False})
        if (account.get('account') or {}).get('type') != 'chatgpt':
            self.close()
            raise bridge.TranslationError('请使用自己的 ChatGPT 账号登录。', 'auth')

    def prepare(self, instruction, model, session_id, cancelled=None):
        with self.lock:
            if cancelled is not None and cancelled.is_set():
                return
            try:
                self.connect()
                self.check_account()
                key = (session_id, model, instruction)
                # Rotate bounded temporary conversations; no source-text disk log.
                if self.key != key or self.turns >= 8:
                    if self.thread and self.proc and self.proc.poll() is None:
                        try:
                            self.rpc('thread/unsubscribe', {'threadId': self.thread})
                        except (StreamingUnavailable, OSError, TimeoutError):
                            self.close()
                    self.connect()
                    result = self.rpc('thread/start', {'model': model, 'modelProvider': 'openai',
                        'cwd': str(ROOT / '.runtime/codex-work'), 'ephemeral': True,
                        'approvalPolicy': 'never', 'sandbox': 'read-only',
                        'baseInstructions': instruction})
                    if result['thread'].get('ephemeral') is not True:
                        raise StreamingUnavailable('流式临时会话未就绪。')
                    self.thread, self.key, self.turns = result['thread']['id'], key, 0
                if cancelled is not None and cancelled.is_set():
                    self.close()
            except bridge.TranslationError:
                raise
            except (StreamingUnavailable, OSError, TimeoutError, ValueError, KeyError):
                self.close()
                raise StreamingUnavailable('流式连接初始化失败，使用兼容翻译方式。') from None

    def translate(self, prompt, model, session_id, on_partial):
        started = time.monotonic()
        instruction, payload = prompt.split('\n资料 JSON：\n', 1)
        with self.lock:
            self.prepare(instruction, model, session_id)
            self.events.clear()
            raw, last_preview, final = '', '', None
            schema = json.loads((ROOT / 'translation.schema.json').read_text(encoding='utf-8'))
            try:
                # Once inference is submitted, do not silently resubmit it.
                response = self.rpc('turn/start', {'threadId': self.thread,
                    'input': [{'type': 'text', 'text': '当前待翻译资料 JSON：\n' + payload}],
                    'effort': 'low', 'outputSchema': schema})
                turn_id = response['turn']['id']
                self.turns += 1
                until = started + 90
                while True:
                    event = self.events.popleft() if self.events else self.next_message(until)
                    params, method = event.get('params', {}), event.get('method')
                    if params.get('threadId', self.thread) != self.thread or params.get('turnId', turn_id) != turn_id:
                        continue
                    if method == 'item/agentMessage/delta':
                        raw += params.get('delta', '')
                        if len(raw) > 100_000:
                            raise ValueError('Oversized translation')
                        preview = chinese_preview(raw)
                        if preview and preview != last_preview:
                            on_partial(preview)
                            last_preview = preview
                    elif method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
                        final = params['item'].get('text')
                    elif method == 'turn/completed':
                        turn = params['turn']
                        if turn.get('id') != turn_id:
                            continue
                        if turn['status'] != 'completed':
                            raw_error = json.dumps(turn.get('error') or {})
                            raise bridge.TranslationError(bridge.failure_message(raw_error), bridge.failure_kind(raw_error))
                        result = bridge.validate_result(json.loads(final if final is not None else raw))
                        return result, round(time.monotonic() - started, 2)
            except bridge.TranslationError:
                self.close()
                raise
            except (OSError, TimeoutError, StreamingUnavailable):
                self.close()
                raise bridge.TranslationError('流式翻译连接中断，请重试该段。', 'network') from None
            except (ValueError, TypeError, KeyError, AttributeError):
                self.close()
                raise bridge.TranslationError('流式译文未通过格式检查，请重试该段。', 'format') from None


CLIENT = CodexStream()
atexit.register(CLIENT.close)


def translate(prompt, model, session_id, on_partial):
    return CLIENT.translate(prompt, model, session_id, on_partial)


def close_session(session_id):
    with CLIENT.lock:
        if CLIENT.key and CLIENT.key[0] == session_id:
            CLIENT.close()
